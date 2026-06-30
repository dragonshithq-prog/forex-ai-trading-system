"""Risk Management CRUD operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.crud_base import CRUDBase
from forex_trading.shared.database.models_risk import (
    RiskConfiguration,
    RiskState,
    RiskAlert,
    RiskOverride,
)


class RiskConfigurationRepository(CRUDBase[RiskConfiguration]):
    """Risk configuration repository."""

    async def get_by_account(
        self, db: AsyncSession, *, broker_account_id: UUID
    ) -> RiskConfiguration | None:
        """Get risk configuration for a broker account."""
        result = await db.execute(
            select(RiskConfiguration).where(
                RiskConfiguration.broker_account_id == broker_account_id,
                RiskConfiguration.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def get_global_config(self, db: AsyncSession) -> RiskConfiguration | None:
        """Get global risk configuration (no account)."""
        result = await db.execute(
            select(RiskConfiguration).where(
                RiskConfiguration.broker_account_id == None,
                RiskConfiguration.is_active == True,
            )
        )
        return result.scalar_one_or_none()


class RiskStateRepository(CRUDBase[RiskState]):
    """Risk state repository."""

    async def get_by_account(
        self, db: AsyncSession, *, broker_account_id: UUID
    ) -> RiskState | None:
        """Get risk state for a broker account."""
        result = await db.execute(
            select(RiskState).where(
                RiskState.broker_account_id == broker_account_id
            )
        )
        return result.scalar_one_or_none()

    async def update_drawdown(
        self,
        db: AsyncSession,
        *,
        broker_account_id: UUID,
        current_drawdown_pct: float,
        max_drawdown_pct: float,
    ) -> RiskState | None:
        """Update drawdown state."""
        state = await self.get_by_account(db, broker_account_id=broker_account_id)
        if state:
            state.current_drawdown_pct = current_drawdown_pct
            state.max_drawdown_pct = max_drawdown_pct
            db.add(state)
            await db.commit()
            await db.refresh(state)
        return state

    async def update_exposure(
        self,
        db: AsyncSession,
        *,
        broker_account_id: UUID,
        total_exposure_pct: float,
        open_positions: int,
    ) -> RiskState | None:
        """Update exposure state."""
        state = await self.get_by_account(db, broker_account_id=broker_account_id)
        if state:
            state.total_exposure_pct = total_exposure_pct
            state.open_positions = open_positions
            db.add(state)
            await db.commit()
            await db.refresh(state)
        return state

    async def activate_circuit_breaker(
        self,
        db: AsyncSession,
        *,
        broker_account_id: UUID,
        until: Any,
        reason: str,
    ) -> RiskState | None:
        """Activate circuit breaker."""
        state = await self.get_by_account(db, broker_account_id=broker_account_id)
        if state:
            state.is_circuit_breaker_active = True
            state.circuit_breaker_until = until
            state.circuit_breaker_reason = reason
            db.add(state)
            await db.commit()
            await db.refresh(state)
        return state


class RiskAlertRepository(CRUDBase[RiskAlert]):
    """Risk alert repository."""

    async def get_by_account(
        self,
        db: AsyncSession,
        *,
        broker_account_id: UUID,
        acknowledged: bool | None = None,
        limit: int = 100,
    ) -> list[RiskAlert]:
        """Get alerts for a broker account."""
        filters = [RiskAlert.broker_account_id == broker_account_id]
        if acknowledged is not None:
            filters.append(RiskAlert.acknowledged == acknowledged)
        return await self.get_multi(db, filters=filters, limit=limit)

    async def get_by_level(
        self,
        db: AsyncSession,
        *,
        level: str,
        limit: int = 100,
    ) -> list[RiskAlert]:
        """Get alerts by level."""
        return await self.get_multi(
            db, filters=[RiskAlert.level == level], limit=limit
        )

    async def acknowledge(
        self, db: AsyncSession, *, alert_id: UUID
    ) -> RiskAlert | None:
        """Acknowledge an alert."""
        from datetime import datetime

        alert = await self.get(db, alert_id)
        if alert:
            alert.acknowledged = True
            alert.acknowledged_at = datetime.utcnow()
            db.add(alert)
            await db.commit()
            await db.refresh(alert)
        return alert


class RiskOverrideRepository(CRUDBase[RiskOverride]):
    """Risk override audit log repository."""

    async def get_by_account(
        self, db: AsyncSession, *, broker_account_id: UUID, limit: int = 100
    ) -> list[RiskOverride]:
        """Get overrides for a broker account."""
        return await self.get_multi(
            db,
            filters=[RiskOverride.broker_account_id == broker_account_id],
            limit=limit,
        )

    async def get_by_order(
        self, db: AsyncSession, *, order_id: UUID
    ) -> list[RiskOverride]:
        """Get overrides for an order."""
        return await self.get_multi(
            db, filters=[RiskOverride.order_id == order_id]
        )


# Repository instances
risk_config_repository = RiskConfigurationRepository(RiskConfiguration)
risk_state_repository = RiskStateRepository(RiskState)
risk_alert_repository = RiskAlertRepository(RiskAlert)
risk_override_repository = RiskOverrideRepository(RiskOverride)
