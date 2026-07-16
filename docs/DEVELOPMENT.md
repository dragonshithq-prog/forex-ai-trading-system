# Development Guide — Forex AI Trading System

> **Version**: 0.1.0  
> **Last updated**: 2026-07-14

---

## Table of Contents

1. [Setting Up Development Environment](#1-setting-up-development-environment)
2. [Code Style and Conventions](#2-code-style-and-conventions)
3. [Testing Guidelines](#3-testing-guidelines)
4. [Adding a New AI Agent](#4-adding-a-new-ai-agent)
5. [Adding a New Broker Plugin](#5-adding-a-new-broker-plugin)
6. [Database Migrations](#6-database-migrations)
7. [CI/CD Pipeline](#7-cicd-pipeline)

---

## 1. Setting Up Development Environment

### 1.1 Prerequisites

```bash
# Python 3.12+
python --version  # Should be ≥ 3.12

# Node.js 20+
node --version    # Should be ≥ 20

# Docker 24+
docker --version  # Should be ≥ 24

# Git
git --version
```

### 1.2 Clone and Setup

```bash
# Clone repository
git clone https://github.com/your-org/forex-trading-system.git
cd forex-trading-system

# Create virtual environment
cd backend
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install with all extras
pip install -e ".[all]"

# Create .env from template
cp ../.env.example ../.env
# Edit .env with your settings
```

### 1.3 Start Infrastructure Services

```bash
# From project root
docker compose -f docker/docker-compose.yml up -d postgres redis kafka

# Verify they're healthy
docker compose -f docker/docker-compose.yml ps
```

### 1.4 Initialize Database

```bash
# Run migrations
cd backend
alembic upgrade head

# (Optional) Seed with sample data
make seed
```

### 1.5 Run Development Server

```bash
# Backend with hot-reload
uvicorn forex_trading.main:app --reload --host 0.0.0.0 --port 8000

# Access: http://localhost:8000
# API docs: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

### 1.6 Setup Frontend (Optional)

```bash
cd frontend
npm install
npm run dev
# Access: http://localhost:3000
```

### 1.7 Verify Setup

```bash
# Backend health check
curl http://localhost:8000/health
# → {"status":"healthy","version":"0.1.0"}

# Run tests
pytest tests/unit -q
# → All tests pass

# Register a test user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@test.com","username":"dev","password":"DevP@ss123!"}'
# → 201 Created with tokens
```

---

## 2. Code Style and Conventions

### 2.1 Python Style Guide

The project follows [PEP 8](https://peps.python.org/pep-0008/) with the following specific rules:

**Line length:** 100 characters

**Naming conventions:**
| Element | Convention | Example |
|---------|-----------|---------|
| Modules | `snake_case` | `market_data_service.py` |
| Classes | `PascalCase` | `RiskEngine` |
| Functions | `snake_case` | `assess_trade()` |
| Variables | `snake_case` | `max_position_size` |
| Constants | `UPPER_CASE` | `MAX_RETRY_ATTEMPTS` |
| Private | `_leading_underscore` | `_validate_order()` |
| Protocols/ABCs | `PascalCase` | `BaseAgent`, `BrokerPlugin` |

**Imports order** (enforced by ruff):
1. Standard library (`os`, `datetime`, etc.)
2. Third-party (`fastapi`, `sqlalchemy`, etc.)
3. First-party (`forex_trading.*`)

### 2.2 Code Formatting

```bash
# Format code
make format        # ruff format

# Check formatting
make lint          # ruff check + ruff format --check + mypy

# Auto-fix lint issues
make lint-fix      # ruff check --fix
```

Configuration is in `backend/pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
select = ["E", "W", "F", "I", "N", "UP", "B", "A", "C4", "SIM", "TCH", "ARG", "PTH"]
ignore = ["E501"]  # Line length checked by formatter

[tool.mypy]
python_version = "3.12"
warn_return_any = true
disallow_untyped_defs = true
plugins = ["pydantic.mypy"]
```

### 2.3 Type Annotations

All code must have type annotations (enforced by mypy):

```python
# ✅ Correct
def calculate_position_size(
    balance: float,
    risk_pct: float,
    stop_loss_pips: float,
) -> float:
    return (balance * risk_pct / 100) / (stop_loss_pips * 10)


# ❌ Incorrect — missing types
def calculate_position_size(balance, risk_pct, stop_loss_pips):
    return (balance * risk_pct / 100) / (stop_loss_pips * 10)
```

### 2.4 Documentation Strings

Use Google-style docstrings:

```python
def assess_trade(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
) -> RiskAssessment:
    """Evaluate whether a trade is within risk limits.
    
    Performs pre-trade checks including position size, exposure,
    drawdown, and correlation validation.
    
    Parameters
    ----------
    symbol : str
        The forex pair to trade (e.g., "EURUSD").
    side : str
        Trade direction — "buy" or "sell".
    quantity : float
        Requested position size in lots.
    price : float
        Expected entry price.
        
    Returns
    -------
    RiskAssessment
        Assessment result with approval status and any warnings.
        
    Raises
    ------
    ValueError
        If symbol or side is invalid.
    """
```

### 2.5 Project Architecture Conventions

**Clean Architecture layers within each module:**
```
module/
├── domain/       # Entities, value objects, aggregates, domain events
├── services/     # Application services / use cases
├── api/          # API endpoints (if the module exposes them)
├── middleware/   # Module-specific middleware
└── engine.py     # Main engine / orchestrator (if applicable)
```

**Dependency injection:**
- All services receive dependencies through constructor injection
- The `Container` class in `shared/di.py` wires everything together
- Never use global state or singletons (except for the DI container itself)

**Module isolation:**
- A module should only import from its own `domain/` or from `shared/`
- Cross-module communication happens through the DI container or event bus
- Never import directly from another module's internals

---

## 3. Testing Guidelines

### 3.1 Test Structure

Tests mirror the source structure:

```
tests/
├── conftest.py              # Shared fixtures
├── factories.py             # Test data factories
├── unit/                    # Unit tests (fast, no external dependencies)
│   ├── test_risk_engine.py
│   ├── test_ai_orchestrator.py
│   └── ...
├── integration/             # Integration tests (mocked DB/services)
│   ├── test_api_auth.py
│   └── ...
├── security/                # Security tests
│   ├── test_jwt.py
│   ├── test_rate_limit.py
│   └── ...
├── e2e/                     # End-to-end tests (full pipeline, mocked broker)
│   └── test_trade_lifecycle.py
└── load/                    # Performance tests
    └── test_execution_performance.py
```

### 3.2 Running Tests

```bash
# All tests with coverage
make test

# Specific categories
make test-unit            # Unit tests only
make test-integration     # Integration tests only
make test-security        # Security tests
make test-e2e             # End-to-end tests
make test-load            # Performance tests

# Using pytest directly
cd backend
pytest tests/unit/ -v -k "test_position_size"  # Filter by name
pytest tests/ -m integration                     # By marker
pytest -x --pdb                                   # Debug on failure
```

### 3.3 Coverage Requirements

The project maintains **≥ 80% code coverage**:

```bash
pytest --cov=src/forex_trading \
  --cov-report=html \
  --cov-report=term-missing \
  --cov-fail-under=80
```

Coverage reports are generated to `backend/htmlcov/`.

### 3.4 Writing Tests

**Use the provided fixtures** in `conftest.py`:

```python
# tests/conftest.py provides:
# - test_db: Async SQLAlchemy session
# - test_client: FastAPI test client
# - test_user: Pre-created test user
# - test_container: DI container with mocked services

async def test_assess_trade_approves_valid_trade(
    risk_engine: RiskEngine,
    test_user: User,
) -> None:
    """A valid trade should be approved."""
    assessment = await risk_engine.assess_trade(
        symbol="EURUSD",
        side="buy",
        quantity=0.1,
        user_id=test_user.id,
    )
    assert assessment.is_approved
    assert len(assessment.violations) == 0
```

**Use test factories** for creating domain objects:

```python
# tests/factories.py provides factory functions
from tests.factories import (
    create_user,
    create_order,
    create_position,
    create_risk_assessment,
)

def test_order_lifecycle(test_db: AsyncSession) -> None:
    user = await create_user(test_db, role="trader")
    order = await create_order(test_db, user_id=user.id, symbol="EURUSD")
    assert order.status == "pending"
```

**Use markers appropriately:**

```python
import pytest

@pytest.mark.unit
def test_risk_limits_validation():
    ...

@pytest.mark.integration
async def test_order_creation_api(test_client):
    ...

@pytest.mark.security
def test_jwt_token_type_binding():
    ...

@pytest.mark.slow
def test_performance_under_load():
    ...
```

### 3.5 Mocking Strategy

- **External services** (brokers, market data): Use `AsyncMock` or the built-in `PaperTradingPlugin`
- **Database**: Use the test database (`sqlite+aiosqlite` in-memory)
- **Redis**: Use fakeredis for unit tests
- **Kafka**: Use `AsyncMock` for producers/consumers
- **HTTP calls**: Use `httpx.AsyncClient` with mock transport

```python
from unittest.mock import AsyncMock, patch

async def test_execution_with_broker_failure(
    execution_engine: ExecutionEngine,
) -> None:
    with patch.object(
        execution_engine.broker_gateway,
        "place_order",
        AsyncMock(side_effect=ConnectionError("Broker unavailable")),
    ):
        result = await execution_engine.process_signal(test_signal)
        assert result.status == "failed"
        assert "Broker unavailable" in result.error_message
```

---

## 4. Adding a New AI Agent

### 4.1 Overview

AI agents are specialized modules that analyze market data and produce trading signals. Each agent runs independently and votes on market direction.

### 4.2 Step-by-Step

#### Step 1: Create the Agent Class

Create a new file in `backend/src/forex_trading/ai/agents/`:

```python
# backend/src/forex_trading/ai/agents/my_agent.py
"""My Custom AI Agent — analyzes [describe what it does]."""

from __future__ import annotations

from forex_trading.ai.agents.base import (
    AgentSignal,
    BaseAgent,
    MarketContext,
    MarketRegime,
    SignalDirection,
)


class MyAgent(BaseAgent):
    """Custom agent that [describe purpose]."""

    agent_id = "my_agent"
    display_name = "My Custom Agent"
    description = "Analyzes [description]"

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Produce a trading signal based on [method]."""
        # 1. Extract relevant data from context
        candles = context.candles
        regime = context.regime

        # 2. Implement your analysis logic
        direction = SignalDirection.LONG
        confidence = 0.75
        reasoning = "Detected [pattern] with [metric] confirmation"

        # 3. Return the signal
        return AgentSignal(
            agent_id=self.agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            supporting_data={
                "key_metric": 42.0,
                "threshold": 30.0,
                "signal_type": "custom",
            },
        )

    def get_weight(self, regime: MarketRegime) -> float:
        """Return agent weight for the current market regime.
        
        Higher weight = more influence on the final decision.
        Should be between 0.0 and 1.0.
        """
        weights = {
            MarketRegime.TRENDING_UP: 0.70,
            MarketRegime.TRENDING_DOWN: 0.70,
            MarketRegime.RANGING: 0.50,
            MarketRegime.VOLATILE: 0.60,
            MarketRegime.LOW_VOLATILITY: 0.40,
        }
        return weights.get(regime, 0.50)

    def required_data(self) -> list[str]:
        """List data requirements for this agent."""
        return ["candles_H1", "candles_D1"]
```

#### Step 2: Add to the Agent Registry

Edit `backend/src/forex_trading/ai/orchestrator.py`:

```python
# Import the new agent
from forex_trading.ai.agents.my_agent import MyAgent

class AIOrchestrator:
    def _initialize_agents(self) -> None:
        """Register all available agents."""
        self._agents: dict[str, BaseAgent] = {
            "market_structure": MarketStructureAgent(),
            "trend_ai": TrendAgent(),
            "liquidity_ai": LiquidityAgent(),
            "volatility_ai": VolatilityAgent(),
            "sentiment_ai": SentimentAgent(),
            "smart_money_ai": SmartMoneyAgent(),
            "risk_ai": RiskAgent(),
            "entry_ai": EntryAgent(),
            "exit_ai": ExitAgent(),
            "my_agent": MyAgent(),  # ← Add here
        }
```

#### Step 3: Add Agent Performance Tracking (if needed)

If your agent needs performance-based weight adjustment, add it to `_AGENT_ID_TO_DB_TYPE`:

```python
# In orchestrator.py
_AGENT_ID_TO_DB_TYPE: dict[str, AgentType] = {
    "market_structure": AgentType.STRUCTURE,
    "trend_ai": AgentType.TREND,
    "sentiment_ai": AgentType.SENTIMENT,
    "liquidity_ai": AgentType.LIQUIDITY,
    "volatility_ai": AgentType.VOLATILITY,
    "my_agent": AgentType.CUSTOM,  # ← Add type mapping
    # Note: Add AgentType.CUSTOM to the AgentType enum if it doesn't exist
}
```

#### Step 4: Write Tests

```python
# tests/test_ai/test_my_agent.py
import pytest
from forex_trading.ai.agents.my_agent import MyAgent
from forex_trading.ai.agents.base import MarketRegime, SignalDirection

@pytest.mark.unit
async def test_my_agent_analyzes_trending_market():
    agent = MyAgent()
    context = MarketContext(
        symbol="EURUSD",
        candles={},
        regime=MarketRegime.TRENDING_UP,
        metadata={},
    )
    signal = await agent.analyze(context)
    assert signal.agent_id == "my_agent"
    assert signal.direction in (
        SignalDirection.LONG,
        SignalDirection.SHORT,
        SignalDirection.NEUTRAL,
    )
    assert 0.0 <= signal.confidence <= 1.0
    assert signal.reasoning  # Must have explanation

@pytest.mark.unit
def test_my_agent_weight_in_trending():
    agent = MyAgent()
    weight = agent.get_weight(MarketRegime.TRENDING_UP)
    assert 0.0 <= weight <= 1.0

@pytest.mark.unit
def test_my_agent_required_data():
    agent = MyAgent()
    data = agent.required_data()
    assert isinstance(data, list)
    assert len(data) > 0
```

### 4.3 Agent Interface Reference

```python
class BaseAgent(ABC):
    @abstractmethod
    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Analyze market data and produce a signal.
        
        Parameters
        ----------
        context : MarketContext
            Current market data including candles, regime, and metadata.
            
        Returns
        -------
        AgentSignal
            The agent's trading signal with direction, confidence, and reasoning.
        """
        ...

    @abstractmethod
    def get_weight(self, regime: MarketRegime) -> float:
        """Return agent weight for the given market regime.
        
        Higher weight = more influence on consensus.
        """
        ...

    @abstractmethod
    def required_data(self) -> list[str]:
        """Return list of data keys this agent needs."""
        ...
```

---

## 5. Adding a New Broker Plugin

### 5.1 Overview

Broker plugins provide a unified interface to different forex brokers. The plugin system allows adding new brokers without modifying existing code.

### 5.2 Step-by-Step

#### Step 1: Create the Plugin Class

Create a new file in `backend/src/forex_trading/broker/plugins/`:

```python
# backend/src/forex_trading/broker/plugins/my_broker.py
"""MyBroker plugin implementation."""

from __future__ import annotations

from typing import Any

from forex_trading.broker.domain import (
    AccountInfo,
    BrokerCredentials,
    Order,
    OrderResult,
    OrderStatus,
    Position,
)
from forex_trading.broker.plugins.base import BrokerPlugin


class MyBrokerPlugin(BrokerPlugin):
    """Plugin for MyBroker forex broker."""

    broker_name = "MyBroker"
    broker_type = "my_broker"

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._account_id: str | None = None
        self._base_url: str | None = None
        self._session: httpx.AsyncClient | None = None

    async def connect(self, credentials: BrokerCredentials) -> bool:
        """Connect to MyBroker API."""
        self._api_key = credentials.api_key
        self._account_id = credentials.account_id
        self._base_url = credentials.environment_url  # or compute from env name
        self._session = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        
        # Test connection
        try:
            response = await self._session.get("/v1/accounts")
            response.raise_for_status()
            return True
        except Exception:
            return False

    async def disconnect(self) -> None:
        """Disconnect from MyBroker."""
        if self._session:
            await self._session.aclose()
            self._session = None

    async def get_account_info(self) -> AccountInfo:
        """Get account balance and status."""
        response = await self._get("/v1/accounts/" + self._account_id)
        data = response.json()
        return AccountInfo(
            account_id=self._account_id,
            balance=float(data["balance"]),
            equity=float(data["equity"]),
            margin_used=float(data["margin_used"]),
            margin_free=float(data["margin_free"]),
            leverage=data["leverage"],
            currency=data["currency"],
        )

    async def place_order(self, order: Order) -> OrderResult:
        """Place an order with MyBroker."""
        payload = {
            "instrument": order.symbol,
            "units": order.quantity * (1 if order.side == "buy" else -1),
            "type": "MARKET" if order.order_type == "market" else "LIMIT",
            "price": order.price,
            "stopLoss": order.stop_loss,
            "takeProfit": order.take_profit,
        }
        response = await self._post("/v1/orders", json=payload)
        data = response.json()
        return OrderResult(
            order_id=data["id"],
            broker_order_id=data["id"],
            status=OrderStatus.FILLED if data["filled"] else OrderStatus.PENDING,
            filled_price=float(data.get("fillPrice", 0)),
            filled_quantity=float(data.get("filledUnits", 0)),
        )

    async def close_position(self, position_id: str, **kwargs) -> OrderResult:
        """Close an open position."""
        response = await self._put(f"/v1/positions/{position_id}/close")
        data = response.json()
        return OrderResult(
            order_id=data["id"],
            broker_order_id=data["id"],
            status=OrderStatus.CLOSED,
            filled_price=float(data["price"]),
        )

    async def get_open_positions(self) -> list[Position]:
        """Get all open positions."""
        response = await self._get(f"/v1/accounts/{self._account_id}/positions")
        return [self._parse_position(p) for p in response.json()["positions"]]

    async def get_account_info(self) -> AccountInfo:
        ...

    async def subscribe_prices(
        self,
        symbols: list[str],
        callback: Callable,
    ) -> None:
        """Subscribe to real-time price updates (WebSocket)."""
        # Implement WebSocket connection
        ...

    def _parse_position(self, data: dict) -> Position:
        return Position(
            position_id=data["id"],
            symbol=data["instrument"],
            side="buy" if float(data["units"]) > 0 else "sell",
            size=abs(float(data["units"])),
            entry_price=float(data["entryPrice"]),
            current_price=float(data["currentPrice"]),
            unrealized_pnl=float(data["unrealizedPL"]),
            stop_loss=data.get("stopLoss"),
            take_profit=data.get("takeProfit"),
        )

    async def _get(self, path: str) -> httpx.Response:
        if not self._session:
            raise ConnectionError("Not connected")
        response = await self._session.get(path)
        response.raise_for_status()
        return response

    async def _post(self, path: str, **kwargs) -> httpx.Response:
        if not self._session:
            raise ConnectionError("Not connected")
        response = await self._session.post(path, **kwargs)
        response.raise_for_status()
        return response
```

#### Step 2: Register the Plugin

Edit the broker registry in `backend/src/forex_trading/broker/gateway.py`:

```python
from forex_trading.broker.plugins.my_broker import MyBrokerPlugin

class BrokerGateway:
    def __init__(self) -> None:
        self._plugin_registry: dict[str, type[BrokerPlugin]] = {
            "oanda": OANDAPlugin,
            "mt4": MT4Plugin,
            "mt5": MT5Plugin,
            "paper": PaperTradingPlugin,
            "my_broker": MyBrokerPlugin,  # ← Register here
        }
```

#### Step 3: Add to Broker API

The broker account creation endpoint needs to accept the new broker type:

```python
# In api/schemas/broker.py
class BrokerAccountCreate(BaseModel):
    broker_name: str  # "oanda", "mt4", "mt5", "paper", "my_broker"
    ...
```

#### Step 4: Write Tests

```python
# tests/test_broker/test_my_broker_plugin.py
import pytest
from unittest.mock import AsyncMock, patch
from forex_trading.broker.plugins.my_broker import MyBrokerPlugin
from forex_trading.broker.domain import BrokerCredentials, Order

@pytest.mark.unit
async def test_my_broker_connect():
    plugin = MyBrokerPlugin()
    credentials = BrokerCredentials(
        api_key="test-key",
        account_id="test-account",
        environment="practice",
    )
    with patch.object(plugin, "_get", AsyncMock(return_value=AsyncMock(status_code=200))):
        result = await plugin.connect(credentials)
        assert result is True

@pytest.mark.unit
async def test_my_broker_place_order():
    plugin = MyBrokerPlugin()
    # ... test order placement logic
```

### 5.3 Plugin Interface Reference

```python
class BrokerPlugin(ABC):
    """Abstract base for all broker plugins."""

    broker_name: str
    broker_type: str

    @abstractmethod
    async def connect(self, credentials: BrokerCredentials) -> bool:
        """Establish connection to the broker."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the broker."""
        ...

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Retrieve account balance, equity, margin."""
        ...

    @abstractmethod
    async def place_order(self, order: Order) -> OrderResult:
        """Place a new order."""
        ...

    @abstractmethod
    async def close_position(self, position_id: str, **kwargs) -> OrderResult:
        """Close an open position."""
        ...

    @abstractmethod
    async def get_open_positions(self) -> list[Position]:
        """List all open positions."""
        ...

    @abstractmethod
    async def subscribe_prices(
        self,
        symbols: list[str],
        callback: Callable[[dict], None],
    ) -> None:
        """Subscribe to real-time market data."""
        ...
```

---

## 6. Database Migrations

### 6.1 Setting Up Alembic

Alembic is already configured in `backend/alembic.ini` and `backend/alembic/`.

Configuration file: `backend/alembic/env.py`:

```python
from forex_trading.config import get_settings
from forex_trading.shared.database.base import Base

settings = get_settings()

# The migration environment uses the DATABASE_URL from settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
```

### 6.2 Creating a Migration

```bash
# Auto-detect changes from models
cd backend
alembic revision --autogenerate -m "describe_your_changes"
```

This creates a new file in `backend/alembic/versions/`.

**Always review auto-generated migrations** — they may miss some changes or generate incorrect SQL.

```python
# Example migration: backend/alembic/versions/abc123_add_symbol_to_orders.py
"""add symbol index to orders

Revision ID: abc123
Revises: previous_revision
Create Date: 2026-07-14 10:30:00.000000
"""
from alembic import op

revision = "abc123"
down_revision = "previous_revision"


def upgrade() -> None:
    op.create_index("ix_orders_symbol", "orders", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_orders_symbol")
```

### 6.3 Running Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade to specific version
alembic upgrade abc123

# Check current version
alembic current

# View history
alembic history

# Downgrade
alembic downgrade -1
```

### 6.4 Migration Best Practices

1. **Always backward-compatible**: Don't rename or remove columns without a deprecation period
2. **Test on staging first**: Run migrations against a staging database before production
3. **Batch large operations**: Use `op.execute()` with batched UPDATE for large tables:

```python
def upgrade():
    # For large tables, batch the migration
    connection = op.get_bind()
    connection.execute(
        text("""
            UPDATE orders SET status = 'cancelled'
            WHERE status = 'expired' AND created_at < NOW() - INTERVAL '30 days'
        """)
    )
```

4. **Add indexes for new query patterns**: Always include indexes when adding new filter columns
5. **Use server defaults**: Prefer `server_default` over application-level defaults for new columns
6. **Separate data migrations**: Use a separate migration revision for data migrations

---

## 7. CI/CD Pipeline

### 7.1 Pipeline Overview

The CI/CD pipeline is defined in `.github/workflows/`:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  PR Opened      │────▶│  CI Pipeline    │────▶│  Checks Pass    │
│  / Push to      │     │  (ci.yml)       │     │  (mergeable)    │
│  feature/*      │     └─────────────────┘     └─────────────────┘
└─────────────────┘                                    │
                                                        │ (merged to main)
                                                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Push to main   │────▶│  CD Pipeline    │────▶│  Deploy to      │
│  / tag v*       │     │  (cd.yml)       │     │  Staging/Prod   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### 7.2 CI Pipeline (ci.yml)

Runs on every PR and push to `main`:

```yaml
name: CI Pipeline
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: timescale/timescaledb:latest-pg16
        env:
          POSTGRES_DB: forex_trading_test
          POSTGRES_USER: forex
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          cd backend
          pip install -e ".[dev]"

      - name: Lint
        run: make lint

      - name: Type check
        run: cd backend && mypy src/

      - name: Run tests
        run: make test
        env:
          DATABASE_URL: postgresql+asyncpg://forex:test@localhost:5432/forex_trading_test
          REDIS_URL: redis://localhost:6379/0
          ENVIRONMENT: testing

      - name: Upload coverage
        uses: codecov/codecov-action@v4

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker images
        run: make build-backend

      - name: Scan for vulnerabilities
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ghcr.io/${{ github.repository }}/backend:ci
          format: sarif
          output: trivy-results.sarif
```

### 7.3 CD Pipeline (cd.yml)

Runs on push to `main` or tag:

```yaml
name: CD Pipeline
on:
  push:
    branches: [main]
    tags: ["v*"]

jobs:
  deploy-staging:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Login to ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -f docker/Dockerfile.backend \
            -t $ECR_REGISTRY/forex-trading/backend:$IMAGE_TAG .
          docker push $ECR_REGISTRY/forex-trading/backend:$IMAGE_TAG

      - name: Deploy to staging
        run: |
          ./scripts/deploy.sh staging ${{ github.sha }}

      - name: Smoke test
        run: |
          curl -f https://staging-api.yourdomain.com/health
          echo "Smoke test passed"

  deploy-production:
    needs: deploy-staging
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy to production
        run: |
          ./scripts/deploy.sh production ${{ github.ref_name }}

      - name: Monitor deployment
        run: |
          # Wait for rollout
          kubectl -n forex-trading rollout status deployment/backend --timeout=300s
          echo "Deployment successful"
```

### 7.4 Makefile Targets

| Target | Description | CI/CD Step |
|--------|-------------|------------|
| `make test` | Run all tests with coverage | ✅ |
| `make lint` | Run ruff + mypy | ✅ |
| `make format` | Format code with ruff | ✅ |
| `make build` | Build Docker images | ✅ |
| `make deploy` | Deploy to environment | ✅ |
| `make rollback` | Rollback deployment | ✅ |
| `make backup` | Backup database | ✅ |
| `make migrate` | Run DB migrations | ✅ |

### 7.5 Pre-commit Hooks

Install pre-commit hooks for local development:

```bash
make precommit-install
```

This runs on every commit:
- `ruff check` — lint Python files
- `ruff format` — check formatting
- `mypy` — type checking
- `trailing-whitespace` — clean up whitespace
- `end-of-file-fixer` — ensure newline at end of file
- `check-yaml` — validate YAML files
- `check-json` — validate JSON files

### 7.6 Release Process

```bash
# 1. Create a release branch
git checkout -b release/v0.2.0

# 2. Update version in pyproject.toml and config.py
#    (bump APP_VERSION to "0.2.0")

# 3. Update CHANGELOG.md

# 4. Commit and push
git add . && git commit -m "chore: bump version to 0.2.0"
git push origin release/v0.2.0

# 5. Create PR and merge to main

# 6. Tag the release
git tag v0.2.0
git push origin v0.2.0

# 7. CI/CD pipeline builds, tests, and deploys to production
```
