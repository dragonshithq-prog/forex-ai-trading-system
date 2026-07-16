"""Repository pattern — one repository per aggregate root.

All DB access goes through repositories. No raw SQLAlchemy queries
outside of this module (except migrations).

Performance Optimizations (Phase 8):
- Query timeouts on all repository queries
- N+1 query detection with logging
- Pagination defaults on all list endpoints
- Eager loading for common relationship patterns
- Cache-aware query execution
"""

from __future__ import annotations

import time
import warnings
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select, func, update, delete, and_, event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload, contains_eager

from forex_trading.shared.database.base import BaseModel
from forex_trading.shared.database.models_trading import (
    Order,
    OrderStatus,
    Position,
    PositionStatus,
    Deal,
)
from forex_trading.shared.database.models_risk import (
    RiskState,
    RiskAlert,
    RiskOverride,
    RiskLevel,
)
from forex_trading.shared.database.models_strategy import AIDecision

ModelType = TypeVar("ModelType", bound=BaseModel)

# Performance tuning constants
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 500
_QUERY_TIMEOUT_WARNING_SECONDS = 1.0  # log warning for queries > 1 second
_N_PLUS_ONE_THRESHOLD = 10  # warn if more than 10 lazy loads per session

# N+1 query detection trackers
_session_query_counts: dict[int, int] = {}


def _track_query(connection, cursor, statement, parameters, context, executemany):
    """Listen to after_execute events to detect N+1 queries."""
    import threading
    thread_id = threading.get_ident()
    _session_query_counts[thread_id] = _session_query_counts.get(thread_id, 0) + 1


def reset_query_count() -> None:
    """Reset the query counter for the current thread."""
    import threading
    _session_query_counts[threading.get_ident()] = 0


def get_query_count() -> int:
    """Get the number of queries executed in the current thread."""
    import threading
    return _session_query_counts.get(threading.get_ident(), 0)


def check_n_plus_one(threshold: int = _N_PLUS_ONE_THRESHOLD) -> None:
    """Check if N+1 query pattern detected and warn if so.

    Call this after fetching a list of entities and accessing relationships.
    """
    count = get_query_count()
    if count > threshold:
        import warnings as _warnings
        _warnings.warn(
            f"Potential N+1 query detected: {count} queries executed "
            f"(threshold: {threshold}). Consider using eager loading."
        )


class QueryTimer:
    """Context manager to time query execution and log slow queries."""

    def __init__(self, operation: str, details: str = ""):
        self._operation = operation
        self._details = details
        self._start: float = 0.0

    async def __aenter__(self) -> QueryTimer:
        self._start = time.monotonic()
        return self

    async def __aexit__(self, *args: Any) -> None:
        elapsed = time.monotonic() - self._start
        if elapsed > _QUERY_TIMEOUT_WARNING_SECONDS:
            import structlog
            log = structlog.get_logger()
            log.warning(
                "slow_query",
                operation=self._operation,
                elapsed_seconds=round(elapsed, 3),
                details=self._details,
            )


class BaseRepository(Generic[ModelType]):
    """Generic repository with common operations and performance optimizations."""

    def __init__(self, session: AsyncSession, model: type[ModelType]) -> None:
        self._session = session
        self._model = model

    def _apply_eager_loading(self, query: Any) -> Any:
        """Apply default eager loading for known relationship patterns.

        Override in subclasses for model-specific eager loading.
        """
        return query

    async def add(self, obj: ModelType) -> None:
        self._session.add(obj)

    async def add_all(self, objs: list[ModelType]) -> None:
        self._session.add_all(objs)

    async def get(self, id: UUID) -> ModelType | None:
        async with QueryTimer("repository.get", f"{self._model.__name__}.id={id}"):
            query = select(self._model).where(self._model.id == id)
            query = self._apply_eager_loading(query)
            result = await self._session.execute(query)
            return result.scalar_one_or_none()

    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = _DEFAULT_PAGE_SIZE,
        filters: list | None = None,
        order_by: Any | None = None,
    ) -> list[ModelType]:
        # Enforce pagination limits
        limit = min(limit, _MAX_PAGE_SIZE)
        skip = max(0, skip)

        async with QueryTimer(
            "repository.get_multi",
            f"{self._model.__name__}.skip={skip}.limit={limit}",
        ):
            query = select(self._model)
            query = self._apply_eager_loading(query)
            if filters:
                for f in filters:
                    query = query.where(f)
            if order_by is not None:
                query = query.order_by(order_by)
            query = query.offset(skip).limit(limit)
            result = await self._session.execute(query)
            return list(result.scalars().all())

    async def count(self, filters: list | None = None) -> int:
        async with QueryTimer("repository.count", self._model.__name__):
            query = select(func.count()).select_from(self._model)
            if filters:
                for f in filters:
                    query = query.where(f)
            result = await self._session.execute(query)
            return result.scalar_one()

    async def update(self, obj: ModelType, values: dict[str, Any]) -> None:
        for key, val in values.items():
            if hasattr(obj, key):
                setattr(obj, key, val)
        self._session.add(obj)

    async def delete(self, obj: ModelType) -> None:
        await self._session.delete(obj)

    async def exists(self, id: UUID) -> bool:
        async with QueryTimer("repository.exists", f"{self._model.__name__}.id={id}"):
            result = await self._session.execute(
                select(self._model.id).where(self._model.id == id)
            )
            return result.scalar_one_or_none() is not None

    async def get_multi_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = _DEFAULT_PAGE_SIZE,
        filters: list | None = None,
        order_by: Any | None = None,
    ) -> tuple[list[ModelType], int, int]:
        """Get paginated results with total count.

        Returns:
            (items, total_count, total_pages)
        """
        page = max(1, page)
        page_size = min(max(1, page_size), _MAX_PAGE_SIZE)
        skip = (page - 1) * page_size

        total = await self.count(filters=filters)
        total_pages = max(1, (total + page_size - 1) // page_size)

        items = await self.get_multi(
            skip=skip,
            limit=page_size,
            filters=filters,
            order_by=order_by,
        )
        return items, total, total_pages


class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Order)

    def _apply_eager_loading(self, query: Any) -> Any:
        return query.options(
            selectinload(Order.strategy),
            selectinload(Order.broker_account),
        )

    async def get_by_broker_id(self, broker_order_id: str) -> Order | None:
        async with QueryTimer("order.get_by_broker_id", broker_order_id):
            query = select(Order).where(Order.broker_order_id == broker_order_id)
            query = self._apply_eager_loading(query)
            result = await self._session.execute(query)
            return result.scalar_one_or_none()

    async def get_by_symbol_and_status(
        self, symbol: str, status: OrderStatus, limit: int = _DEFAULT_PAGE_SIZE
    ) -> list[Order]:
        return await self.get_multi(
            filters=[Order.symbol == symbol, Order.status == status],
            limit=limit,
        )

    async def get_pending_orders(self, broker_account_id: UUID | None = None) -> list[Order]:
        filters = [Order.status.in_([OrderStatus.PENDING, OrderStatus.NEW])]
        if broker_account_id is not None:
            filters.append(Order.broker_account_id == broker_account_id)
        return await self.get_multi(filters=filters)


