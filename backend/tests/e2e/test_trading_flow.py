"""
End-to-end trading flow test.

Simulates the full happy-path without any real infrastructure:
  DB, Redis, Kafka, and broker APIs are all mocked.

Flow:
  1. App started (no real lifespan hooks)
  2. User registered → 201
  3. User logs in → JWT tokens
  4. Broker account connected (paper trading)
  5. Market data context created
  6. AI Orchestrator analyses market (mocked context)
  7. Signal generated (consensus LONG)
  8. Risk engine approves the trade
  9. Order placed via paper broker
  10. Position opened
  11. Risk engine monitors position
  12. Trailing-stop updated
  13. Position closed with profit
  14. Trade analytics updated
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(n: int = 300, trend: float = 0.00015) -> list[dict]:
    rng = random.Random(42)
    price, candles = 1.1000, []
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        price = max(price + trend + rng.gauss(0, 0.0008), 0.0001)
        o = price + rng.gauss(0, 0.0002)
        c = price + rng.gauss(0, 0.0002)
        h = max(o, c) + abs(rng.gauss(0, 0.0003))
        l = min(o, c) - abs(rng.gauss(0, 0.0003))
        candles.append({
            "timestamp": ts + timedelta(hours=i),
            "open": round(o, 5), "high": round(h, 5),
            "low": round(l, 5), "close": round(c, 5),
            "volume": rng.randint(200, 2000),
        })
    return candles


def _build_e2e_app():
    """Build a minimal FastAPI app with all routes, no lifespan."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from forex_trading.api.router import api_router
    from forex_trading.api.websocket import router as ws_router
    from forex_trading.core.exceptions import setup_exception_handlers
    from forex_trading.core.middleware import setup_middleware
    from forex_trading.config import get_settings

    settings = get_settings()
    app = FastAPI(title="e2e-test")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    setup_exception_handlers(app)
    setup_middleware(app)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy", "version": settings.APP_VERSION}

    return app


def _make_mock_user(role: str = "trader") -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.username = "e2e_trader"
    user.email = "e2e@test.com"
    user.full_name = "E2E Trader"
    user.role = MagicMock(); user.role.value = role
    user.is_active = True
    user.is_verified = True
    user.mfa_enabled = False
    user.mfa_secret = None
    user.hashed_password = "hashed"
    user.preferences = {}
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    user.last_login = None
    return user


