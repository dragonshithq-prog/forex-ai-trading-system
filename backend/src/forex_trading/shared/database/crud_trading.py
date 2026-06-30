"""Trading CRUD operations (Orders, Positions, Deals)."""

from typing import Any
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.crud_base import CRUDBase
from forex_trading.shared.database.models_trading import Order, Position, Deal


class OrderRepository(CRUDBase[Order]):
    """Order repository with trading-specific queries."""

    async def get_by_broker_account(
        self,
        db: AsyncSession,
        *,
        broker_account_id: UUID,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Order]:
        """Get orders for a broker account."""
        filters = [Order.broker_account_id == broker_account_id]
        if status:
            filters.append(Order.status == status)
        return await self.get_multi(db, filters=filters, limit=limit)

    async def get_by_symbol(
        self,
        db: AsyncSession,
        *,
        symbol: str,
        status: str | None = None,
    ) -> list[Order]:
        """Get orders for a symbol."""
        filters = [Order.symbol == symbol]
        if status:
            filters.append(Order.status == status)
        return await self.get_multi(db, filters=filters)

    async def get_active_orders(self, db: AsyncSession) -> list[Order]:
        """Get all active (pending/new) orders."""
        return await self.get_multi(
            db,
            filters=[Order.status.in_(["pending", "new", "partially_filled"])],
        )

    async def get_by_broker_order_id(
        self, db: AsyncSession, *, broker_order_id: str
    ) -> Order | None:
        """Get order by broker's order ID."""
        result = await db.execute(
            select(Order).where(Order.broker_order_id == broker_order_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        db: AsyncSession,
        *,
        order_id: UUID,
        status: str,
        filled_quantity: float | None = None,
        filled_price: float | None = None,
    ) -> Order | None:
        """Update order status."""
        from datetime import datetime

        order = await self.get(db, order_id)
        if order:
            order.status = status
            if filled_quantity is not None:
                order.filled_quantity = filled_quantity
            if filled_price is not None:
                order.filled_price = filled_price
            if status == "filled":
                order.filled_at = datetime.utcnow()
            elif status == "cancelled":
                order.cancelled_at = datetime.utcnow()
            db.add(order)
            await db.commit()
            await db.refresh(order)
        return order


class PositionRepository(CRUDBase[Position]):
    """Position repository with trading-specific queries."""

    async def get_open_positions(
        self, db: AsyncSession, *, broker_account_id: UUID | None = None
    ) -> list[Position]:
        """Get all open positions."""
        filters = [Position.status == "open"]
        if broker_account_id:
            filters.append(Position.broker_account_id == broker_account_id)
        return await self.get_multi(db, filters=filters)

    async def get_by_symbol(
        self, db: AsyncSession, *, symbol: str, status: str = "open"
    ) -> list[Position]:
        """Get positions for a symbol."""
        return await self.get_multi(
            db, filters=[Position.symbol == symbol, Position.status == status]
        )

    async def count_open_positions(
        self, db: AsyncSession, *, broker_account_id: UUID | None = None
    ) -> int:
        """Count open positions."""
        filters = [Position.status == "open"]
        if broker_account_id:
            filters.append(Position.broker_account_id == broker_account_id)
        return await self.count(db, filters=filters)

    async def get_total_exposure(
        self, db: AsyncSession, *, broker_account_id: UUID
    ) -> float:
        """Calculate total exposure percentage."""
        result = await db.execute(
            select(func.sum(Position.size * Position.current_price)).where(
                Position.broker_account_id == broker_account_id,
                Position.status == "open",
            )
        )
        total_exposure = result.scalar_one() or 0.0
        return total_exposure


class DealRepository(CRUDBase[Deal]):
    """Deal repository."""

    async def get_by_order(self, db: AsyncSession, *, order_id: UUID) -> list[Deal]:
        """Get deals for an order."""
        return await self.get_multi(db, filters=[Deal.order_id == order_id])

    async def get_by_position(
        self, db: AsyncSession, *, position_id: UUID
    ) -> list[Deal]:
        """Get deals for a position."""
        return await self.get_multi(db, filters=[Deal.position_id == position_id])


# Repository instances
order_repository = OrderRepository(Order)
position_repository = PositionRepository(Position)
deal_repository = DealRepository(Deal)
