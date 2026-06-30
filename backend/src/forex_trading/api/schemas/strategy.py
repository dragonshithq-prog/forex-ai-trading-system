"""Strategy Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID


class StrategyCreate(BaseModel):
    """Strategy creation schema."""
    name: str = Field(..., min_length=1, max_length=100)
    strategy_type: str = Field(..., description="trend_following, mean_reversion, etc.")
    description: str | None = None
    parameters: dict = Field(default_factory=dict)
    symbols: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    max_position_size_pct: float = Field(2.0, gt=0, le=100)
    risk_per_trade_pct: float = Field(1.0, gt=0, le=10)


class StrategyUpdate(BaseModel):
    """Strategy update schema."""
    name: str | None = None
    description: str | None = None
    status: str | None = None
    parameters: dict | None = None
    symbols: list[str] | None = None
    timeframes: list[str] | None = None
    max_position_size_pct: float | None = None
    risk_per_trade_pct: float | None = None


class StrategyResponse(BaseModel):
    """Strategy response schema."""
    id: UUID
    name: str
    strategy_type: str
    description: str | None
    status: str
    parameters: dict
    symbols: list
    timeframes: list
    max_position_size_pct: float
    risk_per_trade_pct: float
    total_trades: int
    winning_trades: int
    total_pnl: float
    created_at: datetime

    model_config = {"from_attributes": True}

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades


class AIDecisionResponse(BaseModel):
    """AI Decision response schema (XAI)."""
    id: UUID
    symbol: str
    timeframe: str
    direction: str
    confidence: float
    agreement_ratio: float
    conflict_ratio: float
    agents_responding: int
    total_agents: int
    was_rejected: bool
    rejection_reason: str | None
    market_regime: str | None
    session: str | None
    price_at_decision: float | None
    agent_signals: dict
    rationale: str | None
    was_executed: bool
    outcome_pnl: float | None
    decision_time: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentPerformanceResponse(BaseModel):
    """Agent performance response schema."""
    id: UUID
    agent_type: str
    symbol: str
    timeframe: str
    total_signals: int
    correct_signals: int
    avg_confidence: float
    period_start: datetime
    period_end: datetime

    model_config = {"from_attributes": True}

    @property
    def accuracy(self) -> float:
        if self.total_signals == 0:
            return 0.0
        return self.correct_signals / self.total_signals
