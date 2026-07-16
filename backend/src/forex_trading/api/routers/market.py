"""Market data API router.

Provides endpoints for market data retrieval.
Uses the standard JWT Bearer auth (not HTTP Basic).
All input is validated via Pydantic.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_current_user, get_db
from forex_trading.shared.database.models_user import User

router = APIRouter(prefix="/market", tags=["Market Data"])


@router.get(
    "/data",
    summary="Get market data",
    description="Get current bid/ask prices for a forex symbol",
    operation_id="get_market_data",
    responses={
        200: {"description": "Market data retrieved successfully"},
        422: {"description": "Invalid symbol format"},
    },
)
async def get_market_data(
    symbol: str = Query(..., min_length=6, max_length=20, description="Forex pair (e.g. EURUSD)"),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get current market data for a symbol."""
    return {
        "symbol": symbol.upper(),
        "bid": 1.0,
        "ask": 1.0001,
        "timestamp": time.time(),
        "message": "Placeholder — wire to your market data provider",
    }


@router.get(
    "/symbols",
    summary="List available symbols",
    description="List all available forex trading symbols",
    operation_id="list_symbols",
)
async def list_symbols(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List available trading symbols."""
    return [
        {"symbol": "EURUSD", "description": "Euro vs US Dollar"},
        {"symbol": "GBPUSD", "description": "British Pound vs US Dollar"},
        {"symbol": "USDJPY", "description": "US Dollar vs Japanese Yen"},
        {"symbol": "AUDUSD", "description": "Australian Dollar vs US Dollar"},
        {"symbol": "USDCAD", "description": "US Dollar vs Canadian Dollar"},
        {"symbol": "GBPJPY", "description": "British Pound vs Japanese Yen"},
    ]
