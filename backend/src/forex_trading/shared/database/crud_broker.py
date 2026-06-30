"""Broker Account CRUD operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from forex_trading.shared.database.crud_base import CRUDBase
from forex_trading.shared.database.models_broker import BrokerAccount, BrokerConnection


class BrokerAccountRepository(CRUDBase[BrokerAccount]):
    """Broker account repository."""

    async def get_by_user(
        self, db: AsyncSession, *, user_id: UUID
    ) -> list[BrokerAccount]:
        """Get all broker accounts for a user."""
        return await self.get_multi(
            db,
            filters=[BrokerAccount.user_id == user_id, BrokerAccount.is_deleted == False],
        )

    async def get_with_connections(
        self, db: AsyncSession, *, id: UUID
    ) -> BrokerAccount | None:
        """Get broker account with connections."""
        result = await db.execute(
            select(BrokerAccount)
            .options(selectinload(BrokerAccount.connections))
            .where(BrokerAccount.id == id)
        )
        return result.scalar_one_or_none()

    async def get_active_accounts(self, db: AsyncSession) -> list[BrokerAccount]:
        """Get all active broker accounts."""
        return await self.get_multi(
            db,
            filters=[BrokerAccount.is_active == True, BrokerAccount.is_deleted == False],
        )

    async def update_balance(
        self,
        db: AsyncSession,
        *,
        account_id: UUID,
        balance: float,
        equity: float,
        margin: float,
        free_margin: float,
        unrealized_pnl: float,
    ) -> BrokerAccount | None:
        """Update account balance."""
        from datetime import datetime

        account = await self.get(db, account_id)
        if account:
            account.balance = balance
            account.equity = equity
            account.margin = margin
            account.free_margin = free_margin
            account.unrealized_pnl = unrealized_pnl
            account.last_sync = datetime.utcnow()
            db.add(account)
            await db.commit()
            await db.refresh(account)
        return account


class BrokerConnectionRepository(CRUDBase[BrokerConnection]):
    """Broker connection repository."""

    async def get_by_account(
        self, db: AsyncSession, *, account_id: UUID
    ) -> list[BrokerConnection]:
        """Get connections for an account."""
        return await self.get_multi(
            db,
            filters=[BrokerConnection.account_id == account_id],
        )

    async def get_active_connection(
        self, db: AsyncSession, *, account_id: UUID
    ) -> BrokerConnection | None:
        """Get active connection for an account."""
        result = await db.execute(
            select(BrokerConnection).where(
                BrokerConnection.account_id == account_id,
                BrokerConnection.status == "connected",
            )
        )
        return result.scalar_one_or_none()


# Repository instances
broker_account_repository = BrokerAccountRepository(BrokerAccount)
broker_connection_repository = BrokerConnectionRepository(BrokerConnection)
