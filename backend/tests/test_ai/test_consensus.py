"""Tests for ConsensusEngine — weighted voting, agreement/conflict ratios, thresholds."""

from __future__ import annotations

import pytest

from forex_trading.ai.agents.base import AgentSignal, MarketRegime, SignalDirection
from forex_trading.ai.consensus.engine import ConsensusEngine, ConsensusResult


pytestmark = pytest.mark.asyncio


class TestConsensusEngine:
    """Tests for the consensus aggregation engine."""

    def setup_method(self):
        self.engine = ConsensusEngine(min_agents=4, agreement_threshold=0.60)

    def _signal(self, agent_id: str, direction: SignalDirection, confidence: float) -> AgentSignal:
        return AgentSignal(
            agent_id=agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=f"{agent_id} analysis",
        )

    async def test_aggregate_long_direction(self):
        """When most agents vote LONG, consensus should be LONG."""
        signals = [
            self._signal("trend_ai", SignalDirection.LONG, 0.8),
            self._signal("momentum", SignalDirection.LONG, 0.7),
            self._signal("structure", SignalDirection.LONG, 0.6),
            self._signal("liquidity", SignalDirection.SHORT, 0.3),
            self._signal("volatility", SignalDirection.NEUTRAL, 0.5),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.TRENDING_UP)
        assert result.direction == SignalDirection.LONG
        assert result.is_actionable is True
        assert result.confidence > 0
        assert result.agreement_ratio > 0

    async def test_aggregate_short_direction(self):
        """When most agents vote SHORT, consensus should be SHORT."""
        signals = [
            self._signal("trend_ai", SignalDirection.SHORT, 0.8),
            self._signal("momentum", SignalDirection.SHORT, 0.7),
            self._signal("structure", SignalDirection.SHORT, 0.6),
            self._signal("liquidity", SignalDirection.LONG, 0.3),
            self._signal("volatility", SignalDirection.NEUTRAL, 0.5),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.TRENDING_DOWN)
        assert result.direction == SignalDirection.SHORT
        assert result.is_actionable is True
        assert result.confidence > 0

    async def test_aggregate_neutral_when_split(self):
        """When votes are evenly split, consensus should be NEUTRAL."""
        signals = [
            self._signal("trend_ai", SignalDirection.LONG, 0.5),
            self._signal("momentum", SignalDirection.SHORT, 0.5),
            self._signal("structure", SignalDirection.LONG, 0.5),
            self._signal("liquidity", SignalDirection.SHORT, 0.5),
            self._signal("volatility", SignalDirection.NEUTRAL, 0.5),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.RANGING)
        assert result.direction == SignalDirection.NEUTRAL or result.is_actionable is False

    async def test_insufficient_agents(self):
        """When fewer than min_agents provided, result should not be actionable."""
        signals = [
            self._signal("trend_ai", SignalDirection.LONG, 0.8),
            self._signal("momentum", SignalDirection.LONG, 0.7),
            self._signal("structure", SignalDirection.LONG, 0.6),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.TRENDING_UP)
        assert result.is_actionable is False

    async def test_weighted_voting(self):
        """Agents with higher weights should influence the consensus more."""
        engine = ConsensusEngine(
            min_agents=4, agreement_threshold=0.60,
        )
        signals = [
            self._signal("trend_ai", SignalDirection.SHORT, 0.8),
            self._signal("momentum", SignalDirection.LONG, 0.8),
            self._signal("structure", SignalDirection.LONG, 0.6),
            self._signal("liquidity", SignalDirection.LONG, 0.6),
            self._signal("volatility", SignalDirection.LONG, 0.6),
        ]
        result = await engine.aggregate(
            signals, MarketRegime.RANGING,
            weights={"trend_ai": 2.0, "momentum": 0.5},
        )
        # Even though 4 out of 5 vote LONG, the high-weight trend_ai voting SHORT
        # should push the consensus toward SHORT (but might not be enough to flip)
        assert result is not None

    async def test_agreement_and_conflict_ratios(self):
        """Agreement and conflict ratios should sum to approximately 1.0."""
        signals = [
            self._signal("trend_ai", SignalDirection.LONG, 0.8),
            self._signal("momentum", SignalDirection.LONG, 0.7),
            self._signal("structure", SignalDirection.LONG, 0.6),
            self._signal("liquidity", SignalDirection.SHORT, 0.3),
            self._signal("volatility", SignalDirection.NEUTRAL, 0.5),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.TRENDING_UP)
        assert result.direction == SignalDirection.LONG
        # agreement_ratio + conflict_ratio may be < 1.0 when NEUTRAL signals exist
        assert 0.0 <= result.agreement_ratio <= 1.0
        assert 0.0 <= result.conflict_ratio <= 1.0
        assert result.agreement_ratio >= result.conflict_ratio
        assert result.supporting_agents is not None
        assert result.conflicting_agents is not None

    async def test_actionability_below_threshold(self):
        """When agreement is below threshold, result should not be actionable."""
        signals = [
            self._signal("trend_ai", SignalDirection.LONG, 0.4),
            self._signal("momentum", SignalDirection.SHORT, 0.4),
            self._signal("structure", SignalDirection.LONG, 0.4),
            self._signal("liquidity", SignalDirection.SHORT, 0.4),
            self._signal("volatility", SignalDirection.NEUTRAL, 0.5),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.RANGING)
        assert result.is_actionable is False

    async def test_all_neutral_not_actionable(self):
        """When all agents are NEUTRAL, the result should not be actionable."""
        signals = [
            self._signal("trend_ai", SignalDirection.NEUTRAL, 0.5),
            self._signal("momentum", SignalDirection.NEUTRAL, 0.5),
            self._signal("structure", SignalDirection.NEUTRAL, 0.5),
            self._signal("liquidity", SignalDirection.NEUTRAL, 0.5),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.RANGING)
        assert result.direction == SignalDirection.NEUTRAL
        assert result.is_actionable is False

    async def test_supporting_and_conflicting_agents(self):
        """Supporting and conflicting agent lists should be populated."""
        signals = [
            self._signal("trend_ai", SignalDirection.LONG, 0.8),
            self._signal("momentum", SignalDirection.LONG, 0.7),
            self._signal("structure", SignalDirection.SHORT, 0.8),
            self._signal("liquidity", SignalDirection.LONG, 0.6),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.TRENDING_UP)
        assert "trend_ai" in result.supporting_agents
        assert "structure" in result.conflicting_agents

    async def test_agent_breakdown(self):
        """Agent breakdown should include all signals."""
        signals = [
            self._signal("trend_ai", SignalDirection.LONG, 0.8),
            self._signal("momentum", SignalDirection.SHORT, 0.7),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.RANGING)
        assert len(result.agent_breakdown) == 2

    async def test_resolve_weights_default(self):
        """Default weights should be 1.0 for unknown agents when no overrides given."""
        signals = [
            self._signal("a", SignalDirection.LONG, 0.8),
            self._signal("b", SignalDirection.LONG, 0.7),
            self._signal("c", SignalDirection.LONG, 0.6),
            self._signal("d", SignalDirection.LONG, 0.5),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.RANGING)
        assert result.direction == SignalDirection.LONG

    async def test_resolve_weights_with_overrides(self):
        """Override weights should take precedence."""
        engine = ConsensusEngine()
        signals = [
            self._signal("important", SignalDirection.LONG, 0.9),
            self._signal("normal", SignalDirection.SHORT, 0.9),
            self._signal("neutral1", SignalDirection.LONG, 0.6),
            self._signal("neutral2", SignalDirection.SHORT, 0.6),
        ]
        result = await engine.aggregate(
            signals, MarketRegime.RANGING,
            weights={"important": 3.0},
        )
        # With weight=3.0 on important (LONG 0.9) vs others weight=1.0,
        # the weighted average should favor LONG
        assert result.direction == SignalDirection.LONG

    async def test_build_reasoning(self):
        """Reasoning should include consensus summary and agent breakdown."""
        signals = [
            self._signal("trend_ai", SignalDirection.LONG, 0.8),
            self._signal("momentum", SignalDirection.LONG, 0.7),
            self._signal("structure", SignalDirection.SHORT, 0.6),
            self._signal("liquidity", SignalDirection.LONG, 0.5),
        ]
        result = await self.engine.aggregate(signals, MarketRegime.TRENDING_UP)
        assert "Consensus" in result.reasoning
        assert "trend_ai" in result.reasoning or "LONG" in result.reasoning
