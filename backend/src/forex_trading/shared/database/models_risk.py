"""Risk Management models."""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from forex_trading.shared.database.base import BaseModel


class RiskLevel(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class OverrideAction(str, enum.Enum):
    REJECT_ORDER = "reject_order"
    CLOSE_POSITION = "close_position"
    REDUCE_SIZE = "reduce_size"
    HALT_TRADING = "halt_trading"
    EMERGENCY_LIQUIDATE = "emergency_liquidate"


class RiskConfiguration(BaseModel):
    """Risk configuration for an account or globally."""

    __tablename__ = "risk_configurations"

    broker_account_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("broker_accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    max_position_size_pct: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    max_total_exposure_pct: Mapped[float] = mapped_column(Float, default=20.0, nullable=False)
    max_positions: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    daily_drawdown_limit_pct: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    weekly_drawdown_limit_pct: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    monthly_drawdown_limit_pct: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    max_drawdown_limit_pct: Mapped[float] = mapped_column(Float, default=15.0, nullable=False)

    max_exposure_per_pair_pct: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    max_correlated_exposure_pct: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)

    max_slippage_pips: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    max_spread_pips: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)

    max_consecutive_losses: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RiskState(BaseModel):
    """Current risk state tracking."""

    __tablename__ = "risk_states"

    broker_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("broker_accounts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    current_equity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    peak_equity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    daily_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    weekly_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    monthly_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    total_exposure_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    open_positions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    consecutive_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_circuit_breaker_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    circuit_breaker_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    circuit_breaker_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_trade_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RiskAlert(BaseModel):
    """Risk management alerts."""

    __tablename__ = "risk_alerts"
    __table_args__ = (
        Index("idx_risk_alerts_level_timestamp", "level", "created_at"),
    )

    broker_account_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("broker_accounts.id", ondelete="CASCADE"),
        nullable=True,
    )

    level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    current_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    action_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RiskOverride(BaseModel):
    """Risk override audit log."""

    __tablename__ = "risk_overrides"

    broker_account_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("broker_accounts.id", ondelete="CASCADE"),
        nullable=True,
    )
    order_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    position_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("positions.id", ondelete="SET NULL"),
        nullable=True,
    )

    action: Mapped[OverrideAction] = mapped_column(Enum(OverrideAction), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk_state_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
