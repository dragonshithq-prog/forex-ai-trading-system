"""Comprehensive tests for all AI agents, consensus engine, explainer, and orchestrator."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from forex_trading.ai.agents.base import (
    AgentSignal,
    MarketContext,
    MarketRegime,
    SignalDirection,
)
from forex_trading.ai.agents.entry import EntryAgent
from forex_trading.ai.agents.exit import ExitAgent
from forex_trading.ai.agents.liquidity import LiquidityAgent
from forex_trading.ai.agents.market_structure import MarketStructureAgent
from forex_trading.ai.agents.risk_agent import RiskAgent
from forex_trading.ai.agents.sentiment import SentimentAgent
from forex_trading.ai.agents.smart_money import SmartMoneyAgent
from forex_trading.ai.agents.trend import TrendAgent
from forex_trading.ai.agents.volatility import VolatilityAgent
from forex_trading.ai.consensus.engine import ConsensusEngine, ConsensusResult
from forex_trading.ai.orchestrator import AIOrchestrator, OrchestratorResult
from forex_trading.ai.xai.explainer import TradeExplanation, TradeExplainer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_candles(
    n: int = 300,
    base: float = 1.1000,
    trend: float = 0.0,
    seed: int = 42,
) -> list[dict]:
    """Generate n synthetic OHLCV candles with optional trend bias."""
    rng = random.Random(seed)
    candles: list[dict] = []
    price = base
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        price = price + trend + rng.uniform(-0.0015, 0.0015)
        open_ = price
        close = price + rng.uniform(-0.0010, 0.0010)
        high = max(open_, close) + rng.uniform(0.0002, 0.0008)
        low = min(open_, close) - rng.uniform(0.0002, 0.0008)
        candles.append({
            "timestamp": ts + timedelta(hours=i),
            "open": round(open_, 5),
            "high": round(high, 5),
            "low": round(low, 5),
            "close": round(close, 5),
            "volume": rng.randint(200, 2000),
        })
    return candles


def _make_bullish_candles(n: int = 300) -> list[dict]:
    """Generate candles with a clear uptrend."""
    return _make_candles(n=n, trend=0.00015, seed=1)


def _make_bearish_candles(n: int = 300) -> list[dict]:
    """Generate candles with a clear downtrend."""
    return _make_candles(n=n, trend=-0.00015, seed=2)


def _make_ranging_candles(n: int = 300) -> list[dict]:
    """Generate flat/ranging candles."""
    return _make_candles(n=n, trend=0.0, seed=3)


_SENTINEL = object()


def _base_context(
    candles: list[dict] | None = _SENTINEL,  # type: ignore[assignment]
    regime: MarketRegime = MarketRegime.RANGING,
    metadata: dict | None = None,
) -> MarketContext:
    return MarketContext(
        symbol="EURUSD",
        timeframe="H1",
        candles=_make_candles() if candles is _SENTINEL else candles,
        regime=regime,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# MarketStructureAgent tests
# ---------------------------------------------------------------------------

class TestMarketStructureAgent:
    agent = MarketStructureAgent()

    def test_agent_id(self):
        assert self.agent.agent_id == "market_structure"

    def test_required_data(self):
        assert "candles" in self.agent.required_data()

    def test_get_weight_trending_up(self):
        assert self.agent.get_weight(MarketRegime.TRENDING_UP) >= 0.85

    def test_get_weight_trending_down(self):
        assert self.agent.get_weight(MarketRegime.TRENDING_DOWN) >= 0.85

    def test_get_weight_ranging_lower(self):
        w_trend = self.agent.get_weight(MarketRegime.TRENDING_UP)
        w_range = self.agent.get_weight(MarketRegime.RANGING)
        assert w_trend > w_range

    @pytest.mark.asyncio
    async def test_insufficient_candles_returns_neutral(self):
        ctx = _base_context(candles=_make_candles(5))
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL
        assert sig.confidence == 0.0

    @pytest.mark.asyncio
    async def test_returns_agent_signal(self):
        ctx = _base_context(candles=_make_candles(100))
        sig = await self.agent.analyze(ctx)
        assert isinstance(sig, AgentSignal)
        assert sig.agent_id == "market_structure"
        assert 0.0 <= sig.confidence <= 1.0
        assert sig.direction in list(SignalDirection)

    @pytest.mark.asyncio
    async def test_bullish_trend_returns_long_or_neutral(self):
        ctx = _base_context(candles=_make_bullish_candles(100))
        sig = await self.agent.analyze(ctx)
        assert sig.direction in (SignalDirection.LONG, SignalDirection.NEUTRAL)

    @pytest.mark.asyncio
    async def test_bearish_trend_returns_short_or_neutral(self):
        ctx = _base_context(candles=_make_bearish_candles(100))
        sig = await self.agent.analyze(ctx)
        assert sig.direction in (SignalDirection.SHORT, SignalDirection.NEUTRAL)

    @pytest.mark.asyncio
    async def test_supporting_data_populated(self):
        ctx = _base_context(candles=_make_candles(100))
        sig = await self.agent.analyze(ctx)
        assert "structure_label" in sig.supporting_data
        assert "bos_event" in sig.supporting_data


# ---------------------------------------------------------------------------
# TrendAgent tests
# ---------------------------------------------------------------------------

class TestTrendAgent:
    agent = TrendAgent()

    def test_agent_id(self):
        assert self.agent.agent_id == "trend"

    def test_required_data(self):
        assert "candles" in self.agent.required_data()

    def test_weight_trending_highest(self):
        assert self.agent.get_weight(MarketRegime.TRENDING_UP) >= 0.85
        assert self.agent.get_weight(MarketRegime.RANGING) < self.agent.get_weight(MarketRegime.TRENDING_UP)

    @pytest.mark.asyncio
    async def test_insufficient_candles(self):
        ctx = _base_context(candles=_make_candles(50))
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_returns_valid_signal_with_enough_candles(self):
        ctx = _base_context(candles=_make_candles(220))
        sig = await self.agent.analyze(ctx)
        assert isinstance(sig, AgentSignal)
        assert 0.0 <= sig.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_supporting_data_has_indicators(self):
        ctx = _base_context(candles=_make_candles(220))
        sig = await self.agent.analyze(ctx)
        if sig.direction != SignalDirection.NEUTRAL or sig.confidence > 0:
            # If we got indicators, check keys
            data = sig.supporting_data
            if data:
                assert any(k in data for k in ["ema20", "adx", "macd_diff"])

    @pytest.mark.asyncio
    async def test_confidence_bounded(self):
        for _ in range(3):
            ctx = _base_context(candles=_make_candles(250, seed=random.randint(0, 999)))
            sig = await self.agent.analyze(ctx)
            assert 0.0 <= sig.confidence <= 1.0


# ---------------------------------------------------------------------------
# LiquidityAgent tests
# ---------------------------------------------------------------------------

class TestLiquidityAgent:
    agent = LiquidityAgent()

    def test_agent_id(self):
        assert self.agent.agent_id == "liquidity"

    def test_required_data(self):
        assert "candles" in self.agent.required_data()

    def test_weight_ranging_highest(self):
        assert self.agent.get_weight(MarketRegime.RANGING) >= 0.80

    @pytest.mark.asyncio
    async def test_insufficient_candles_neutral(self):
        ctx = _base_context(candles=_make_candles(10))
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_returns_valid_signal(self):
        ctx = _base_context(candles=_make_candles(100))
        sig = await self.agent.analyze(ctx)
        assert isinstance(sig, AgentSignal)
        assert sig.direction in list(SignalDirection)

    @pytest.mark.asyncio
    async def test_supporting_data_has_zone_info(self):
        ctx = _base_context(candles=_make_candles(100))
        sig = await self.agent.analyze(ctx)
        assert "order_blocks_found" in sig.supporting_data
        assert "fvgs_found" in sig.supporting_data


# ---------------------------------------------------------------------------
# VolatilityAgent tests
# ---------------------------------------------------------------------------

class TestVolatilityAgent:
    agent = VolatilityAgent()

    def test_agent_id(self):
        assert self.agent.agent_id == "volatility"

    def test_required_data(self):
        assert "candles" in self.agent.required_data()

    def test_weight_volatile_high(self):
        assert self.agent.get_weight(MarketRegime.VOLATILE) >= 0.80

    def test_weight_low_vol_high(self):
        assert self.agent.get_weight(MarketRegime.LOW_VOLATILITY) >= 0.80

    @pytest.mark.asyncio
    async def test_insufficient_candles_neutral(self):
        ctx = _base_context(candles=_make_candles(10))
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_returns_valid_signal(self):
        ctx = _base_context(candles=_make_candles(50))
        sig = await self.agent.analyze(ctx)
        assert isinstance(sig, AgentSignal)
        assert 0.0 <= sig.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_volatility_regime_in_supporting_data(self):
        ctx = _base_context(candles=_make_candles(50))
        sig = await self.agent.analyze(ctx)
        assert "volatility_regime" in sig.supporting_data


# ---------------------------------------------------------------------------
# SentimentAgent tests
# ---------------------------------------------------------------------------

class TestSentimentAgent:
    agent = SentimentAgent()

    def test_agent_id(self):
        assert self.agent.agent_id == "sentiment"

    def test_required_data(self):
        assert "candles" in self.agent.required_data()

    def test_weight_ranging_highest(self):
        w_range = self.agent.get_weight(MarketRegime.RANGING)
        w_trend = self.agent.get_weight(MarketRegime.TRENDING_UP)
        assert w_range >= w_trend

    @pytest.mark.asyncio
    async def test_insufficient_candles_neutral(self):
        ctx = _base_context(candles=_make_candles(10))
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_returns_valid_signal(self):
        ctx = _base_context(candles=_make_candles(50))
        sig = await self.agent.analyze(ctx)
        assert isinstance(sig, AgentSignal)
        assert 0.0 <= sig.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_cot_data_accepted(self):
        ctx = _base_context(
            candles=_make_candles(50),
            metadata={"cot_data": {"net_noncommercial": 50000}},
        )
        sig = await self.agent.analyze(ctx)
        assert isinstance(sig, AgentSignal)

    @pytest.mark.asyncio
    async def test_supporting_data_has_rsi(self):
        ctx = _base_context(candles=_make_candles(50))
        sig = await self.agent.analyze(ctx)
        assert "rsi" in sig.supporting_data or sig.confidence == 0.0


# ---------------------------------------------------------------------------
# SmartMoneyAgent tests
# ---------------------------------------------------------------------------

class TestSmartMoneyAgent:
    agent = SmartMoneyAgent()

    def test_agent_id(self):
        assert self.agent.agent_id == "smart_money"

    def test_required_data(self):
        assert "candles" in self.agent.required_data()

    def test_weight_trending_high(self):
        assert self.agent.get_weight(MarketRegime.TRENDING_UP) >= 0.75

    @pytest.mark.asyncio
    async def test_insufficient_candles_neutral(self):
        ctx = _base_context(candles=_make_candles(10))
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_returns_valid_signal(self):
        ctx = _base_context(candles=_make_candles(100))
        sig = await self.agent.analyze(ctx)
        assert isinstance(sig, AgentSignal)
        assert 0.0 <= sig.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_supporting_data_has_smc_fields(self):
        ctx = _base_context(candles=_make_candles(100))
        sig = await self.agent.analyze(ctx)
        data = sig.supporting_data
        assert "equilibrium" in data
        assert "in_discount" in data
        assert "long_score" in data


# ---------------------------------------------------------------------------
# RiskAgent tests
# ---------------------------------------------------------------------------

class TestRiskAgent:
    agent = RiskAgent()

    def test_agent_id(self):
        assert self.agent.agent_id == "risk_ai"

    def test_required_data(self):
        assert "candles" in self.agent.required_data()
        assert "metadata" in self.agent.required_data()

    def test_weight_high_in_all_regimes(self):
        for regime in MarketRegime:
            assert self.agent.get_weight(regime) >= 0.80

    @pytest.mark.asyncio
    async def test_high_spread_vetoes(self):
        ctx = _base_context(
            candles=_make_candles(20),
            metadata={"spread": 10.0},
        )
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL
        assert "spread" in sig.reasoning.lower()

    @pytest.mark.asyncio
    async def test_high_drawdown_vetoes(self):
        ctx = _base_context(
            candles=_make_candles(20),
            metadata={"current_drawdown_pct": 6.0},
        )
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_imminent_news_vetoes(self):
        now = datetime.now(tz=timezone.utc)
        ctx = _base_context(
            candles=_make_candles(20),
            metadata={
                "news_events": [
                    {
                        "name": "NFP",
                        "time": (now + timedelta(minutes=10)).isoformat(),
                        "impact": "high",
                    }
                ]
            },
        )
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_past_news_no_veto(self):
        past = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        ctx = _base_context(
            candles=_make_candles(20),
            metadata={
                "spread": 1.5,
                "news_events": [
                    {"name": "CPI", "time": past.isoformat(), "impact": "high"}
                ],
                "market_bias": "long",
            },
        )
        sig = await self.agent.analyze(ctx)
        assert sig.direction != SignalDirection.NEUTRAL or sig.confidence < 0.80

    @pytest.mark.asyncio
    async def test_too_many_positions_vetoes(self):
        ctx = _base_context(
            candles=_make_candles(20),
            metadata={"open_positions": [{"id": i} for i in range(5)]},
        )
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_clean_environment_passes(self):
        ctx = _base_context(
            candles=_make_candles(20),
            metadata={
                "spread": 1.2,
                "current_drawdown_pct": 1.0,
                "open_positions": [],
                "market_bias": "long",
            },
        )
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.LONG
        assert sig.confidence > 0


# ---------------------------------------------------------------------------
# EntryAgent tests
# ---------------------------------------------------------------------------

class TestEntryAgent:
    agent = EntryAgent()

    def test_agent_id(self):
        assert self.agent.agent_id == "entry_ai"

    def test_required_data(self):
        assert "candles" in self.agent.required_data()
        assert "ticks" in self.agent.required_data()

    def test_weight_high_all_regimes(self):
        for regime in MarketRegime:
            assert self.agent.get_weight(regime) >= 0.75

    @pytest.mark.asyncio
    async def test_insufficient_candles_neutral(self):
        ctx = _base_context(candles=_make_candles(5))
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_returns_valid_signal(self):
        ctx = _base_context(candles=_make_candles(50))
        sig = await self.agent.analyze(ctx)
        assert isinstance(sig, AgentSignal)
        assert 0.0 <= sig.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_supporting_data_has_rr(self):
        ctx = _base_context(candles=_make_candles(50))
        sig = await self.agent.analyze(ctx)
        assert "rr_long" in sig.supporting_data
        assert "rr_short" in sig.supporting_data

    def test_custom_rr_ratio(self):
        agent = EntryAgent(min_rr_ratio=2.5)
        assert agent._min_rr_ratio == 2.5


# ---------------------------------------------------------------------------
# ExitAgent tests
# ---------------------------------------------------------------------------

class TestExitAgent:
    agent = ExitAgent()

    def test_agent_id(self):
        assert self.agent.agent_id == "exit_ai"

    def test_required_data(self):
        assert "candles" in self.agent.required_data()
        assert "metadata" in self.agent.required_data()

    def test_weight_high_all_regimes(self):
        for regime in MarketRegime:
            assert self.agent.get_weight(regime) >= 0.75

    @pytest.mark.asyncio
    async def test_trail_stop_triggers_exit(self):
        ctx = _base_context(
            candles=_make_candles(30),
            metadata={
                "position_direction": "long",
                "trail_stop_price": 999999.0,  # above market
            },
        )
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.SHORT  # exit long = short signal

    @pytest.mark.asyncio
    async def test_tp_reached_triggers_exit(self):
        candles = _make_candles(30)
        last_price = candles[-1]["close"]
        ctx = _base_context(
            candles=candles,
            metadata={
                "position_direction": "long",
                "take_profit_price": last_price - 0.001,  # below market → TP hit
            },
        )
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.SHORT

    @pytest.mark.asyncio
    async def test_no_exit_conditions_returns_neutral(self):
        # Build candles with deliberately alternating bull/bear to suppress reversal detection.
        # 30 candles, alternating open>close and open<close so _detect_reversal_pattern stays quiet.
        candles = _make_candles(30, seed=200)
        for i in range(len(candles)):
            c = candles[i]
            if i % 2 == 0:
                # Make bullish
                if c["close"] < c["open"]:
                    c["open"], c["close"] = c["close"], c["open"]
            else:
                # Make bearish
                if c["close"] > c["open"]:
                    c["open"], c["close"] = c["close"], c["open"]
        # Verify no run of 3 same-direction candles in last 3
        ctx = _base_context(
            candles=candles,
            metadata={"position_direction": "long"},
        )
        sig = await self.agent.analyze(ctx)
        # With alternating candles, reversal detector fires on doji or is suppressed
        # The expected behavior: no external exit triggers → stays neutral
        assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_session_end_triggers_exit(self):
        future = datetime.now(tz=timezone.utc) + timedelta(minutes=15)
        ctx = _base_context(
            candles=_make_candles(30),
            metadata={
                "position_direction": "short",
                "session_end_time": future.isoformat(),
            },
        )
        sig = await self.agent.analyze(ctx)
        assert sig.direction == SignalDirection.LONG  # exit short = long signal


# ---------------------------------------------------------------------------
# ConsensusEngine tests
# ---------------------------------------------------------------------------

class TestConsensusEngine:
    engine = ConsensusEngine(min_agents=3, agreement_threshold=0.60)

    def _make_signal(
        self,
        agent_id: str,
        direction: SignalDirection,
        confidence: float = 0.70,
    ) -> AgentSignal:
        return AgentSignal(
            agent_id=agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=f"Test signal from {agent_id}",
        )

    @pytest.mark.asyncio
    async def test_insufficient_agents_not_actionable(self):
        signals = [self._make_signal("a", SignalDirection.LONG)]
        result = await self.engine.aggregate(signals, MarketRegime.RANGING)
        assert not result.is_actionable
        assert result.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_unanimous_long_actionable(self):
        signals = [
            self._make_signal(f"agent_{i}", SignalDirection.LONG, 0.80)
            for i in range(5)
        ]
        weights = {f"agent_{i}": 0.80 for i in range(5)}
        result = await self.engine.aggregate(signals, MarketRegime.TRENDING_UP, weights)
        assert result.direction == SignalDirection.LONG
        assert result.is_actionable
        assert result.agreement_ratio >= 0.60

    @pytest.mark.asyncio
    async def test_unanimous_short_actionable(self):
        signals = [
            self._make_signal(f"agent_{i}", SignalDirection.SHORT, 0.75)
            for i in range(5)
        ]
        result = await self.engine.aggregate(signals, MarketRegime.TRENDING_DOWN)
        assert result.direction == SignalDirection.SHORT
        assert result.is_actionable

    @pytest.mark.asyncio
    async def test_conflict_reduces_actionability(self):
        signals = [
            self._make_signal("a1", SignalDirection.LONG, 0.80),
            self._make_signal("a2", SignalDirection.LONG, 0.80),
            self._make_signal("a3", SignalDirection.SHORT, 0.80),
            self._make_signal("a4", SignalDirection.SHORT, 0.80),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.RANGING)
        # Tied → NEUTRAL or low agreement
        assert result.agreement_ratio < 0.80

    @pytest.mark.asyncio
    async def test_weighted_vote_respects_weights(self):
        signals = [
            self._make_signal("heavy_long", SignalDirection.LONG, 0.90),
            self._make_signal("light_short1", SignalDirection.SHORT, 0.90),
            self._make_signal("light_short2", SignalDirection.SHORT, 0.90),
            self._make_signal("light_short3", SignalDirection.SHORT, 0.90),
        ]
        weights = {
            "heavy_long": 10.0,
            "light_short1": 1.0,
            "light_short2": 1.0,
            "light_short3": 1.0,
        }
        result = await self.engine.aggregate(signals, MarketRegime.TRENDING_UP, weights)
        assert result.direction == SignalDirection.LONG

    @pytest.mark.asyncio
    async def test_result_has_agent_breakdown(self):
        signals = [
            self._make_signal(f"agent_{i}", SignalDirection.LONG)
            for i in range(4)
        ]
        result = await self.engine.aggregate(signals, MarketRegime.RANGING)
        assert len(result.agent_breakdown) == 4
        for sig in signals:
            assert sig.agent_id in result.agent_breakdown

    @pytest.mark.asyncio
    async def test_consensus_result_has_reasoning(self):
        signals = [
            self._make_signal(f"a{i}", SignalDirection.LONG, 0.75)
            for i in range(4)
        ]
        result = await self.engine.aggregate(signals, MarketRegime.RANGING)
        assert len(result.reasoning) > 20
        assert "LONG" in result.reasoning.upper() or "NEUTRAL" in result.reasoning.upper()

    @pytest.mark.asyncio
    async def test_neutral_only_agents_not_actionable(self):
        signals = [
            self._make_signal(f"n{i}", SignalDirection.NEUTRAL, 0.80)
            for i in range(5)
        ]
        result = await self.engine.aggregate(signals, MarketRegime.RANGING)
        assert not result.is_actionable

    @pytest.mark.asyncio
    async def test_empty_signals(self):
        result = await self.engine.aggregate([], MarketRegime.RANGING)
        assert not result.is_actionable
        assert result.direction == SignalDirection.NEUTRAL


# ---------------------------------------------------------------------------
# TradeExplainer tests
# ---------------------------------------------------------------------------

class TestTradeExplainer:
    explainer = TradeExplainer()

    def _make_consensus(self, direction: SignalDirection = SignalDirection.LONG) -> ConsensusResult:
        breakdown = {
            f"agent_{i}": AgentSignal(
                agent_id=f"agent_{i}",
                direction=direction,
                confidence=0.75,
                reasoning=f"Test reasoning for agent_{i}",
            )
            for i in range(3)
        }
        breakdown["risk_ai"] = AgentSignal(
            agent_id="risk_ai",
            direction=direction,
            confidence=0.80,
            reasoning="Risk acceptable",
        )
        return ConsensusResult(
            direction=direction,
            confidence=0.75,
            agreement_ratio=0.80,
            conflict_ratio=0.05,
            supporting_agents=list(breakdown.keys()),
            conflicting_agents=[],
            is_actionable=True,
            reasoning="Test consensus reasoning",
            agent_breakdown=breakdown,
        )

    def test_explain_decision_returns_explanation(self):
        consensus = self._make_consensus()
        ctx = _base_context()
        risk = {"spread": 1.5, "drawdown": 2.0}
        explanation = self.explainer.explain_decision(consensus, ctx, risk)
        assert isinstance(explanation, TradeExplanation)

    def test_explanation_has_decision_id(self):
        explanation = self.explainer.explain_decision(
            self._make_consensus(), _base_context(), {}
        )
        assert isinstance(explanation.decision_id, UUID)

    def test_explanation_direction_matches_consensus(self):
        explanation = self.explainer.explain_decision(
            self._make_consensus(SignalDirection.SHORT), _base_context(), {}
        )
        assert explanation.direction == "SHORT"

    def test_explanation_has_timestamp(self):
        explanation = self.explainer.explain_decision(
            self._make_consensus(), _base_context(), {}
        )
        assert isinstance(explanation.timestamp, datetime)

    def test_supporting_signals_populated(self):
        explanation = self.explainer.explain_decision(
            self._make_consensus(), _base_context(), {}
        )
        assert len(explanation.supporting_signals) > 0

    def test_risk_assessment_passed_through(self):
        risk = {"spread": 2.5, "drawdown_pct": 1.0, "special_key": "value"}
        explanation = self.explainer.explain_decision(
            self._make_consensus(), _base_context(), risk
        )
        assert explanation.risk_assessment["special_key"] == "value"

    def test_market_regime_in_explanation(self):
        ctx = _base_context(regime=MarketRegime.TRENDING_UP)
        explanation = self.explainer.explain_decision(
            self._make_consensus(), ctx, {}
        )
        assert "trending_up" in explanation.market_regime

    def test_confidence_score_bounded(self):
        explanation = self.explainer.explain_decision(
            self._make_consensus(), _base_context(), {}
        )
        assert 0.0 <= explanation.confidence_score <= 1.0


# ---------------------------------------------------------------------------
# AIOrchestrator tests
# ---------------------------------------------------------------------------

class TestAIOrchestrator:
    @pytest.mark.asyncio
    async def test_orchestrator_instantiates_with_9_agents(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        assert len(orch.list_agents()) == 9

    @pytest.mark.asyncio
    async def test_all_agent_ids_registered(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        expected_ids = {
            "market_structure", "trend", "liquidity", "volatility",
            "sentiment", "smart_money", "risk_ai", "entry_ai", "exit_ai",
        }
        registered_ids = {a.agent_id for a in orch.list_agents()}
        assert expected_ids == registered_ids

    @pytest.mark.asyncio
    async def test_analyze_returns_orchestrator_result(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        ctx = _base_context(candles=_make_candles(300))
        result = await orch.analyze(ctx)
        assert isinstance(result, OrchestratorResult)

    @pytest.mark.asyncio
    async def test_analyze_result_has_consensus(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        ctx = _base_context(candles=_make_candles(300))
        result = await orch.analyze(ctx)
        assert isinstance(result.consensus, ConsensusResult)

    @pytest.mark.asyncio
    async def test_analyze_result_has_explanation(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        ctx = _base_context(candles=_make_candles(300))
        result = await orch.analyze(ctx)
        assert isinstance(result.explanation, TradeExplanation)

    @pytest.mark.asyncio
    async def test_analyze_agent_signals_dict_populated(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        ctx = _base_context(candles=_make_candles(300))
        result = await orch.analyze(ctx)
        assert isinstance(result.agent_signals, dict)
        assert len(result.agent_signals) > 0

    @pytest.mark.asyncio
    async def test_should_trade_is_bool(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        ctx = _base_context(candles=_make_candles(300))
        result = await orch.analyze(ctx)
        assert isinstance(result.should_trade, bool)

    @pytest.mark.asyncio
    async def test_explain_last_decision_returns_explanation(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        ctx = _base_context(candles=_make_candles(300))
        await orch.analyze(ctx)
        explanation = await orch.explain_last_decision()
        assert isinstance(explanation, TradeExplanation)

    @pytest.mark.asyncio
    async def test_explain_last_decision_none_before_analyze(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        explanation = await orch.explain_last_decision()
        assert explanation is None

    @pytest.mark.asyncio
    async def test_register_unregister_agent(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        initial_count = len(orch.list_agents())
        new_agent = MarketStructureAgent()
        new_agent.agent_id = "test_duplicate"
        orch.register_agent(new_agent)
        assert len(orch.list_agents()) == initial_count + 1
        orch.unregister_agent("test_duplicate")
        assert len(orch.list_agents()) == initial_count

    @pytest.mark.asyncio
    async def test_risk_veto_prevents_trade(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        ctx = _base_context(
            candles=_make_candles(300),
            metadata={"spread": 50.0},  # extreme spread = risk veto
        )
        result = await orch.analyze(ctx)
        assert not result.should_trade

    @pytest.mark.asyncio
    async def test_disabled_agent_not_run(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        orch.get_agent("trend").disable()
        ctx = _base_context(candles=_make_candles(300))
        result = await orch.analyze(ctx)
        assert "trend" not in result.agent_signals
        orch.get_agent("trend").enable()

    @pytest.mark.asyncio
    async def test_no_agents_enabled_returns_neutral(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        for agent in orch.list_agents():
            agent.disable()
        ctx = _base_context(candles=_make_candles(50))
        result = await orch.analyze(ctx)
        assert result.consensus.direction == SignalDirection.NEUTRAL
        assert not result.should_trade

    @pytest.mark.asyncio
    async def test_concurrent_execution_completes(self):
        orch = AIOrchestrator(uow_factory=MagicMock())
        ctx = _base_context(candles=_make_candles(300))
        # Run analyze 3 times concurrently
        results = await asyncio.gather(
            orch.analyze(ctx), orch.analyze(ctx), orch.analyze(ctx)
        )
        assert len(results) == 3
        for r in results:
            assert isinstance(r, OrchestratorResult)


# ---------------------------------------------------------------------------
# Edge case and integration tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_candles_all_agents_neutral(self):
        ctx = _base_context(candles=[])
        agents = [
            MarketStructureAgent(), TrendAgent(), LiquidityAgent(),
            VolatilityAgent(), SentimentAgent(), SmartMoneyAgent(),
        ]
        for agent in agents:
            sig = await agent.analyze(ctx)
            assert sig.direction == SignalDirection.NEUTRAL, f"{agent.agent_id} not neutral on empty candles"

    @pytest.mark.asyncio
    async def test_single_candle_all_agents_neutral(self):
        ctx = _base_context(candles=_make_candles(1))
        agents = [MarketStructureAgent(), TrendAgent(), LiquidityAgent()]
        for agent in agents:
            sig = await agent.analyze(ctx)
            assert sig.direction == SignalDirection.NEUTRAL

    @pytest.mark.asyncio
    async def test_nan_volume_handled(self):
        candles = _make_candles(50)
        for c in candles:
            c["volume"] = None
        ctx = _base_context(candles=candles)
        agent = EntryAgent()
        sig = await agent.analyze(ctx)
        assert isinstance(sig, AgentSignal)

    @pytest.mark.asyncio
    async def test_all_agents_return_agent_id_matching_class(self):
        candles = _make_candles(300)
        ctx = _base_context(candles=candles)
        agents_and_ids = [
            (MarketStructureAgent(), "market_structure"),
            (TrendAgent(), "trend"),
            (LiquidityAgent(), "liquidity"),
            (VolatilityAgent(), "volatility"),
            (SentimentAgent(), "sentiment"),
            (SmartMoneyAgent(), "smart_money"),
            (RiskAgent(), "risk_ai"),
            (EntryAgent(), "entry_ai"),
            (ExitAgent(), "exit_ai"),
        ]
        for agent, expected_id in agents_and_ids:
            sig = await agent.analyze(ctx)
            assert sig.agent_id == expected_id

    @pytest.mark.asyncio
    async def test_consensus_with_mixed_signals(self):
        engine = ConsensusEngine(min_agents=3, agreement_threshold=0.60)
        signals = [
            AgentSignal("a1", SignalDirection.LONG, 0.85, "Long signal"),
            AgentSignal("a2", SignalDirection.LONG, 0.75, "Long signal"),
            AgentSignal("a3", SignalDirection.LONG, 0.80, "Long signal"),
            AgentSignal("a4", SignalDirection.NEUTRAL, 0.50, "Neutral"),
            AgentSignal("a5", SignalDirection.SHORT, 0.40, "Short signal"),
        ]
        result = await engine.aggregate(signals, MarketRegime.TRENDING_UP)
        assert result.direction == SignalDirection.LONG
        assert "a1" in result.supporting_agents
        assert "a5" in result.conflicting_agents
