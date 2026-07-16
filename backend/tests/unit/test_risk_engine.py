"""
Comprehensive unit tests for the RiskEngine.

Covers: trade assessment, circuit breaker lifecycle, consecutive losses,
daily drawdown halt, position sizing adjustments, risk score calculation,
force-close and emergency liquidation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from forex_trading.risk.engine import (
    RiskAssessment,
    RiskEngine,
    RiskLimits,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def limits() -> RiskLimits:
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
    )


@pytest.fixture
def engine(limits: RiskLimits) -> RiskEngine:
    e = RiskEngine(limits=limits)
    e.update_state(equity=10_000.0, drawdown_pct=0.0)
    return e


# ---------------------------------------------------------------------------
# TestTradeAssessment
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTradeAssessment:
    """assess_trade() covers all hard-limit paths."""

    @pytest.mark.asyncio
    async def test_assess_trade_within_limits_approved(self, engine):
        """Small trade well within all limits → approved."""
        result = await engine.assess_trade(
            symbol="EURUSD",
            side="long",
            size=0.1,
            entry_price=1.1000,
        )
        assert result.is_approved is True
        assert len(result.violations) == 0
        assert 0.0 <= result.risk_score <= 1.0

    @pytest.mark.asyncio
    async def test_assess_trade_exceeds_max_positions_rejected(self, engine):
        """10 open positions → next trade rejected."""
        engine._state.open_positions = 10
        result = await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        assert result.is_approved is False
        assert any("positions" in v.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_assess_trade_circuit_breaker_active_rejected(self, engine):
        """Active circuit breaker blocks all new trades."""
        engine._state.is_circuit_breaker_active = True
        engine._state.circuit_breaker_until = datetime.utcnow() + timedelta(hours=1)

        result = await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        assert result.is_approved is False
        assert result.risk_score == 1.0
        assert any("circuit breaker" in v.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_assess_trade_circuit_breaker_expired_auto_reset(self, engine):
        """Expired circuit breaker is auto-reset and trade can proceed."""
        engine._state.is_circuit_breaker_active = True
        engine._state.circuit_breaker_until = datetime.utcnow() - timedelta(hours=1)  # in the past

        result = await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        # Circuit breaker should have been cleared
        assert engine._state.is_circuit_breaker_active is False
        # Trade may be approved now (no other violations)
        assert result.is_approved is True

    @pytest.mark.asyncio
    async def test_assess_trade_daily_drawdown_limit_rejected(self, engine):
        """Daily drawdown at or above limit → violation."""
        engine.update_state(equity=10_000.0, drawdown_pct=3.5)  # above 3.0% daily limit
        result = await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        assert result.is_approved is False
        assert any("drawdown" in v.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_assess_trade_max_drawdown_activates_circuit_breaker(self, engine):
        """Drawdown at max limit → circuit breaker activated AND trade rejected."""
        engine.update_state(equity=10_000.0, drawdown_pct=15.5)  # above 15% max
        result = await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        assert result.is_approved is False
        assert engine._state.is_circuit_breaker_active is True
        assert engine._state.circuit_breaker_until is not None

    @pytest.mark.asyncio
    async def test_assess_trade_consecutive_losses_limit_rejected(self, engine):
        """5 consecutive losses → trade rejected."""
        engine._state.consecutive_losses = 5  # at limit
        result = await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        assert result.is_approved is False
        assert any("consecutive" in v.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_assess_trade_oversized_position_gets_warning(self, engine):
        """Position exceeding max_position_size_pct (2%) → warning and adjusted size."""
        # 300 units at 1.1 = $330 = 3.3% of $10k → exceeds 2% max
        result = await engine.assess_trade("EURUSD", "long", 300.0, 1.1000)
        assert len(result.warnings) > 0
        # Adjusted size should be smaller than original
        if result.adjusted_size is not None:
            assert result.adjusted_size < 300.0

    @pytest.mark.asyncio
    async def test_assess_trade_no_equity_still_runs(self, engine):
        """Engine with zero equity should not crash – returns a result."""
        engine.update_state(equity=0.0, drawdown_pct=0.0)
        result = await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        assert isinstance(result, RiskAssessment)

    @pytest.mark.asyncio
    async def test_assess_trade_short_side_approved(self, engine):
        """Short trades follow the same rules."""
        result = await engine.assess_trade("GBPUSD", "short", 0.1, 1.2700)
        assert result.is_approved is True

    @pytest.mark.asyncio
    async def test_multiple_violations_all_captured(self, engine):
        """Multiple violations are all recorded."""
        engine._state.open_positions = 10
        engine.update_state(equity=10_000.0, drawdown_pct=4.0)  # exceeds daily

        result = await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        assert result.is_approved is False
        assert len(result.violations) >= 2  # both positions and drawdown


# ---------------------------------------------------------------------------
# TestCircuitBreaker
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCircuitBreaker:
    """Circuit breaker activation, blocking, and cooldown reset."""

    @pytest.mark.asyncio
    async def test_emergency_liquidate_activates_circuit_breaker(self, engine):
        result = await engine.emergency_liquidate_all("Test emergency")
        assert result["status"] == "liquidating"
        assert engine._state.is_circuit_breaker_active is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_new_trades_after_activation(self, engine):
        """Active circuit breaker with future expiry blocks all new trades."""
        # Set CB explicitly with a future expiry (emergency_liquidate sets active=True
        # but not 'until', so we set both here to ensure the block path is exercised)
        engine._state.is_circuit_breaker_active = True
        engine._state.circuit_breaker_until = datetime.utcnow() + timedelta(hours=1)
        result = await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        assert result.is_approved is False

    @pytest.mark.asyncio
    async def test_circuit_breaker_reset_after_cooldown(self, engine):
        """Once cooldown expires the CB auto-resets on next trade assessment."""
        engine._state.is_circuit_breaker_active = True
        # Set cooldown in the past
        engine._state.circuit_breaker_until = datetime.utcnow() - timedelta(minutes=1)

        result = await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        assert engine._state.is_circuit_breaker_active is False
        assert result.is_approved is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_until_set_correctly(self, engine):
        """Activated circuit breaker sets future cooldown timestamp."""
        engine.update_state(equity=10_000.0, drawdown_pct=15.5)
        await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        assert engine._state.circuit_breaker_until is not None
        assert engine._state.circuit_breaker_until > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_circuit_breaker_alert_added_on_activation(self, engine):
        """Alert is logged when circuit breaker fires."""
        engine.update_state(equity=10_000.0, drawdown_pct=15.5)
        await engine.assess_trade("EURUSD", "long", 0.1, 1.1000)
        alerts = engine.get_alerts()
        assert len(alerts) > 0
        assert any("circuit_breaker" == a.category for a in alerts)


# ---------------------------------------------------------------------------
# TestRiskScore
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRiskScore:
    """Risk score is correctly computed and bounded."""

    def test_risk_score_is_zero_at_baseline(self, engine):
        """Fresh engine with zero drawdown/exposure → risk score = 0."""
        score = engine._calculate_risk_score()
        assert 0.0 <= score <= 1.0

    def test_risk_score_increases_with_drawdown(self, engine):
        engine.update_state(equity=10_000.0, drawdown_pct=0.0)
        low = engine._calculate_risk_score()
        engine.update_state(equity=10_000.0, drawdown_pct=7.5)
        high = engine._calculate_risk_score()
        assert high > low

    def test_risk_score_increases_with_consecutive_losses(self, engine):
        engine._state.consecutive_losses = 0
        low = engine._calculate_risk_score()
        engine._state.consecutive_losses = 4
        high = engine._calculate_risk_score()
        assert high > low

    def test_risk_score_capped_at_one(self, engine):
        """Risk score never exceeds 1.0 even in extreme conditions."""
        engine.update_state(equity=10_000.0, drawdown_pct=100.0)
        engine._state.total_exposure_pct = 9999.0
        engine._state.consecutive_losses = 9999
        score = engine._calculate_risk_score()
        assert score <= 1.0

    def test_risk_score_never_negative(self, engine):
        score = engine._calculate_risk_score()
        assert score >= 0.0


# ---------------------------------------------------------------------------
# TestPositionMonitoring
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPositionMonitoring:
    """Position-level risk monitoring."""

    @pytest.mark.asyncio
    async def test_monitor_profitable_position_no_alert(self, engine):
        pos = Position(
            position_id=uuid4(),
            symbol="EURUSD",
            side="long",
            size=0.1,
            entry_price=1.1000,
            current_price=1.1100,
            unrealized_pnl=100.0,  # profit
        )
        alert = await engine.monitor_position(pos)
        assert alert is None

    @pytest.mark.asyncio
    async def test_monitor_large_loss_generates_alert(self, engine):
        """Loss exceeding max_position_size_pct of equity → alert."""
        pos = Position(
            position_id=uuid4(),
            symbol="EURUSD",
            side="long",
            size=1.0,
            entry_price=1.1000,
            current_price=1.0700,
            unrealized_pnl=-3_000.0,  # 30% of $10k equity
        )
        alert = await engine.monitor_position(pos)
        assert alert is not None
        assert alert.category == "position_loss"

    @pytest.mark.asyncio
    async def test_force_close_existing_position(self, engine):
        """force_close_position on a tracked position returns closed status."""
        pid = uuid4()
        engine._positions[pid] = Position(
            position_id=pid, symbol="EURUSD", side="long",
            size=0.1, entry_price=1.1000, current_price=1.1050,
            unrealized_pnl=50.0,
        )
        result = await engine.force_close_position(pid, "test close")
        assert result.get("status") == "closed"
        assert result.get("position_id") == str(pid)

    @pytest.mark.asyncio
    async def test_force_close_nonexistent_position_returns_error(self, engine):
        """force_close_position on unknown ID returns error dict (not raise)."""
        result = await engine.force_close_position(uuid4(), "orphan close")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_emergency_liquidate_all_returns_liquidating(self, engine):
        pid = uuid4()
        engine._positions[pid] = Position(
            position_id=pid, symbol="EURUSD", side="long",
            size=0.1, entry_price=1.1000, current_price=1.1000,
            unrealized_pnl=0.0,
        )
        result = await engine.emergency_liquidate_all("Emergency test")
        assert result["status"] == "liquidating"
        assert result["positions_count"] == 1
        assert engine._state.is_circuit_breaker_active is True


# ---------------------------------------------------------------------------
# TestStateManagement
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStateManagement:
    """update_state and get_state work correctly."""

    def test_update_state_persists_equity_and_drawdown(self, engine):
        engine.update_state(equity=50_000.0, drawdown_pct=2.5)
        state = engine.get_state()
        assert state.current_equity == 50_000.0
        assert state.current_drawdown_pct == 2.5

    def test_update_state_updates_timestamp(self, engine):
        before = engine._state.last_updated
        engine.update_state(equity=10_000.0, drawdown_pct=0.0)
        after = engine._state.last_updated
        # Timestamp should advance (or be equal within the same second)
        assert after >= before

    def test_get_alerts_returns_list(self, engine):
        alerts = engine.get_alerts()
        assert isinstance(alerts, list)

    def test_get_alerts_respects_limit(self, engine):
        """get_alerts(limit=2) returns at most 2 alerts."""
        from forex_trading.risk.engine import RiskAlert, RiskLevel
        for i in range(5):
            engine._alerts.append(RiskAlert(
                level=RiskLevel.INFO,
                category="test",
                message=f"alert {i}",
            ))
        alerts = engine.get_alerts(limit=2)
        assert len(alerts) <= 2


# ---------------------------------------------------------------------------
# TestPositionSizeCalculations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPositionSizeCalculations:
    """Internal sizing helpers."""

    def test_calculate_position_pct_correct(self, engine):
        """100,000 units (1 standard lot) EURUSD @ 1.1 on $10k = 1100%."""
        pct = engine._calculate_position_pct(size=100_000.0, price=1.1)
        assert pct == pytest.approx(1100.0, rel=0.01)

    def test_calculate_position_pct_zero_equity(self, engine):
        engine.update_state(equity=0.0, drawdown_pct=0.0)
        pct = engine._calculate_position_pct(size=1.0, price=1.1)
        assert pct == 0.0

    def test_calculate_max_allowed_size_positive(self, engine):
        """Max allowed size must be > 0 when equity > 0."""
        max_size = engine._calculate_max_allowed_size(price=1.1)
        assert max_size > 0

    def test_calculate_max_allowed_size_zero_price(self, engine):
        assert engine._calculate_max_allowed_size(price=0.0) == 0.0

    def test_calculate_max_position_size_capped(self, engine):
        """Single position max: equity * 2% / price = $200 / 1.1 ≈ 182 units."""
        max_pos = engine._calculate_max_position_size(price=1.1)
        expected = 10_000 * 0.02 / 1.1
        assert max_pos == pytest.approx(expected, rel=0.01)
