"""Pydantic schemas for API request/response validation."""

from forex_trading.api.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    TokenPayload,
)
from forex_trading.api.schemas.user import UserResponse, UserUpdate
from forex_trading.api.schemas.broker import (
    BrokerAccountCreate,
    BrokerAccountResponse,
)
from forex_trading.api.schemas.trading import (
    OrderCreate,
    OrderResponse,
    PositionResponse,
)
from forex_trading.api.schemas.strategy import (
    StrategyCreate,
    StrategyResponse,
)
from forex_trading.api.schemas.risk import (
    RiskConfigUpdate,
    RiskStateResponse,
)
from forex_trading.api.schemas.market import (
    SymbolResponse,
    CandleResponse,
    TickResponse,
)
from forex_trading.api.schemas.common import (
    PaginationParams,
    PaginatedResponse,
    ErrorResponse,
    SuccessResponse,
)

__all__ = [
    "LoginRequest",
    "RegisterRequest",
    "TokenResponse",
    "TokenPayload",
    "UserResponse",
    "UserUpdate",
    "BrokerAccountCreate",
    "BrokerAccountResponse",
    "OrderCreate",
    "OrderResponse",
    "PositionResponse",
    "StrategyCreate",
    "StrategyResponse",
    "RiskConfigUpdate",
    "RiskStateResponse",
    "SymbolResponse",
    "CandleResponse",
    "TickResponse",
    "PaginationParams",
    "PaginatedResponse",
    "ErrorResponse",
    "SuccessResponse",
]
