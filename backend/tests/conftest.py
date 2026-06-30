"""
Comprehensive test configuration and fixtures.

Provides realistic OHLCV candle generators, auth helpers, mock brokers,
risk engine instances, and the async httpx test client.
"""

from __future__ import annotations

import asyncio
import math
import random
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Event loop (session-scoped)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop – required by pytest-asyncio for async fixtures."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# OHLCV candle generators
# ---------------------------------------------------------------------------

def _make_candles(
    n: int = 200,
    base: float = 1.1000,
    trend: float = 0.0,
    volatility: float = 0.0010,
    seed: int = 42,
) -> list[dict]:
    """Generate n realistic OHLCV candles."""
    rng = random.Random(seed)
    candles: list[dict] = []
    price = base
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        price = price + trend + rng.gauss(0, volatility)
        price = max(price, 0.0001)
        open_ = price + rng.gauss(0, volatility * 0.3)
        close = price + rng.gauss(0, volatility * 0.3)
        high = max(open_, close) + abs(rng.gauss(0, volatility * 0.4))
        low = min(open_, close) - abs(rng.gauss(0, volatility * 0.4))
        candles.append({
            "timestamp": ts + timedelta(hours=i),
            "open": round(open_, 5),
            "high": round(high, 5),
            "low": round(low, 5),
            "close": round(close, 5),
            "volume": int(abs(rng.gauss(500, 200))) + 50,
        })
    return candles


@pytest.fixture
def sample_candles() -> list[dict]:
    """200 realistic OHLCV candles (random walk)."""
    return _make_candles(n=200, seed=42)


@pytest.fixture
def trending_candles() -> list[dict]:
    """200 candles in a clear uptrend (+0.00015 per bar)."""
    return _make_candles(n=200, trend=0.00015, seed=1)


@pytest.fixture
def ranging_candles() -> list[dict]:
    """200 flat/ranging candles (zero trend)."""
    return _make_candles(n=200, trend=0.0, volatility=0.0005, seed=3)


@pytest.fixture
def bearish_candles() -> list[dict]:
    """200 candles in a clear downtrend."""
    return _make_candles(n=200, trend=-0.00015, seed=2)


@pytest.fixture
def high_volatility_candles() -> list[dict]:
    """200 candles with high volatility (3× normal)."""
    return _make_candles(n=200, volatility=0.0030, seed=7)


# ---------------------------------------------------------------------------
# Risk engine fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def risk_engine():
    """Fresh RiskEngine configured with tight test limits."""
    from forex_trading.risk.engine import RiskEngine, RiskLimits
    limits = RiskLimits(
        max_position_size_pct=2.0,
        max_total_exposure_pct=20.0,
        max_positions=10,
        daily_drawdown_limit_pct=3.0,
        max_drawdown_limit_pct=15.0,
        max_consecutive_losses=5,
        cooldown_minutes=60,
    )
    engine = RiskEngine(limits=limits)
    engine.update_state(equity=10_000.0, drawdown_pct=0.0)
    return engine


# ---------------------------------------------------------------------------
# Mock broker plugin
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_broker_plugin():
    """Mock BrokerPlugin that returns realistic test data."""
    plugin = MagicMock()
    plugin.is_connected = True
    plugin.broker_name = "paper_test"

    account_info = MagicMock()
    account_info.balance = 10_000.0
    account_info.equity = 10_000.0
    account_info.leverage = 100
    account_info.currency = "USD"
    plugin.get_account_info = AsyncMock(return_value=account_info)

    plugin.place_order = AsyncMock(return_value={
        "order_id": f"BROKER-{uuid4().hex[:8].upper()}",
        "fill_price": 1.1002,
        "status": "filled",
    })
    plugin.close_position = AsyncMock(return_value={"status": "closed"})
    plugin.get_open_positions = AsyncMock(return_value=[])
    plugin.get_order = AsyncMock(return_value={"status": "filled"})
    plugin.connect = AsyncMock()
    plugin.disconnect = AsyncMock()
    return plugin


# ---------------------------------------------------------------------------
# Market context fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def market_context(sample_candles):
    """MarketContext with 200 sample candles for agent testing."""
    from forex_trading.ai.agents.base import MarketContext, MarketRegime
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        candles=sample_candles,
        regime=MarketRegime.RANGING,
        metadata={
            "spread": 1.2,
            "current_drawdown_pct": 0.5,
            "open_positions": [],
        },
    )


# ---------------------------------------------------------------------------
# JWT / auth helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def jwt_algorithm() -> str:
    """Algorithm used by security_manager in test environment."""
    from forex_trading.core.security import security_manager
    return security_manager.algorithm


@pytest.fixture
def make_token():
    """Factory to create valid JWT tokens for arbitrary roles."""
    from forex_trading.core.security import security_manager

    def _make(user_id: str = "test-user-id", role: str = "trader",
               permissions: list[str] | None = None) -> str:
        return security_manager.create_access_token(
            user_id=user_id,
            role=role,
            permissions=permissions or [],
        )

    return _make


# ---------------------------------------------------------------------------
# ASGI test client (no real DB – lifespan bypassed)
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """
    httpx AsyncClient wired to the FastAPI app.

    The lifespan is bypassed so no real DB/Redis/Kafka connection is attempted.
    All endpoint dependencies that touch external services must be overridden
    per-test using ``app.dependency_overrides``.
    """
    from forex_trading.main import create_application

    # Build a fresh app without the lifespan hooks
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from forex_trading.config import get_settings
    from forex_trading.core.exceptions import setup_exception_handlers
    from forex_trading.core.middleware import setup_middleware
    from forex_trading.api.router import api_router
    from forex_trading.api.websocket import router as ws_router

    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        # No lifespan – tests don't need DB/cache
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    setup_exception_handlers(app)
    setup_middleware(app)
    app.include_router(api_router, prefix=settings.API_PREFIX)
    app.include_router(ws_router)

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": settings.APP_VERSION}

    @app.get("/health/detailed")
    async def detailed_health():
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT.value,
        }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Standalone UUID / symbol fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_uuid():
    return uuid4()


@pytest.fixture
def sample_symbol():
    return "EURUSD"
