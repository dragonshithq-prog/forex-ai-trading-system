"""
Comprehensive test configuration and fixtures for the forex trading system.

Provides:
- AsyncSQLAlchemy engine using aiosqlite (in-memory)
- Session factory with nested transactions for isolation
- UoW factory for the test session
- Mock BrokerGateway, EventBus, and CacheManager
- Container with all services wired for testing
- Test data factories for Order, Position, AIDecision, RiskState, EventOutbox
- OHLCV candle generators
"""

from __future__ import annotations

import asyncio
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from forex_trading.shared.database.base import Base
from forex_trading.shared.database.uow import UnitOfWork, UnitOfWorkFactory
from forex_trading.shared.messaging.event_bus import EventBus, EventHandler


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
# Per-test in-memory SQLite database
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_engine():
    """Create a fresh in-memory aiosqlite engine for each test.

    Using ``file::memory:?cache=shared&uri=true`` with a random cache ID
    to ensure every test gets its own isolated database.
    """
    import uuid as _uuid
    db_id = _uuid.uuid4().hex
    url = f"sqlite+aiosqlite:///file:{db_id}?mode=memory&cache=private&uri=true"
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh async session for a test-isolated database.

    Each call gets its own in-memory database, so data never leaks between
    tests.  The session has no wrapping transaction — UoW/outbox commits
    persist to the isolated database and cleanup happens when the engine
    is disposed at the end of the test.
    """
    connection = await db_engine.connect()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    # Begin a savepoint so that tests can roll back without affecting
    # the isolated database's state for subsequent tests.
    await session.begin_nested()

    yield session

    await session.close()
    # Rollback the connection in case any uncommitted changes remain
    await connection.rollback()
    await connection.close()


@pytest_asyncio.fixture
async def uow_factory(db_session) -> UnitOfWorkFactory:
    """Create a UnitOfWorkFactory wired to the test db_session."""
    factory = UnitOfWorkFactory(lambda: db_session)
    return factory


# ---------------------------------------------------------------------------
# Mock BrokerGateway
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_broker_gateway():
    """Mock BrokerGateway that returns realistic test data."""
    gw = MagicMock()
    gw.is_connected = True

    # Account info
    account_info = MagicMock()
    account_info.balance = 10_000.0
    account_info.equity = 10_000.0
    account_info.leverage = 100
    account_info.currency = "USD"
    account_info.free_margin = 9_000.0
    account_info.margin_level = 500.0
    gw.get_account_info = AsyncMock(return_value=account_info)

    # Order placement
    gw.place_order = AsyncMock(return_value={
        "order_id": f"BROKER-{uuid4().hex[:8].upper()}",
        "fill_price": 1.1002,
        "status": "filled",
        "filled_quantity": 0.1,
    })

    # Position management
    gw.close_position = AsyncMock(return_value={"status": "closed"})
    gw.get_open_positions = AsyncMock(return_value=[])
    gw.get_positions = AsyncMock(return_value=[])
    gw.get_order = AsyncMock(return_value={"status": "filled"})
    gw.connect = AsyncMock(return_value=True)
    gw.disconnect = AsyncMock()
    gw.get_connected_brokers = MagicMock(return_value=[])

    return gw


# ---------------------------------------------------------------------------
# In-memory EventBus (test double implementing the EventBus interface)
# ---------------------------------------------------------------------------

class InMemoryEventBus(EventBus):
    """In-memory event bus for testing.

    Stores all published events in memory and can replay them.
    """

    def __init__(self):
        self._events: list[dict[str, Any]] = []
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._function_handlers: dict[str, list[Callable]] = defaultdict(list)

    async def publish(self, topic: str, key: str, value: dict[str, Any]) -> None:
        self._events.append({"topic": topic, "key": key, "value": value})
        # Call registered handlers
        for handler in self._handlers.get(topic, []):
            await handler.handle(value)
        for handler in self._function_handlers.get(topic, []):
            await handler(value)

    async def publish_batch(self, topic: str, messages: list[tuple[str, dict[str, Any]]]) -> None:
        for key, value in messages:
            await self.publish(topic, key, value)

    async def close(self) -> None:
        self._events.clear()
        self._handlers.clear()
        self._function_handlers.clear()

    async def health_check(self) -> bool:
        return True

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        self._handlers[topic].append(handler)

    def subscribe_function(self, topic: str, handler: Callable) -> None:
        self._function_handlers[topic].append(handler)

    def clear(self) -> None:
        self._events.clear()

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def count(self, topic: str | None = None) -> int:
        if topic:
            return sum(1 for e in self._events if e["topic"] == topic)
        return len(self._events)


@pytest.fixture
def mock_event_bus():
    """In-memory EventBus test double."""
    return InMemoryEventBus()


# ---------------------------------------------------------------------------
# Mock CacheManager
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_cache():
    """In-memory cache manager for testing."""
    cache = MagicMock()
    cache._store: dict[str, Any] = {}

    async def _get(key: str) -> Any | None:
        return cache._store.get(key)

    async def _set(key: str, value: Any, ttl: int | None = None) -> bool:
        cache._store[key] = value
        return True

    async def _delete(key: str) -> bool:
        return cache._store.pop(key, None) is not None

    async def _health_check() -> bool:
        return True

    async def _close():
        cache._store.clear()

    cache.get = AsyncMock(side_effect=_get)
    cache.set = AsyncMock(side_effect=_set)
    cache.delete = AsyncMock(side_effect=_delete)
    cache.health_check = AsyncMock(side_effect=_health_check)
    cache.close = AsyncMock(side_effect=_close)
    cache.initialize = AsyncMock()

    return cache


# ---------------------------------------------------------------------------
# Mock StrategyEngine
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_strategy_engine():
    """Mock StrategyEngine for execution tests."""
    engine = MagicMock()
    engine.get_strategy = MagicMock(return_value=None)
    return engine


# ---------------------------------------------------------------------------
# Mock BrokerGateway with BrokerPosition support
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_broker_gateway_with_positions():
    """Mock BrokerGateway with BrokerPosition support for reconciliation tests."""
    from forex_trading.broker.gateway import AccountInfo, BrokerPosition, BrokerType

    gw = MagicMock()
    gw.is_connected = True

    account_info = AccountInfo(
        account_id="test-account",
        broker=BrokerType.MT5,
        balance=10_000.0,
        equity=10_000.0,
        margin=0.0,
        free_margin=10_000.0,
        margin_level=500.0,
        unrealized_pnl=0.0,
        currency="USD",
        leverage=100,
    )
    gw.get_account_info = AsyncMock(return_value=account_info)

    # Returns list of BrokerPosition objects
    gw.get_positions = AsyncMock(return_value=[])
    gw.get_open_positions = AsyncMock(return_value=[])
    gw.place_order = AsyncMock(return_value={
        "order_id": f"BROKER-{uuid4().hex[:8].upper()}",
        "fill_price": 1.1002,
        "status": "filled",
    })
    gw.close_position = AsyncMock(return_value={"status": "closed"})
    gw.connect = AsyncMock(return_value=True)
    gw.disconnect = AsyncMock()
    gw.get_connected_brokers = MagicMock(return_value=[])
    gw.get_order = AsyncMock(return_value={"status": "filled"})

    return gw


# ---------------------------------------------------------------------------
# DI Container fixture for testing
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_container(db_session, mock_broker_gateway, mock_event_bus, mock_cache):
    """Create a Container with all services wired for testing."""
    from forex_trading.shared.di import Container
    from forex_trading.shared.database.engine import DatabaseEngine
    from forex_trading.shared.database.uow import UnitOfWorkFactory

    container = Container()

    # Wire core infrastructure with mocks
    container.db = DatabaseEngine("sqlite+aiosqlite://", echo=False)
    container.event_bus = mock_event_bus
    container.cache = mock_cache

    # Session factory from our test session
    def _session_factory():
        return db_session

    container.uow_factory = UnitOfWorkFactory(_session_factory)
    container.broker_gateway = mock_broker_gateway

    # Market data service (mock)
    from forex_trading.market_data.services.market_data_service import MarketDataService
    container.market_data = MarketDataService(
        cache_manager=mock_cache,
        broker_gateway=mock_broker_gateway,
    )

    # Strategy engine (mock)
    from forex_trading.strategy.engine import StrategyEngine
    container.strategy_engine = StrategyEngine()

    # Risk engine wired to real code with mock uow
    from forex_trading.risk.engine import RiskEngine, RiskLimits
    container.risk_engine = RiskEngine(
        limits=RiskLimits(
            max_position_size_pct=2.0,
            max_total_exposure_pct=20.0,
            max_positions=10,
            daily_drawdown_limit_pct=3.0,
            max_drawdown_limit_pct=15.0,
            max_consecutive_losses=5,
            cooldown_minutes=60,
            max_daily_trades=50,
        ),
        uow_factory=container.uow_factory,
    )

    # Position sizer
    from forex_trading.execution.services.position_sizer import PositionSizer
    container.position_sizer = PositionSizer()

    # Position manager
    from forex_trading.execution.position_manager import PositionManager
    container.position_manager = PositionManager(
        uow_factory=container.uow_factory,
        event_bus=mock_event_bus,
        broker_gateway=mock_broker_gateway,
    )

    # Execution engine
    from forex_trading.execution.engine import ExecutionEngine
    container.execution_engine = ExecutionEngine(
        risk_engine=container.risk_engine,
        broker_gateway=mock_broker_gateway,
        strategy_engine=container.strategy_engine,
        position_manager=container.position_manager,
        uow_factory=container.uow_factory,
        event_bus=mock_event_bus,
        allow_off_hours=True,
    )

    # Feature service
    from forex_trading.ai.services.feature_service import FeatureService
    container.feature_service = FeatureService(cache=mock_cache)

    # AI orchestrator
    from forex_trading.ai.orchestrator import AIOrchestrator
    container.ai_orchestrator = AIOrchestrator(
        uow_factory=container.uow_factory,
        cache=mock_cache,
    )

    # Auto trader
    from forex_trading.execution.services.auto_trader import AutoTrader
    container.auto_trader = AutoTrader(
        market_data=container.market_data,
        broker_gateway=mock_broker_gateway,
        risk_engine=container.risk_engine,
        strategy_engine=container.strategy_engine,
        execution_engine=container.execution_engine,
        position_manager=container.position_manager,
        position_sizer=container.position_sizer,
        poll_interval_seconds=3600,
        symbols=["EURUSD"],
    )

    return container


# ---------------------------------------------------------------------------
# Risk Engine fixture (standalone, no DB)
# ---------------------------------------------------------------------------

@pytest.fixture
def risk_limits():
    """Standard test risk limits."""
    from forex_trading.risk.engine import RiskLimits
    return RiskLimits(
        max_position_size_pct=2.0,
        max_total_exposure_pct=20.0,
        max_positions=10,
        daily_drawdown_limit_pct=3.0,
        weekly_drawdown_limit_pct=5.0,
        monthly_drawdown_limit_pct=10.0,
        max_drawdown_limit_pct=15.0,
        max_consecutive_losses=5,
        cooldown_minutes=60,
        max_daily_trades=50,
    )


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
            "timestamp": (ts + timedelta(hours=i)).isoformat(),
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
# MarketContext fixture
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
            "entry_price": 1.1000,
        },
    )


# ---------------------------------------------------------------------------
# TradeSignal fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def trade_signal():
    """Create a basic TradeSignal for testing."""
    from forex_trading.ai.agents.base import SignalDirection
    from forex_trading.strategy.engine import TradeSignal, StrategyParameters, StrategyType
    return TradeSignal(
        strategy=StrategyType.TREND_FOLLOWING,
        symbol="EURUSD",
        direction=SignalDirection.LONG,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        confidence=0.75,
        parameters=StrategyParameters(
            stop_loss_pips=50.0,
            take_profit_pips=100.0,
            max_holding_time_minutes=240,
            metadata={
                "atr": 0.0010,
                "lots": 0.1,
                "current_spread_pips": 1.2,
            },
        ),
    )


# ---------------------------------------------------------------------------
# Sample UUID / symbol fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_uuid() -> UUID:
    return uuid4()


@pytest.fixture
def sample_symbol() -> str:
    return "EURUSD"


@pytest.fixture
def broker_account_id() -> UUID:
    return uuid4()
