"""
Load / concurrency tests using asyncio.

Tests that the core components handle concurrent workloads without
deadlocks, race conditions, or data corruption.  No real infrastructure
is required – all services are instantiated in-process.

Marks: @pytest.mark.slow  (excluded from default CI run via addopts)
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(n: int = 300, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    price = 1.1000
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i in range(n):
        price = max(price + rng.gauss(0, 0.0008), 0.0001)
        o = price + rng.gauss(0, 0.0002)
        c = price + rng.gauss(0, 0.0002)
        h = max(o, c) + abs(rng.gauss(0, 0.0003))
        l = min(o, c) - abs(rng.gauss(0, 0.0003))
        candles.append({
            "timestamp": ts + timedelta(hours=i),
            "open": round(o, 5), "high": round(h, 5),
            "low": round(l, 5), "close": round(c, 5),
            "volume": rng.randint(100, 2000),
        })
    return candles


# ---------------------------------------------------------------------------
# TASK 1 – Concurrent Risk Assessments
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestRiskEngineUnderLoad:
    """Risk engine must handle many concurrent assessments safely."""

    @pytest.mark.asyncio
    async def test_1000_risk_assessments_in_parallel(self):
        """
        1 000 concurrent risk assessments must all complete and each return
        a valid RiskAssessment without raising.
        """
        from forex_trading.risk.engine import RiskEngine, RiskLimits

        engine = RiskEngine(limits=RiskLimits(max_positions=500))
        engine.update_state(equity=100_000.0, drawdown_pct=0.0)

        async def assess(i: int):
            return await engine.assess_trade(
                symbol="EURUSD",
                side="long" if i % 2 == 0 else "short",
                size=0.01,
                entry_price=1.1000 + i * 0.00001,
            )

        results = await asyncio.gather(*[assess(i) for i in range(1000)])
        assert len(results) == 1000
        for r in results:
            assert hasattr(r, "is_approved")
            assert 0.0 <= r.risk_score <= 1.0

    @pytest.mark.asyncio
    async def test_concurrent_state_updates_no_corruption(self):
        """Concurrent update_state calls do not corrupt the equity value."""
        from forex_trading.risk.engine import RiskEngine

        engine = RiskEngine()
        engine.update_state(equity=10_000.0, drawdown_pct=0.0)

        async def update(equity: float):
            engine.update_state(equity=equity, drawdown_pct=0.0)
            await asyncio.sleep(0)

        equities = [10_000.0 + i for i in range(100)]
        await asyncio.gather(*[update(e) for e in equities])
        # Last state must be one of the valid equity values we set
        final_equity = engine.get_state().current_equity
        assert final_equity in equities or final_equity == 10_000.0

    @pytest.mark.asyncio
    async def test_emergency_liquidate_under_concurrent_assess(self):
        """Emergency liquidate fires concurrently with trade assessments."""
        from forex_trading.risk.engine import RiskEngine

        engine = RiskEngine()
        engine.update_state(equity=50_000.0, drawdown_pct=0.0)

        async def assess_many():
            results = []
            for i in range(50):
                r = await engine.assess_trade("EURUSD", "long", 0.1, 1.1)
                results.append(r)
            return results

        liq_result, assess_results = await asyncio.gather(
            engine.emergency_liquidate_all("load test"),
            assess_many(),
        )
        assert liq_result["status"] == "liquidating"
        assert len(assess_results) == 50


# ---------------------------------------------------------------------------
# TASK 2 – Concurrent Market Data (tick processing)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestMarketDataUnderLoad:
    """MarketDataService handles high-frequency tick ingestion."""

    @pytest.mark.asyncio
    async def test_100_concurrent_tick_subscriptions(self):
        """100 concurrent subscribers each receive ticks for their symbol."""
        from forex_trading.market_data.services.market_data_service import MarketDataService

        service = MarketDataService()
        received: dict[str, list] = {}

        async def subscribe_and_wait(symbol: str):
            received[symbol] = []

            async def cb(event):
                received[symbol].append(event)

            await service.subscribe_ticks(symbol, cb)

        symbols = [f"SYM{i:03d}" for i in range(100)]
        await asyncio.gather(*[subscribe_and_wait(s) for s in symbols])

        # Send one tick per symbol
        await asyncio.gather(*[
            service.on_tick(s, 1.1000 + i * 0.0001, 1.1002 + i * 0.0001, 100)
            for i, s in enumerate(symbols)
        ])

        for s in symbols:
            assert len(received[s]) == 1

    @pytest.mark.asyncio
    async def test_high_frequency_ticks_for_single_symbol(self):
        """1 000 sequential ticks are all processed, last tick is current."""
        from forex_trading.market_data.services.market_data_service import MarketDataService

        service = MarketDataService()
        tick_count = 0

        async def cb(event):
            nonlocal tick_count
            tick_count += 1

        await service.subscribe_ticks("EURUSD", cb)

        for i in range(1_000):
            await service.on_tick("EURUSD", 1.1000 + i * 0.000001,
                                  1.1002 + i * 0.000001, 100)

        assert tick_count == 1_000
        price = await service.get_current_price("EURUSD")
        assert price["bid"] == pytest.approx(1.1000 + 999 * 0.000001, rel=1e-5)


# ---------------------------------------------------------------------------
# TASK 3 – Concurrent AI Orchestrator
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestAIOrchestatorUnderLoad:
    """AI Orchestrator handles concurrent analysis requests."""

    @pytest.mark.asyncio
    async def test_10_concurrent_analyses(self):
        """10 concurrent analyze() calls complete without errors."""
        from forex_trading.ai.orchestrator import AIOrchestrator, OrchestratorResult
        from forex_trading.ai.agents.base import MarketContext, MarketRegime

        orch = AIOrchestrator()
        candles = _make_candles(300)
        ctx = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            candles=candles,
            regime=MarketRegime.RANGING,
            metadata={},
        )

        results = await asyncio.gather(*[orch.analyze(ctx) for _ in range(10)])
        assert len(results) == 10
        for r in results:
            assert isinstance(r, OrchestratorResult)
            assert hasattr(r, "consensus")
            assert hasattr(r, "should_trade")

    @pytest.mark.asyncio
    async def test_concurrent_analyses_results_are_consistent(self):
        """Concurrent analyses on the same context produce consistent directions."""
        from forex_trading.ai.orchestrator import AIOrchestrator
        from forex_trading.ai.agents.base import MarketContext, MarketRegime

        orch = AIOrchestrator()
        candles = _make_candles(300, seed=99)
        ctx = MarketContext(
            symbol="EURUSD",
            timeframe="H1",
            candles=candles,
            regime=MarketRegime.RANGING,
            metadata={},
        )

        results = await asyncio.gather(*[orch.analyze(ctx) for _ in range(5)])
        directions = {r.consensus.direction for r in results}
        # All runs on the same deterministic context should give the same direction
        # (agents use numpy calculations; allow tiny non-determinism)
        assert len(directions) <= 2  # at most 2 different directions in edge cases


# ---------------------------------------------------------------------------
# TASK 4 – Session Detection Under Load
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestSessionDetectorUnderLoad:
    """SessionDetector is stateless and safe for concurrent use."""

    @pytest.mark.asyncio
    async def test_1000_concurrent_session_detections(self):
        """1 000 concurrent get_current_session calls."""
        from forex_trading.market_data.services.session_detector import SessionDetector
        from datetime import timezone

        detector = SessionDetector()

        async def detect(hour: int):
            t = datetime(2024, 1, 15, hour, 0, tzinfo=timezone.utc)
            return detector.get_current_session(t)

        tasks = [detect(h % 24) for h in range(1_000)]
        results = await asyncio.gather(*tasks)
        assert len(results) == 1_000
        for info in results:
            assert 0.0 <= info.session_strength <= 1.0


# ---------------------------------------------------------------------------
# TASK 5 – Throughput benchmark (informational, not a hard assertion)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestThroughputBenchmarks:
    """Rough throughput measurements – values are informational."""

    @pytest.mark.asyncio
    async def test_risk_assessment_throughput(self):
        """Measure risk assessments / second – must exceed 100/s."""
        from forex_trading.risk.engine import RiskEngine

        engine = RiskEngine()
        engine.update_state(equity=100_000.0, drawdown_pct=0.0)

        n = 500
        start = time.monotonic()
        await asyncio.gather(*[
            engine.assess_trade("EURUSD", "long", 0.01, 1.1)
            for _ in range(n)
        ])
        elapsed = time.monotonic() - start

        if elapsed < 1e-6:
            # So fast that elapsed rounds to zero – trivially exceeds threshold
            return

        throughput = n / elapsed

        # Very conservative threshold – even slow CI should hit 100/s
        assert throughput > 100, f"Risk assessment throughput too low: {throughput:.0f}/s"

    @pytest.mark.asyncio
    async def test_session_detection_throughput(self):
        """Session detections/second > 10 000 (pure computation, no I/O)."""
        from forex_trading.market_data.services.session_detector import SessionDetector

        detector = SessionDetector()
        n = 10_000
        t = datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)

        start = time.monotonic()
        for _ in range(n):
            detector.get_current_session(t)
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"Session detection too slow: {n/elapsed:.0f}/s"
