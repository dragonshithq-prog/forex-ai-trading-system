"""Risk Management Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UpdateRiskConfigRequest(BaseModel):
    max_position_size_pct: float | None = Field(None, gt=0, le=100)
    max_total_exposure_pct: float | None = Field(None, gt=0, le=100)
    max_positions: int | None = Field(None, gt=0, le=100)
    daily_drawdown_limit_pct: float | None = Field(None, gt=0, le=100)
    weekly_drawdown_limit_pct: float | None = Field(None, gt=0, le=100)
    monthly_drawdown_limit_pct: float | None = Field(None, gt=0, le=100)
    max_drawdown_limit_pct: float | None = Field(None, gt=0, le=100)
    max_exposure_per_pair_pct: float | None = Field(None, gt=0, le=100)
    max_correlated_exposure_pct: float | None = Field(None, gt=0, le=100)
    max_slippage_pips: float | None = Field(None, gt=0)
    max_spread_pips: float | None = Field(None, gt=0)
    max_consecutive_losses: int | None = Field(None, gt=0)
    cooldown_minutes: int | None = Field(None, gt=0)
    risk_per_trade_pct: float | None = Field(None, gt=0, le=10)


class RiskConfigResponse(BaseModel):
    id: UUID
    broker_account_id: UUID | None
    max_position_size_pct: float
    max_total_exposure_pct: float
    max_positions: int
    daily_drawdown_limit_pct: float
    weekly_drawdown_limit_pct: float
    monthly_drawdown_limit_pct: float
    max_drawdown_limit_pct: float
    max_exposure_per_pair_pct: float
    max_correlated_exposure_pct: float
    max_slippage_pips: float
    max_spread_pips: float
    max_consecutive_losses: int
    cooldown_minutes: int
    risk_per_trade_pct: float
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskStateResponse(BaseModel):
    id: UUID
    broker_account_id: UUID
    current_equity: float
    peak_equity: float
    current_drawdown_pct: float
    max_drawdown_pct: float
    daily_pnl: float
    weekly_pnl: float
    monthly_pnl: float
    total_exposure_pct: float
    open_positions: int
    consecutive_losses: int
    daily_trades: int
    is_circuit_breaker_active: bool
    circuit_breaker_until: datetime | None
    circuit_breaker_reason: str | None
    last_updated: datetime
    last_trade_at: datetime | None

    model_config = {"from_attributes": True}


class RiskAlertResponse(BaseModel):
    id: UUID
    broker_account_id: UUID | None
    level: str
    category: str
    message: str
    current_value: float | None
    threshold_value: float | None
    action_required: bool
    acknowledged: bool
    acknowledged_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CircuitBreakerResponse(BaseModel):
    is_active: bool
    activated_at: datetime | None
    active_until: datetime | None
    reason: str | None
    broker_account_id: UUID | None


class ExposureResponse(BaseModel):
    broker_account_id: UUID
    total_exposure_pct: float
    long_exposure_pct: float
    short_exposure_pct: float
    exposure_by_symbol: dict[str, float]
    exposure_by_currency: dict[str, float]
    timestamp: datetime


# Legacy aliases for existing router compatibility
class RiskConfigUpdate(BaseModel):
    max_position_size_pct: float | None = Field(None, gt=0, le=100)
    max_total_exposure_pct: float | None = Field(None, gt=0, le=100)
    max_positions: int | None = Field(None, gt=0, le=100)
    daily_drawdown_limit_pct: float | None = Field(None, gt=0, le=100)
    weekly_drawdown_limit_pct: float | None = Field(None, gt=0, le=100)
    monthly_drawdown_limit_pct: float | None = Field(None, gt=0, le=100)
    max_drawdown_limit_pct: float | None = Field(None, gt=0, le=100)
    max_exposure_per_pair_pct: float | None = Field(None, gt=0, le=100)
    max_correlated_exposure_pct: float | None = Field(None, gt=0, le=100)
    max_slippage_pips: float | None = Field(None, gt=0)
    max_spread_pips: float | None = Field(None, gt=0)
    max_consecutive_losses: int | None = Field(None, gt=0)
    cooldown_minutes: int | None = Field(None, gt=0)
    risk_per_trade_pct: float | None = Field(None, gt=0, le=10)


class RiskAssessmentResponse(BaseModel):
    is_approved: bool
    adjusted_size: float | None
    max_allowed_size: float
    warnings: list[str]
    violations: list[str]
    risk_score: float


class RiskOverrideResponse(BaseModel):
    id: UUID
    broker_account_id: UUID | None
    order_id: UUID | None
    position_id: UUID | None
    action: str
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}
