"""Strategy and AI Decision models."""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forex_trading.shared.database.base import BaseModel, SoftDeleteMixin


class StrategyType(str, enum.Enum):
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    SCALPING = "scalping"
    BREAKOUT = "breakout"
    GRID_TRADING = "grid_trading"
    SENTIMENT_FADE = "sentiment_fade"


class StrategyStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class Strategy(BaseModel, SoftDeleteMixin):
    """Trading strategy configuration."""

    __tablename__ = "strategies"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    strategy_type: Mapped[StrategyType] = mapped_column(Enum(StrategyType), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[StrategyStatus] = mapped_column(
        Enum(StrategyStatus), default=StrategyStatus.ACTIVE, nullable=False
    )

    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    symbols: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    timeframes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    max_position_size_pct: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Relationships
    orders = relationship("Order", back_populates="strategy", lazy="selectin")
    positions = relationship("Position", back_populates="strategy", lazy="selectin")
    ai_decisions = relationship("AIDecision", back_populates="strategy", lazy="selectin")

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades


class AgentType(str, enum.Enum):
    STRUCTURE = "structure"
    TREND = "trend"
    MOMENTUM = "momentum"
    LIQUIDITY = "liquidity"
    SENTIMENT = "sentiment"
    VOLATILITY = "volatility"
    CORRELATION = "correlation"


class SignalDirection(str, enum.Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class AIDecision(BaseModel):
    """AI decision log."""

    __tablename__ = "ai_decisions"
    __table_args__ = (
        Index("idx_ai_decisions_symbol_timestamp", "symbol", "created_at"),
    )

    strategy_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
    )

    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    direction: Mapped[SignalDirection] = mapped_column(Enum(SignalDirection), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    agreement_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    conflict_ratio: Mapped[float] = mapped_column(Float, nullable=False)

    agents_responding: Mapped[int] = mapped_column(Integer, nullable=False)
    total_agents: Mapped[int] = mapped_column(Integer, nullable=False)
    was_rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    market_regime: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    session: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    price_at_decision: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    agent_signals: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    was_executed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outcome_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    decision_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    strategy = relationship("Strategy", back_populates="ai_decisions")


class AgentPerformance(BaseModel):
    """Track individual agent performance."""

    __tablename__ = "agent_performance"

    agent_type: Mapped[AgentType] = mapped_column(Enum(AgentType), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)

    total_signals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_signals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @property
    def accuracy(self) -> float:
        if self.total_signals == 0:
            return 0.0
        return self.correct_signals / self.total_signals