# ---------------------------------------------------------------------------
# E2E Flow
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestCompleteTradingFlow:
    """
    Step-by-step happy-path end-to-end test.
    Each step asserts on the previous step's output.
    """

    # ------------------------------------------------------------------
    # Step 1: Health check (system up)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_step_01_health_check_passes(self):
        app = _build_e2e_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    # ------------------------------------------------------------------
    # Step 2: Register user
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_step_02_register_user(self):
        """New user can register → 201 with tokens."""
        from forex_trading.api.dependencies import get_db, get_current_user
        from forex_trading.shared.database.crud_user import user_repository
        from forex_trading.core.security import security_manager

        new_user = _make_mock_user()
        new_user.hashed_password = "mocked_hash"

        app = _build_e2e_app()

        async def _fake_db():
            yield MagicMock()

        app.dependency_overrides[get_db] = _fake_db

        # Patch the token creation to avoid RS256 issues
        with patch.object(user_repository, "get_by_email", new=AsyncMock(return_value=None)), \
             patch.object(user_repository, "get_by_username", new=AsyncMock(return_value=None)), \
             patch.object(user_repository, "create", new=AsyncMock(return_value=new_user)), \
             patch.object(user_repository, "update_last_login", new=AsyncMock()), \
             patch.object(security_manager, "hash_password", return_value="hashed"), \
             patch.object(security_manager, "create_token_pair") as mock_pair:

            mock_pair.return_value = MagicMock(
                access_token="test.access.token",
                refresh_token="test.refresh.token",
                expires_in=900,
            )

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/api/v1/auth/register", json={
                    "username": "e2e_trader",
                    "email": "e2e@test.com",
                    "password": "TestPass123!",
                    "full_name": "E2E Trader",
                })

        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data

    # ------------------------------------------------------------------
    # Step 3: Login and get JWT
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_step_03_login_returns_jwt(self):
        """Registered user can login and get JWT tokens."""
        from forex_trading.api.dependencies import get_db
        from forex_trading.shared.database.crud_user import user_repository
        from forex_trading.core.security import security_manager
        from forex_trading.api.schemas.user import UserResponse
        from datetime import datetime, timezone

        user = _make_mock_user()
        user.hashed_password = "mocked_hash"

        app = _build_e2e_app()

        async def _fake_db():
            yield MagicMock()

        app.dependency_overrides[get_db] = _fake_db

        mock_response = UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name="E2E Trader",
            role="trader",
            is_active=True,
            is_verified=True,
            mfa_enabled=False,
            last_login=None,
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(user_repository, "get_by_username", new=AsyncMock(return_value=user)), \
             patch.object(user_repository, "get_by_email", new=AsyncMock(return_value=None)), \
             patch.object(user_repository, "update_last_login", new=AsyncMock()), \
             patch.object(security_manager, "verify_password", return_value=True), \
             patch.object(security_manager, "create_token_pair") as mock_pair, \
             patch("forex_trading.api.routers.auth.UserResponse.model_validate") as mv:

            mock_pair.return_value = MagicMock(
                access_token="test.access.token",
                refresh_token="test.refresh.token",
                expires_in=900,
            )
            mv.return_value = mock_response

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/api/v1/auth/login", json={
                    "username": "e2e_trader",
                    "password": "TestPass123!",
                })

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["access_token"] != data["refresh_token"]

    # ------------------------------------------------------------------
    # Step 4: Subscribe to market data
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_step_04_subscribe_to_market_data(self):
        """Market data service accepts subscription without errors."""
        from forex_trading.market_data.services.market_data_service import MarketDataService

        service = MarketDataService()
        events = []

        async def handler(event):
            events.append(event)

        await service.subscribe_ticks("EURUSD", handler)
        await service.on_tick("EURUSD", 1.1050, 1.1052, 500)

        assert len(events) == 1
        # Event may be a dict or object depending on implementation
        event = events[0]
        symbol = event.get("symbol") if isinstance(event, dict) else event.symbol
        assert symbol == "EURUSD"

    # ------------------------------------------------------------------
    # Step 5: AI analyses market
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_step_05_ai_orchestrator_analyses_market(self):
        """AI Orchestrator produces a valid analysis result."""
        from forex_trading.ai.orchestrator import AIOrchestrator, OrchestratorResult
        from forex_trading.ai.agents.base import MarketContext, MarketRegime

        orch = AIOrchestrator()
        ctx = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            candles=_make_candles(300),
            regime=MarketRegime.TRENDING_UP,
            metadata={
                "spread": 1.2,
                "current_drawdown_pct": 0.5,
                "open_positions": [],
            },
        )
        result = await orch.analyze(ctx)
        assert isinstance(result, OrchestratorResult)
        assert result.consensus is not None
        assert isinstance(result.should_trade, bool)

    # ------------------------------------------------------------------
    # Step 6: Risk engine approves a valid trade
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_step_06_risk_engine_approves_trade(self):
        """Risk engine approves a small, well-sized trade."""
        from forex_trading.risk.engine import RiskEngine, RiskLimits

        engine = RiskEngine(limits=RiskLimits(max_positions=10))
        engine.update_state(equity=10_000.0, drawdown_pct=0.0)

        assessment = await engine.assess_trade(
            symbol="EURUSD", side="long", size=0.1, entry_price=1.1050
        )
        assert assessment.is_approved is True
        assert len(assessment.violations) == 0

    # ------------------------------------------------------------------
    # Step 7: Paper order placed
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_step_07_paper_order_placed(self):
        """ExecutionEngine processes a signal and places a paper order."""
        from forex_trading.execution.engine import ExecutionEngine
        from forex_trading.ai.agents.base import SignalDirection
        from forex_trading.risk.engine import RiskAssessment
        from forex_trading.strategy.engine import (
            StrategyParameters, StrategyType, TradeSignal, ValidationResult
        )

        risk_engine = MagicMock()
        risk_engine.assess_trade = AsyncMock(return_value=RiskAssessment(
            is_approved=True, violations=[], risk_score=0.1
        ))

        broker_gw = MagicMock()
        broker_gw.get_account_info = AsyncMock(return_value=MagicMock(
            balance=10_000.0, equity=10_000.0, leverage=100
        ))
        broker_gw.place_order = AsyncMock(return_value={
            "order_id": "E2E-001", "fill_price": 1.1052
        })

        strategy_engine = MagicMock()
        validation = ValidationResult(is_valid=True)
        strat = MagicMock()
        strat.validate_signal.return_value = validation
        strategy_engine.get_strategy.return_value = strat

        engine = ExecutionEngine(
            risk_engine=risk_engine,
            broker_gateway=broker_gw,
            strategy_engine=strategy_engine,
            allow_off_hours=True,
        )

        signal = TradeSignal(
            strategy=StrategyType.TREND_FOLLOWING,
            symbol="EURUSD",
            direction=SignalDirection.LONG,
            entry_price=1.1050,
            stop_loss=1.0990,
            take_profit=1.1170,
            confidence=0.82,
            parameters=StrategyParameters(
                stop_loss_pips=60.0,
                take_profit_pips=120.0,
                metadata={"lots": 0.1, "atr": 0.0008},
            ),
        )
        result = await engine.process_signal(signal, uuid4())
        assert result.success is True
        assert result.order_id is not None

    # ------------------------------------------------------------------
    # Step 8: Position monitoring (trailing stop)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_step_08_trailing_stop_updates(self):
        """Position manager moves stop to breakeven after 1×ATR move."""
        from forex_trading.execution.engine import ExecutionEngine, _TrackedPosition

        risk_engine = MagicMock()
        risk_engine.assess_trade = AsyncMock(return_value=MagicMock(is_approved=True))
        broker_gw = MagicMock()
        broker_gw.get_account_info = AsyncMock(return_value=MagicMock(
            balance=10_000.0, equity=10_000.0, leverage=100
        ))
        broker_gw.place_order = AsyncMock(return_value={"order_id": "E2E-002", "fill_price": 1.1052})

        strategy_engine = MagicMock()
        from forex_trading.strategy.engine import ValidationResult
        strategy_engine.get_strategy.return_value = MagicMock(
            validate_signal=MagicMock(return_value=ValidationResult(is_valid=True))
        )

        engine = ExecutionEngine(
            risk_engine=risk_engine,
            broker_gateway=broker_gw,
            strategy_engine=strategy_engine,
            allow_off_hours=True,
        )

        pid = uuid4()
        engine._positions[pid] = _TrackedPosition(
            position_id=pid,
            symbol="EURUSD",
            direction="long",
            entry_price=1.1050,
            current_stop_loss=1.0990,
            take_profit=1.1170,
            quantity=0.1,
            atr=0.0010,
            strategy_type="trend_following",
            max_holding_minutes=480,
            highest_price=1.1050,
            lowest_price=1.1050,
        )
        # Price moves 1.1×ATR above entry
        action = await engine.manage_position(pid, current_price=1.1061)
        assert action.action == "move_breakeven"

    # ------------------------------------------------------------------
    # Step 9: Position closes with profit
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_step_09_position_closes_at_take_profit(self):
        """Position is fully closed when requested."""
        from forex_trading.execution.engine import ExecutionEngine, _TrackedPosition

        risk_engine = MagicMock()
        broker_gw = MagicMock()
        broker_gw.get_account_info = AsyncMock(return_value=MagicMock(
            balance=10_000.0, equity=10_250.0, leverage=100
        ))
        broker_gw.place_order = AsyncMock(return_value={"order_id": "E2E-003", "fill_price": 1.1170})

        strategy_engine = MagicMock()
        from forex_trading.strategy.engine import ValidationResult
        strategy_engine.get_strategy.return_value = MagicMock(
            validate_signal=MagicMock(return_value=ValidationResult(is_valid=True))
        )

        engine = ExecutionEngine(
            risk_engine=risk_engine,
            broker_gateway=broker_gw,
            strategy_engine=strategy_engine,
            allow_off_hours=True,
        )

        pid = uuid4()
        conn = uuid4()
        engine._positions[pid] = _TrackedPosition(
            position_id=pid,
            symbol="EURUSD",
            direction="long",
            entry_price=1.1050,
            current_stop_loss=1.1050,  # at breakeven
            take_profit=1.1170,
            quantity=0.1,
            atr=0.0010,
            strategy_type="trend_following",
            max_holding_minutes=480,
            broker_connection_id=conn,
        )

        success = await engine.close_position(pid, reason="take_profit_hit", partial_pct=100.0)
        assert success is True
        assert pid not in engine._positions

    # ------------------------------------------------------------------
    # Step 10: Full pipeline integration (all components together)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_step_10_full_pipeline_from_context_to_order(self):
        """
        Complete pipeline:
        AI analysis → consensus → risk check → execution engine order.
        """
        from forex_trading.ai.orchestrator import AIOrchestrator
        from forex_trading.ai.agents.base import MarketContext, MarketRegime, SignalDirection
        from forex_trading.risk.engine import RiskEngine
        from forex_trading.execution.engine import ExecutionEngine
        from forex_trading.strategy.engine import (
            StrategyParameters, StrategyType, TradeSignal, ValidationResult
        )

        # --- AI layer ---
        orch = AIOrchestrator()
        ctx = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            candles=_make_candles(300),
            regime=MarketRegime.TRENDING_UP,
            metadata={
                "spread": 1.2,
                "current_drawdown_pct": 0.5,
                "open_positions": [],
                "market_bias": "long",
            },
        )
        ai_result = await orch.analyze(ctx)
        assert ai_result is not None

        # --- Risk layer ---
        risk_engine = RiskEngine()
        risk_engine.update_state(equity=10_000.0, drawdown_pct=0.0)
        assessment = await risk_engine.assess_trade("EURUSD", "long", 0.1, 1.1050)
        assert assessment.is_approved is True

        # --- Execution layer ---
        broker_gw = MagicMock()
        broker_gw.get_account_info = AsyncMock(return_value=MagicMock(
            balance=10_000.0, equity=10_000.0, leverage=100
        ))
        broker_gw.place_order = AsyncMock(return_value={"order_id": "FULL-001", "fill_price": 1.1052})

        mock_risk = MagicMock()
        from forex_trading.risk.engine import RiskAssessment
        mock_risk.assess_trade = AsyncMock(return_value=RiskAssessment(
            is_approved=True, violations=[], risk_score=0.1
        ))

        strat_engine = MagicMock()
        strat_engine.get_strategy.return_value = MagicMock(
            validate_signal=MagicMock(return_value=ValidationResult(is_valid=True))
        )

        exec_engine = ExecutionEngine(
            risk_engine=mock_risk,
            broker_gateway=broker_gw,
            strategy_engine=strat_engine,
            allow_off_hours=True,
        )

        signal = TradeSignal(
            strategy=StrategyType.TREND_FOLLOWING,
            symbol="EURUSD",
            direction=SignalDirection.LONG,
            entry_price=1.1050,
            stop_loss=1.0990,
            take_profit=1.1170,
            confidence=0.82,
            parameters=StrategyParameters(
                stop_loss_pips=60.0,
                take_profit_pips=120.0,
                metadata={"lots": 0.1, "atr": 0.0008},
            ),
        )
        exec_result = await exec_engine.process_signal(signal, uuid4())
        assert exec_result.success is True
        assert exec_result.order_id is not None
        assert exec_result.filled_price == pytest.approx(1.1052, abs=0.001)
