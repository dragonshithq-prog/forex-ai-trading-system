"""Strategy and AI Decision CRUD operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.crud_base import CRUDBase
from forex_trading.shared.database.models_strategy import (
    Strategy,
    AIDecision,
    AgentPerformance,
)


class StrategyRepository(CRUDBase[Strategy]):
    """Strategy repository."""

    async def get_by_name(self, db: AsyncSession, *, name: str) -> Strategy | None:
        """Get strategy by name."""
        result = await db.execute(select(Strategy).where(Strategy.name == name))
        return result.scalar_one_or_none()

    async def get_active_strategies(self, db: AsyncSession) -> list[Strategy]:
        """Get all active strategies."""
        return await self.get_multi(
            db, filters=[Strategy.status == "active", Strategy.is_deleted == False]
        )

    async def get_by_type(
        self, db: AsyncSession, *, strategy_type: str
    ) -> list[Strategy]:
        """Get strategies by type."""
        return await self.get_multi(
            db,
            filters=[Strategy.strategy_type == strategy_type, Strategy.is_deleted == False],
        )

    async def update_performance(
        self,
        db: AsyncSession,
        *,
        strategy_id: UUID,
        total_trades: int,
        winning_trades: int,
        total_pnl: float,
    ) -> Strategy | None:
        """Update strategy performance metrics."""
        strategy = await self.get(db, strategy_id)
        if strategy:
            strategy.total_trades = total_trades
            strategy.winning_trades = winning_trades
            strategy.total_pnl = total_pnl
            db.add(strategy)
            await db.commit()
            await db.refresh(strategy)
        return strategy


class AIDecisionRepository(CRUDBase[AIDecision]):
    """AI Decision repository for XAI logging."""

    async def get_by_symbol(
        self,
        db: AsyncSession,
        *,
        symbol: str,
        limit: int = 100,
    ) -> list[AIDecision]:
        """Get AI decisions for a symbol."""
        return await self.get_multi(
            db, filters=[AIDecision.symbol == symbol], limit=limit
        )

    async def get_recent_decisions(
        self, db: AsyncSession, *, limit: int = 50
    ) -> list[AIDecision]:
        """Get recent AI decisions."""
        result = await db.execute(
            select(AIDecision).order_by(AIDecision.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_rejected_decisions(
        self, db: AsyncSession, *, limit: int = 50
    ) -> list[AIDecision]:
        """Get rejected AI decisions."""
        return await self.get_multi(
            db, filters=[AIDecision.was_rejected == True], limit=limit
        )

    async def record_execution(
        self,
        db: AsyncSession,
        *,
        decision_id: UUID,
        pnl: float | None = None,
    ) -> AIDecision | None:
        """Record that a decision was executed."""
        decision = await self.get(db, decision_id)
        if decision:
            decision.was_executed = True
            if pnl is not None:
                decision.outcome_pnl = pnl
            db.add(decision)
            await db.commit()
            await db.refresh(decision)
        return decision


class AgentPerformanceRepository(CRUDBase[AgentPerformance]):
    """Agent performance repository."""

    async def get_by_agent_type(
        self,
        db: AsyncSession,
        *,
        agent_type: str,
        symbol: str | None = None,
    ) -> list[AgentPerformance]:
        """Get performance records for an agent type."""
        filters = [AgentPerformance.agent_type == agent_type]
        if symbol:
            filters.append(AgentPerformance.symbol == symbol)
        return await self.get_multi(db, filters=filters)


# Repository instances
strategy_repository = StrategyRepository(Strategy)
ai_decision_repository = AIDecisionRepository(AIDecision)
agent_performance_repository = AgentPerformanceRepository(AgentPerformance)
