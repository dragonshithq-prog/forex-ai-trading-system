"""Unit of Work — atomic transactional boundary for aggregate persistence.

Every command that touches multiple aggregates (e.g., place order + update
risk state + emit event) must happen inside a single UnitOfWork.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Callable
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.outbox import create_outbox_entry
from forex_trading.shared.database.repository import (
    OrderRepository,
    PositionRepository,
    TradeRepository,
    RiskStateRepository,
    RiskAlertRepository,
    RiskOverrideRepository,
    AIDecisionRepository,
)

logger = structlog.get_logger()


class UnitOfWork:
    """Atomic transaction boundary.

    Usage::

        async with uow_factory() as uow:
            uow.orders.add(order)
            uow.positions.add(position)
            uow.add_event("trading.order.placed", ...)
            await uow.commit()   # writes order + position + outbox in one transaction
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._events: list[dict[str, Any]] = []

        # Repositories
        self.orders = OrderRepository(session)
        self.positions = PositionRepository(session)
        self.trades = TradeRepository(session)
        self.risk_states = RiskStateRepository(session)
        self.risk_alerts = RiskAlertRepository(session)
        self.risk_overrides = RiskOverrideRepository(session)
        self.ai_decisions = AIDecisionRepository(session)

    def add_event(
        self,
        aggregate_type: str,
        aggregate_id: UUID | None,
        event_type: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
    ) -> None:
        """Register a domain event to be written to the outbox on commit."""
        self._events.append(
            create_outbox_entry(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
                trace_id=trace_id,
            )
        )

    async def commit(self) -> None:
        """Commit the transaction and flush outbox events."""
        from forex_trading.shared.database.models_trading import EventOutbox

        for evt in self._events:
            entry = EventOutbox(**evt)
            self._session.add(entry)

        await self._session.commit()
        self._events.clear()
        logger.debug("uow_committed", events_count=len(self._events))

    async def rollback(self) -> None:
        """Roll back the transaction."""
        await self._session.rollback()
        self._events.clear()
        logger.debug("uow_rolled_back")

    async def flush(self) -> None:
        """Flush without committing (useful for getting generated IDs)."""
        await self._session.flush()

    @property
    def session(self) -> AsyncSession:
        return self._session


class UnitOfWorkFactory:
    """Creates UnitOfWork instances with proper session lifecycle.

    Used as the sole way to get a UoW throughout the application.
    """

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> UnitOfWork:
        self._session = self._session_factory()
        self._uow = UnitOfWork(self._session)
        return self._uow

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            await self._uow.rollback()
        await self._session.close()
