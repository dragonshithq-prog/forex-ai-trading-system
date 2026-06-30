"""Broker Account Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BrokerConnectionRequest(BaseModel):
    broker_type: str = Field(..., description="Broker type: oanda, mt4, mt5, ctrader")
    account_number: str = Field(..., min_length=1, max_length=100)
    environment: str = Field("practice", description="practice or live")
    api_key: str | None = None
    api_secret: str | None = None
    password: str | None = None
    host: str | None = None
    port: int | None = Field(None, gt=0, le=65535)


class BrokerConnectionResponse(BaseModel):
    id: UUID
    account_id: UUID
    status: str
    connected_at: datetime | None
    last_heartbeat: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}


class AccountInfoResponse(BaseModel):
    account_id: UUID
    broker_type: str
    account_number: str
    environment: str
    currency: str
    leverage: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level_pct: float | None
    unrealized_pnl: float
    open_positions: int
    last_sync: datetime | None


class BrokerStatusResponse(BaseModel):
    broker_type: str
    is_connected: bool
    ping_ms: float | None
    server_time: datetime | None
    status_message: str
    last_heartbeat: datetime | None


# Legacy schemas for compatibility with existing broker router
class BrokerAccountCreate(BaseModel):
    broker_type: str = Field(..., description="Broker type (oanda, mt5, etc.)")
    account_name: str = Field(..., min_length=1, max_length=255)
    account_number: str = Field(..., min_length=1, max_length=100)
    environment: str = Field("practice", description="practice or live")
    api_key: str | None = None
    api_secret: str | None = None
    password: str | None = None
    host: str | None = None
    port: int | None = None


class BrokerAccountUpdate(BaseModel):
    account_name: str | None = None
    is_active: bool | None = None


class BrokerAccountResponse(BaseModel):
    id: UUID
    broker_type: str
    account_name: str
    account_number: str
    environment: str
    currency: str
    leverage: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    unrealized_pnl: float
    is_active: bool
    last_sync: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
