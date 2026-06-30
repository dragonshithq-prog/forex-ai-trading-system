"""Core exceptions and error handling."""

from typing import Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger()


class TradingSystemError(Exception):
    """Base exception for the trading system."""

    def __init__(self, message: str, code: str = "SYSTEM_ERROR", details: dict | None = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class DomainError(TradingSystemError):
    """Base exception for domain errors."""
    pass


class ValidationError(TradingSystemError):
    """Validation error exception."""
    def __init__(self, message: str, field: str | None = None, **kwargs):
        super().__init__(message, code="VALIDATION_ERROR", **kwargs)
        self.field = field


class NotFoundError(TradingSystemError):
    """Resource not found exception."""
    def __init__(self, resource: str, identifier: str | None = None):
        message = f"{resource} not found"
        if identifier:
            message += f": {identifier}"
        super().__init__(message, code="NOT_FOUND")


class AuthenticationError(TradingSystemError):
    """Authentication failed exception."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code="AUTHENTICATION_ERROR")


class AuthorizationError(TradingSystemError):
    """Authorization failed exception."""
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, code="AUTHORIZATION_ERROR")


class BrokerConnectionError(TradingSystemError):
    """Broker connection failed exception."""
    def __init__(self, broker: str, message: str = "Connection failed"):
        super().__init__(message, code="BROKER_CONNECTION_ERROR", details={"broker": broker})


class OrderExecutionError(TradingSystemError):
    """Order execution failed exception."""
    def __init__(self, order_id: str, message: str = "Execution failed"):
        super().__init__(message, code="ORDER_EXECUTION_ERROR", details={"order_id": order_id})


class RiskLimitExceeded(TradingSystemError):
    """Risk limit exceeded exception."""
    def __init__(self, limit_type: str, current: float, threshold: float):
        message = f"Risk limit exceeded: {limit_type} = {current} (threshold: {threshold})"
        super().__init__(message, code="RISK_LIMIT_EXCEEDED", details={
            "limit_type": limit_type,
            "current_value": current,
            "threshold": threshold,
        })


class CircuitBreakerActive(TradingSystemError):
    """Circuit breaker is active exception."""
    def __init__(self, reason: str = "Circuit breaker active", cooldown_minutes: int = 60):
        super().__init__(reason, code="CIRCUIT_BREAKER_ACTIVE", details={
            "cooldown_minutes": cooldown_minutes,
        })


class MarketDataError(TradingSystemError):
    """Market data error exception."""
    def __init__(self, symbol: str, message: str = "Data unavailable"):
        super().__init__(message, code="MARKET_DATA_ERROR", details={"symbol": symbol})


class ModelNotReadyError(TradingSystemError):
    """AI model not ready exception."""
    def __init__(self, model_name: str):
        super().__init__(f"Model not ready: {model_name}", code="MODEL_NOT_READY")


def setup_exception_handlers(app: FastAPI) -> None:
    """Setup custom exception handlers for the FastAPI app."""

    @app.exception_handler(TradingSystemError)
    async def trading_system_error_handler(request: Request, exc: TradingSystemError) -> JSONResponse:
        logger.error("trading_system_error", error=exc.code, message=exc.message, details=exc.details)
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(exc.detail),
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                }
            },
        )
