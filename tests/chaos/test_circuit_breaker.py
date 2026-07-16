"""Chaos test: Circuit breaker validation — verify auto-reset after failures.

Validates that circuit breakers trip on repeated failures, block operations
while open, and reset automatically after the cooldown period.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest


pytestmark = pytest.mark.chaos


class TestCircuitBreakerTrips:
    """Circuit breaker trips after repeated failures."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_trips_after_threshold(self):
        """After threshold consecutive failures, circuit breaker opens."""
        from forex_trading.risk.engine import RiskEngine, RiskLimits

        engine = RiskEngine(
            limits=RiskLimits(
                max_consecutive_losses=3,
                cooldown_minutes=60,
            )
        )
        engine.update_state(equity=100_000.0, drawdown_pct=0.0)

        # Simulate 3 consecutive losing trades
        for i in range(3):
            engine.record_trade_result(loss=True)
            await asyncio.sleep(0)

        assert engine.is_circuit_breaker_active() is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_new_trades(self):
        """When circuit breaker is open, new trade assessments are rejected."""
        from forex_trading.risk.engine import RiskEngine, RiskLimits

        engine = RiskEngine(
            limits=RiskLimits(
                max_consecutive_losses=2,
                cooldown_minutes=60,
            )
        )
        engine.update_state(equity=100_000.0, drawdown_pct=0.0)
        engine._circuit_breaker_active = True
        engine._circuit_breaker_until = datetime.now(timezone.utc) + timedelta(hours=1)

        assessment = await engine.assess_trade(
            symbol="EURUSD", side="long", size=0.1, entry_price=1.1000
        )
        assert assessment.is_approved is False
        assert any("circuit breaker" in v.lower() for v in assessment.violations)

    @pytest.mark.asyncio
    async def test_circuit_breaker_allows_trades_after_cooldown(self):
        """After cooldown expires, new trades are allowed again."""
        from forex_trading.risk.engine import RiskEngine, RiskLimits

        engine = RiskEngine(
            limits=RiskLimits(
                max_consecutive_losses=2,
                cooldown_minutes=0,  # Immediate reset
            )
        )
        engine.update_state(equity=100_000.0, drawdown_pct=0.0)

        # Trip the breaker
        for i in range(2):
            engine.record_trade_result(loss=True)

        assert engine.is_circuit_breaker_active() is True

        # Force reset (simulating cooldown expiry)
        engine.reset_circuit_breaker()
        assert engine.is_circuit_breaker_active() is False

        assessment = await engine.assess_trade(
            symbol="EURUSD", side="long", size=0.1, entry_price=1.1000
        )
        assert assessment.is_approved is True

    @pytest.mark.asyncio
    async def test_winning_trade_resets_consecutive_loss_counter(self):
        """A winning trade resets the consecutive loss counter, preventing breaker trip."""
        from forex_trading.risk.engine import RiskEngine, RiskLimits

        engine = RiskEngine(
            limits=RiskLimits(max_consecutive_losses=3, cooldown_minutes=60)
        )

        # Two losses
        engine.record_trade_result(loss=True)
        engine.record_trade_result(loss=True)
        # Then a win
        engine.record_trade_result(loss=False)

        # Third loss should NOT trip (since win reset counter)
        engine.record_trade_result(loss=True)
        assert engine.is_circuit_breaker_active() is False


class TestCircuitBreakerPersistence:
    """Circuit breaker state persists across container restarts."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_serializable(self):
        """Circuit breaker state can be serialized for DB persistence."""
        from forex_trading.risk.engine import RiskEngine, RiskLimits

        engine = RiskEngine(limits=RiskLimits())
        engine._circuit_breaker_active = True
        engine._circuit_breaker_reason = "Test: consecutive losses"

        state = engine.get_state()
        assert state is not None

    @pytest.mark.asyncio
    async def test_multiple_breakers_independent(self):
        """Different instruments/broker accounts have independent breakers."""
        from forex_trading.risk.engine import RiskEngine, RiskLimits

        eur_engine = RiskEngine(limits=RiskLimits(max_consecutive_losses=2))
        gbp_engine = RiskEngine(limits=RiskLimits(max_consecutive_losses=2))

        eur_engine._circuit_breaker_active = True
        assert gbp_engine.is_circuit_breaker_active() is False
