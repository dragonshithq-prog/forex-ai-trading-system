"""Trading Pydantic schemas (Orders, Positions)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PlaceOrderRequest(BaseModel):
    symbol: str = Field(..., min_length=6, max_length=20)
    side: str = Field(..., description="buy or sell")
    quantity: float = Field(..., gt=0)
    order_type: str = Field("market", description="market, limit, stop, stop_limit")
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    comment: str | None = Field(None, max_length=500)


class ClosePositionRequest(BaseModel):
    partial_pct: float = Field(default=100.0, ge=1.0, le=100.0)
    reason: str | None = None


class UpdateStopLossRequest(BaseModel):
    stop_loss: float = Field(..., gt=0)


class UpdateTakeProfitRequest(BaseModel):
    take_profit: float = Field(..., gt=0)


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
    price: float | None = None
    stop_price: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    time_in_force: str = Field("gtc", description="gtc, ioc, fok, day")


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
    quantity: float | None = Field(None, gt=0)
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None


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