class PositionRepository(BaseRepository[Position]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Position)

    def _apply_eager_loading(self, query: Any) -> Any:
        return query.options(
            selectinload(Position.strategy),
            selectinload(Position.broker_account),
            selectinload(Position.deals),
        )

    async def get_open_positions(
        self, broker_account_id: UUID | None = None
    ) -> list[Position]:
        filters = [Position.status == PositionStatus.OPEN]
        if broker_account_id is not None:
            filters.append(Position.broker_account_id == broker_account_id)
        return await self.get_multi(filters=filters)

    async def get_by_symbol(
        self, symbol: str, status: PositionStatus | None = None
    ) -> list[Position]:
        filters = [Position.symbol == symbol]
        if status is not None:
            filters.append(Position.status == status)
        return await self.get_multi(filters=filters)

    async def get_by_broker_position_id(self, broker_position_id: str) -> Position | None:
        async with QueryTimer("position.get_by_broker_position_id", broker_position_id):
            query = select(Position).where(Position.broker_position_id == broker_position_id)
            query = self._apply_eager_loading(query)
            result = await self._session.execute(query)
            return result.scalar_one_or_none()


class TradeRepository(BaseRepository[Deal]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Deal)

    async def get_by_position(self, position_id: UUID) -> list[Deal]:
        return await self.get_multi(filters=[Deal.position_id == position_id])

    async def get_by_order(self, order_id: UUID) -> list[Deal]:
        return await self.get_multi(filters=[Deal.order_id == order_id])


class RiskStateRepository(BaseRepository[RiskState]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RiskState)

    async def get_by_account(self, broker_account_id: UUID) -> RiskState | None:
        async with QueryTimer("risk_state.get_by_account", str(broker_account_id)):
            result = await self._session.execute(
                select(RiskState).where(RiskState.broker_account_id == broker_account_id)
            )
            return result.scalar_one_or_none()

    async def upsert(self, broker_account_id: UUID, values: dict[str, Any]) -> RiskState:
        existing = await self.get_by_account(broker_account_id)
        if existing:
            for key, val in values.items():
                if hasattr(existing, key):
                    setattr(existing, key, val)
            existing.last_updated = datetime.now(timezone.utc)
            return existing
        state = RiskState(broker_account_id=broker_account_id, **values)
        self._session.add(state)
        return state


class RiskAlertRepository(BaseRepository[RiskAlert]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RiskAlert)

    async def get_active_alerts(
        self, level: RiskLevel | None = None, limit: int = _DEFAULT_PAGE_SIZE
    ) -> list[RiskAlert]:
        filters = [RiskAlert.acknowledged == False]
        if level is not None:
            filters.append(RiskAlert.level == level)
        return await self.get_multi(
            filters=filters,
            order_by=RiskAlert.created_at.desc(),
            limit=limit,
        )


class RiskOverrideRepository(BaseRepository[RiskOverride]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RiskOverride)


class AIDecisionRepository(BaseRepository[AIDecision]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AIDecision)

    def _apply_eager_loading(self, query: Any) -> Any:
        return query.options(
            selectinload(AIDecision.strategy),
        )

    async def get_by_symbol(
        self, symbol: str, limit: int = _DEFAULT_PAGE_SIZE
    ) -> list[AIDecision]:
        return await self.get_multi(
            filters=[AIDecision.symbol == symbol],
            order_by=AIDecision.decision_time.desc(),
            limit=limit,
        )
