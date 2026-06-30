"""Market Data Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CandleResponse(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: str


class TickResponse(BaseModel):
    symbol: str
    bid: float
    ask: float
    spread: float
    timestamp: datetime


class SessionResponse(BaseModel):
    active_session: str
    sessions_active: list[str]
    is_overlap: bool
    session_strength: float
    time_to_next_session_minutes: int | None


class MarketStructureResponse(BaseModel):
    symbol: str
    timeframe: str
    trend_direction: str
    support_levels: list[float]
    resistance_levels: list[float]
    order_blocks: list[dict]
    fair_value_gaps: list[dict]


class CurrencyStrengthResponse(BaseModel):
    currency: str
    strength_score: float
    rank: int
    pairs_analyzed: int
    timestamp: datetime


class EconomicEventResponse(BaseModel):
    event_id: str
    title: str
    country: str
    currency: str
    impact: str
    scheduled_at: datetime
    actual: str | None
    forecast: str | None
    previous: str | None


class PairInfoResponse(BaseModel):
    symbol: str
    base_currency: str
    quote_currency: str
    session_affinity: list[str]
    typical_spread: float | None
    pip_size: float


# Legacy schemas kept for backward compatibility
class SymbolResponse(BaseModel):
    id: UUID
    symbol: str
    description: str | None
    base_currency: str
    quote_currency: str
    pip_value: float
    pip_size: float
    min_lot_size: float
    max_lot_size: float
    lot_step: float
    typical_spread: float | None
    is_active: bool

    model_config = {"from_attributes": True}


class TickLegacyResponse(BaseModel):
    symbol: str
    bid: float
    ask: float
    spread: float
    volume: float | None
    timestamp: datetime


class MarketStructureLegacyResponse(BaseModel):
    symbol: str
    timeframe: str
    structure_type: str
    break_type: str
    trend_direction: str
    strength: float
    order_blocks: list[dict] | None
    fair_value_gaps: list[dict] | None
    liquidity_zones: list[dict] | None
    timestamp: datetime


class SessionInfoResponse(BaseModel):
    active_session: str
    sessions_active: list[str]
    is_overlap: bool
    overlap_sessions: list[str]
    session_strength: float
