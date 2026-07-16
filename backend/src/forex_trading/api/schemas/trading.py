"""Trading Pydantic schemas (Orders, Positions).

All inputs are strictly validated:
  - Symbol format: ``^[A-Z]{6}$`` (e.g. EURUSD, GBPJPY)
  - Numeric ranges (quantity > 0, price > 0)
  - UUID format for IDs
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# Forex symbol validation pattern
SYMBOL_PATTERN = re.compile(r"^[A-Z]{6}$")

# Valid currency codes
_VALID_CURRENCIES: set[str] = {
    "EUR", "USD", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF",
    "SGD", "HKD", "NOK", "SEK", "MXN", "ZAR", "TRY", "CNH",
    "XAU", "XAG", "XPT", "XPD", "BTC", "ETH",
}


def validate_forex_symbol(symbol: str) -> str:
    """Validate a forex symbol (e.g. EURUSD)."""
    s = symbol.upper().strip()
    if not SYMBOL_PATTERN.match(s):
        raise ValueError(f"Invalid symbol format: '{symbol}'. Must be 6 uppercase letters (e.g. EURUSD)")
    base = s[:3]
    quote = s[3:]
    if base not in _VALID_CURRENCIES or quote not in _VALID_CURRENCIES:
        raise ValueError(f"Invalid currency pair: '{symbol}'. Unknown currency code(s)")
    return s


class PlaceOrderRequest(BaseModel):
    symbol: str = Field(..., min_length=6, max_length=20, description="Forex pair (e.g. EURUSD)")
    side: str = Field(..., description="buy or sell")
    quantity: float = Field(..., gt=0, description="Trade size in lots")
    order_type: str = Field("market", description="market, limit, stop, stop_limit")
    price: float | None = Field(None, gt=0, description="Required for limit/stop orders")
    stop_loss: float | None = Field(None, gt=0, description="Stop loss price")
    take_profit: float | None = Field(None, gt=0, description="Take profit price")
    comment: str | None = Field(None, max_length=500)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        return validate_forex_symbol(v)

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in ("buy", "sell"):
            raise ValueError("Side must be 'buy' or 'sell'")
        return v_lower

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        v_lower = v.lower()
        valid_types = {"market", "limit", "stop", "stop_limit"}
        if v_lower not in valid_types:
            raise ValueError(f"Order type must be one of: {', '.join(sorted(valid_types))}")
        return v_lower


class ClosePositionRequest(BaseModel):
    partial_pct: float = Field(default=100.0, ge=1.0, le=100.0, description="Percentage of position to close (1-100)")
    reason: str | None = Field(None, max_length=500, description="Optional reason for closing")

    @field_validator("partial_pct")
    @classmethod
    def round_pct(cls, v: float) -> float:
        return round(v, 2)


class UpdateStopLossRequest(BaseModel):
    stop_loss: float = Field(..., gt=0, description="New stop loss price")

    @field_validator("stop_loss")
    @classmethod
    def round_price(cls, v: float) -> float:
        return round(v, 5)


class UpdateTakeProfitRequest(BaseModel):
    take_profit: float = Field(..., gt=0, description="New take profit price")

    @field_validator("take_profit")
    @classmethod
    def round_price(cls, v: float) -> float:
        return round(v, 5)


class OrderResponse(BaseModel):
    order_id: str
    symbol: str
    side: str
    quantity: float
    status: str
    filled_price: float | None
    created_at: datetime


class PositionResponse(BaseModel):
    position_id: str
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: float | None
    take_profit: float | None
    opened_at: datetime


# Legacy schemas kept for compatibility with existing CRUD routers
class OrderCreate(BaseModel):
    broker_account_id: UUID
    symbol: str = Field(..., min_length=6, max_length=20)
    side: str = Field(..., description="buy or sell")
    order_type: str = Field("market", description="market, limit, stop, stop_limit")
    quantity: float = Field(..., gt=0)
    price: float | None = Field(None, gt=0)
    stop_price: float | None = Field(None, gt=0)
    take_profit: float | None = Field(None, gt=0)
    stop_loss: float | None = Field(None, gt=0)
    time_in_force: str = Field("gtc", description="gtc, ioc, fok, day")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        return validate_forex_symbol(v)

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in ("buy", "sell"):
            raise ValueError("Side must be 'buy' or 'sell'")
        return v_lower

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        v_lower = v.lower()
        valid_types = {"market", "limit", "stop", "stop_limit"}
        if v_lower not in valid_types:
            raise ValueError(f"Order type must be one of: {', '.join(sorted(valid_types))}")
        return v_lower

    @field_validator("time_in_force")
    @classmethod
    def validate_tif(cls, v: str) -> str:
        v_lower = v.lower()
        valid_tif = {"gtc", "ioc", "fok", "day"}
        if v_lower not in valid_tif:
            raise ValueError(f"Time in force must be one of: {', '.join(sorted(valid_tif))}")
        return v_lower


class OrderFullResponse(BaseModel):
    id: UUID
    broker_account_id: UUID
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None
    stop_price: float | None
    take_profit: float | None
    stop_loss: float | None
    status: str
    filled_quantity: float
    filled_price: float | None
    commission: float
    slippage: float
    broker_order_id: str | None
    rejection_reason: str | None
    submitted_at: datetime | None
    filled_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderModify(BaseModel):
    quantity: float | None = Field(None, gt=0, description="New quantity")
    price: float | None = Field(None, gt=0, description="New price")
    stop_loss: float | None = Field(None, gt=0, description="New stop loss")
    take_profit: float | None = Field(None, gt=0, description="New take profit")


class PositionFullResponse(BaseModel):
    id: UUID
    broker_account_id: UUID
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    stop_loss: float | None
    take_profit: float | None
    trailing_stop: float | None
    status: str
    broker_position_id: str | None
    commission: float
    swap: float
    opened_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class DealResponse(BaseModel):
    id: UUID
    order_id: UUID
    position_id: UUID | None
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float
    slippage: float
    realized_pnl: float | None
    broker_deal_id: str | None
    executed_at: datetime

    model_config = {"from_attributes": True}
