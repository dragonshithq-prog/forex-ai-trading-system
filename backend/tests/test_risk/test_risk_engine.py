"""Tests for the RiskEngine — circuit breakers, drawdown limits, Kelly criterion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hypothesis import given, strategies as st
from hypothesis.strategies import floats

from forex_trading.risk.engine import (
    RiskEngine,
    RiskLimits,
    RiskAssessment,
    CircuitBreakerState,
    RiskLevel,
)
from tests.factories import fake_risk_state


pytestmark = pytest.mark.asyncio


# ─── Helper to create a mock UoW with a risk state ────────────────────────

def _make_mock_uow(broker_account_id=None, **state_overrides):
    """Create a mock UoW with a fake RiskState."""
    account_id = broker_account_id or uuid4()
    state = fake_risk_state(broker_account_id=account_id, **state_overrides)
    uow = MagicMock()
    uow.risk_states.get_by_account = AsyncMock(return_value=state)
    uow.risk_states.upsert = AsyncMock(return_value=state)
    uow.flush = AsyncMock()
    uow.session = MagicMock()
    uow.session.add = MagicMock()
    return uow, account_id, state


class TestRiskEngineTradeAssessment:
    """Tests for the main assess_trade flow."""

    async def test_approves_valid_trade(self, risk_limits):
        """A trade with no violations should be approved."""
        uow, account_id, _ = _make_mock_uow(
            current_equity=10_000.0,
            peak_equity=10_000.0,
            current_drawdown_pct=0.0,
            total_exposure_pct=0.0,
            open_positions=0,
            consecutive_losses=0,
            daily_trades=0,
            is_circuit_breaker_active=False,
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        assessment = await engine.assess_trade(
            broker_account_id=account_id,
            symbol="EURUSD",
            side="buy",
            size=0.1,
            entry_price=1.1000,
            stop_loss=1.0950,
            confidence=0.75,
        )
        assert assessment.is_approved is True
        assert len(assessment.violations) == 0

    async def test_rejects_when_circuit_breaker_active(self, risk_limits):
        """An active circuit breaker should reject all trades."""
        uow, account_id, _ = _make_mock_uow(
            is_circuit_breaker_active=True,
            circuit_breaker_until=datetime.now(timezone.utc) + timedelta(hours=1),
            circuit_breaker_reason="Max drawdown",
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        assessment = await engine.assess_trade(
            broker_account_id=account_id,
            symbol="EURUSD",
            side="buy",
            size=0.1,
            entry_price=1.1000,
        )
        assert assessment.is_approved is False
        assert any("Circuit breaker" in v for v in assessment.violations)

    async def test_auto_resets_expired_circuit_breaker(self, risk_limits):
        """An expired circuit breaker should auto-reset and allow the trade."""
        uow, account_id, state = _make_mock_uow(
            is_circuit_breaker_active=True,
            circuit_breaker_until=datetime.now(timezone.utc) - timedelta(minutes=5),
            circuit_breaker_reason="Stale reason",
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        assessment = await engine.assess_trade(
            broker_account_id=account_id,
            symbol="EURUSD",
            side="buy",
            size=0.1,
            entry_price=1.1000,
        )
        # After auto-reset, if no other violations, the trade should be approved
        assert state.is_circuit_breaker_active is False
        assert state.circuit_breaker_until is None

    async def test_rejects_max_positions_exceeded(self, risk_limits):
        """Trades should be rejected if max positions reached."""
        uow, account_id, _ = _make_mock_uow(
            open_positions=10,  # max_positions = 10, so this is at limit
            current_equity=10_000.0,
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        assessment = await engine.assess_trade(
            broker_account_id=account_id,
            symbol="EURUSD",
            side="buy",
            size=0.1,
            entry_price=1.1000,
        )
        assert assessment.is_approved is False
        assert any("Maximum positions reached" in v for v in assessment.violations)

    async def test_warns_on_large_position_size(self, risk_limits):
        """Position size exceeding max should generate a warning."""
        uow, account_id, _ = _make_mock_uow(
            current_equity=10_000.0,
            total_exposure_pct=0.0,
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        # A large position relative to equity — 200 000 units (2 lots @ 100k)
        # on $10k equity is ~2200% notional, well above the 2% limit.
        assessment = await engine.assess_trade(
            broker_account_id=account_id,
            symbol="EURUSD",
            side="buy",
            size=200_000.0,  # units, not lots
            entry_price=1.1000,
        )
        # Position size is clamped but trade should proceed with warnings
        assert assessment.adjusted_size is not None or len(assessment.warnings) > 0

    async def test_rejects_daily_drawdown_exceeded(self, risk_limits):
        """Trades should be rejected if daily drawdown limit is exceeded."""
        uow, account_id, _ = _make_mock_uow(
            current_drawdown_pct=4.0,  # > daily drawdown limit of 3%
            current_equity=10_000.0,
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        assessment = await engine.assess_trade(
            broker_account_id=account_id,
            symbol="EURUSD",
            side="buy",
            size=0.1,
            entry_price=1.1000,
        )
        assert assessment.is_approved is False
        assert any("Daily drawdown" in v for v in assessment.violations)

    async def test_rejects_consecutive_losses(self, risk_limits):
        """Trades should be rejected if consecutive losses exceed limit."""
        uow, account_id, _ = _make_mock_uow(
            consecutive_losses=5,  # max is 5
            current_equity=10_000.0,
            current_drawdown_pct=0.0,
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        assessment = await engine.assess_trade(
            broker_account_id=account_id,
            symbol="EURUSD",
            side="buy",
            size=0.1,
            entry_price=1.1000,
        )
        assert assessment.is_approved is False
        assert any("Consecutive losses" in v for v in assessment.violations)

    async def test_rejects_daily_trade_limit(self, risk_limits):
        """Trades should be rejected if daily trade limit is reached."""
        uow, account_id, _ = _make_mock_uow(
            daily_trades=50,  # max_daily_trades = 50
            current_equity=10_000.0,
            current_drawdown_pct=0.0,
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        assessment = await engine.assess_trade(
            broker_account_id=account_id,
            symbol="EURUSD",
            side="buy",
            size=0.1,
            entry_price=1.1000,
        )
        assert assessment.is_approved is False
        assert any("Daily trade limit" in v for v in assessment.violations)

    async def test_max_drawdown_triggers_circuit_breaker(self, risk_limits):
        """Exceeding max drawdown should activate the circuit breaker."""
        uow, account_id, _ = _make_mock_uow(
            current_drawdown_pct=16.0,  # > max_drawdown_limit_pct of 15%
            current_equity=8_000.0,
            peak_equity=10_000.0,
            is_circuit_breaker_active=False,
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        assessment = await engine.assess_trade(
            broker_account_id=account_id,
            symbol="EURUSD",
            side="buy",
            size=0.1,
            entry_price=1.1000,
        )
        assert assessment.is_approved is False
        assert any("Maximum drawdown" in v for v in assessment.violations)

    async def test_requires_attached_uow(self, risk_limits):
        """assess_trade should raise RuntimeError without an attached UoW."""
        engine = RiskEngine(limits=risk_limits)
        with pytest.raises(RuntimeError, match="no UnitOfWork"):
            await engine.assess_trade(
                broker_account_id=uuid4(),
                symbol="EURUSD",
                side="buy",
                size=0.1,
                entry_price=1.1000,
            )


class TestRiskEngineRecordOutcome:
    """Tests for recording trade outcomes."""

    async def test_record_winning_trade(self, risk_limits):
        """A winning trade should reset consecutive losses."""
        uow, account_id, state = _make_mock_uow(
            consecutive_losses=3,
            current_equity=10_500.0,
            peak_equity=10_000.0,
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        await engine.record_trade_outcome(
            broker_account_id=account_id,
            pnl=500.0,
            won=True,
        )
        assert state.consecutive_losses == 0

    async def test_record_losing_trade(self, risk_limits):
        """A losing trade should increment consecutive losses."""
        uow, account_id, state = _make_mock_uow(
            consecutive_losses=0,
            current_equity=9_500.0,
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        await engine.record_trade_outcome(
            broker_account_id=account_id,
            pnl=-500.0,
            won=False,
        )
        assert state.consecutive_losses == 1

    async def test_record_outcome_activates_circuit_breaker(self, risk_limits):
        """Hitting max consecutive losses should activate circuit breaker."""
        uow, account_id, state = _make_mock_uow(
            consecutive_losses=4,  # One more loss = 5 = max
            current_equity=9_000.0,
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        await engine.record_trade_outcome(
            broker_account_id=account_id,
            pnl=-200.0,
            won=False,
        )
        assert state.consecutive_losses >= risk_limits.max_consecutive_losses
        assert state.is_circuit_breaker_active is True


class TestRiskEngineCircuitBreaker:
    """Tests for circuit breaker state machine."""

    async def test_deactivate_circuit_breaker(self, risk_limits):
        uow, account_id, state = _make_mock_uow(
            is_circuit_breaker_active=True,
            circuit_breaker_until=datetime.now(timezone.utc) + timedelta(hours=1),
            circuit_breaker_reason="Test",
        )
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        await engine.deactivate_circuit_breaker(account_id)
        assert state.is_circuit_breaker_active is False
        assert state.circuit_breaker_until is None
        assert state.circuit_breaker_reason is None

    async def test_emergency_liquidate(self, risk_limits):
        uow, account_id, state = _make_mock_uow()
        engine = RiskEngine(limits=risk_limits, uow_factory=MagicMock())
        engine._uow = uow

        result = await engine.emergency_liquidate_all(account_id, "Test emergency")
        assert result["status"] == "circuit_breaker_activated"
        assert result["reason"] == "Test emergency"
        assert state.is_circuit_breaker_active is True

    async def test_check_circuit_breaker_closed(self, risk_limits):
        engine = RiskEngine(limits=risk_limits)
        state = fake_risk_state(is_circuit_breaker_active=False)
        assert engine._check_circuit_breaker(state) is None


class TestKellyCriterion:
    """Tests for the Kelly Criterion position sizing."""

    def test_kelly_with_valid_inputs(self):
        engine = RiskEngine()
        fk, risk_amount = engine.kelly_size(
            win_rate=0.6,
            avg_win=200.0,
            avg_loss=100.0,
            account_balance=10_000.0,
            max_cap_pct=0.02,
        )
        # p = 0.6, q = 0.4, b = 2.0
        # kelly = (0.6*2 - 0.4)/2 = (1.2-0.4)/2 = 0.4
        # fractional (25%) = 0.1
        # capped at 0.02 → 0.02
        assert fk == 0.02
        assert risk_amount == 200.0

    def test_kelly_with_edge_cases(self):
        engine = RiskEngine()

        # Zero win rate → use default
        fk, risk = engine.kelly_size(0.0, 200, 100, 10_000)
        assert fk == 0.01

        # Win rate = 1.0 (never lose) → falls back to default
        fk, risk = engine.kelly_size(1.0, 200, 100, 10_000)
        assert fk == 0.01

        # Unprofitable strategy
        fk, risk = engine.kelly_size(0.4, 100, 150, 10_000)
        # Kelly would be negative → use fallback
        assert fk == 0.01

    def test_kelly_with_zero_avg_loss(self):
        engine = RiskEngine()
        fk, risk = engine.kelly_size(0.6, 200, 0, 10_000)
        assert fk == 0.01  # Falls back on avg_loss <= 0

    @given(
        win_rate=floats(min_value=0.01, max_value=0.99),
        avg_win=floats(min_value=1.0, max_value=1000.0),
        avg_loss=floats(min_value=1.0, max_value=1000.0),
        balance=floats(min_value=1000.0, max_value=1_000_000.0),
    )
    def test_kelly_property_bounds(self, win_rate, avg_win, avg_loss, balance):
        """Kelly fraction should always be in the range (0, max_cap_pct]."""
        engine = RiskEngine()
        fk, risk_amount = engine.kelly_size(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            account_balance=balance,
            max_cap_pct=0.02,
        )
        assert 0 < fk <= 0.02
        assert 0 < risk_amount <= balance * 0.02


class TestRiskEngineSizingHelpers:
    """Tests for position sizing helpers."""

    def test_position_size_pct(self):
        engine = RiskEngine()
        state = fake_risk_state(current_equity=10_000.0)
        # size is in units, price in quote currency per unit
        # pct = (units * price) / equity * 100
        # 100_000 units (1 lot) at 1.1000 on 10k equity:
        # (100000 * 1.1) / 10000 * 100 = 1100%
        pct = engine._position_size_pct(size=100_000.0, price=1.1000, state=state)
        assert pct == pytest.approx(1100.0)

    def test_position_size_pct_zero_equity(self):
        engine = RiskEngine()
        state = fake_risk_state(current_equity=0.0)
        pct = engine._position_size_pct(size=0.1, price=1.1000, state=state)
        assert pct == 0.0

    def test_compute_risk_score(self):
        engine = RiskEngine(limits=RiskLimits(
            max_drawdown_limit_pct=10.0,
            max_total_exposure_pct=20.0,
            max_consecutive_losses=5,
        ))
        state = fake_risk_state(
            current_drawdown_pct=5.0,
            total_exposure_pct=10.0,
            consecutive_losses=2,
            is_circuit_breaker_active=False,
        )
        score = engine._compute_risk_score(state)
        # dd = 5/10 = 0.5, exp = 10/20 = 0.5, loss = 2/5 = 0.4, cb = 0
        # (0.5 + 0.5 + 0.4 + 0) / 4 = 0.35
        assert score == pytest.approx(0.35, rel=0.01)

    def test_risk_score_with_circuit_breaker(self):
        engine = RiskEngine()
        state = fake_risk_state(
            current_drawdown_pct=0.0,
            total_exposure_pct=0.0,
            consecutive_losses=0,
            is_circuit_breaker_active=True,
        )
        score = engine._compute_risk_score(state)
        # (0 + 0 + 0 + 1) / 4 = 0.25
        assert score == 0.25


class TestRiskEngineHealthCheck:
    """Tests for the health check endpoint."""

    async def test_health_check(self, risk_limits):
        engine = RiskEngine(limits=risk_limits)
        status = await engine.health_check()
        assert status["limits"]["max_positions"] == 10
        assert status["limits"]["max_drawdown_pct"] == 15.0
        assert status["limits"]["max_consecutive_losses"] == 5
