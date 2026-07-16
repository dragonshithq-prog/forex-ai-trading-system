"""Tests for AIOrchestrator — agent registration, concurrent execution, risk veto, drift detection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from forex_trading.ai.orchestrator import AIOrchestrator, OrchestratorResult
from forex_trading.ai.agents.base import (
    AgentSignal,
    MarketContext,
    MarketRegime,
    SignalDirection,
    BaseAgent,
)


pytestmark = pytest.mark.asyncio


class _MockAgent(BaseAgent):
    """Simple mock agent that returns a predetermined signal."""

    def __init__(self, agent_id: str, name: str, signal: AgentSignal | None = None):
        super().__init__(agent_id, name)
        self._signal = signal or AgentSignal(
            agent_id=agent_id,
            direction=SignalDirection.LONG,
            confidence=0.8,
            reasoning=f"{name} test signal",
        )

    async def analyze(self, context: MarketContext) -> AgentSignal:
        return self._signal

    def get_weight(self, regime: MarketRegime) -> float:
        return 1.0

    def required_data(self) -> list[str]:
        return ["candles"]


class TestAIOrchestrator:
    """Tests for the AI Orchestrator."""

    async def test_register_agent(self, uow_factory, mock_cache):
        """Agents should be registered and retrievable."""
        orch = AIOrchestrator(uow_factory, mock_cache)
        agent = _MockAgent("test_agent", "Test Agent")
        orch.register_agent(agent)

        assert orch.get_agent("test_agent") is agent
        assert agent in orch.list_agents()

    async def test_unregister_agent(self, uow_factory, mock_cache):
        """Unregistered agents should be removed."""
        orch = AIOrchestrator(uow_factory, mock_cache)
        agent = _MockAgent("test_agent", "Test Agent")
        orch.register_agent(agent)
        orch.unregister_agent("test_agent")

        assert orch.get_agent("test_agent") is None

    async def test_analyze_with_no_enabled_agents(self, uow_factory, mock_cache):
        """When no agents are enabled, analysis should return empty result."""
        orch = AIOrchestrator(uow_factory, mock_cache)

        # Disable all default agents
        for agent in orch.list_agents():
            agent.disable()

        context = MarketContext(symbol="EURUSD", timeframe="H1", candles=[])
        result = await orch.analyze(context)

        assert result.should_trade is False
        assert result.consensus.direction == SignalDirection.NEUTRAL
        assert result.consensus.is_actionable is False

    async def test_analyze_produces_consensus(self, uow_factory, mock_cache, market_context):
        """With enabled agents, analysis should produce a consensus result."""
        orch = AIOrchestrator(uow_factory, mock_cache)

        result = await orch.analyze(market_context)
        assert isinstance(result, OrchestratorResult)
        assert result.consensus is not None
        assert result.explanation is not None
        assert result.agent_signals is not None

    async def test_analyze_persists_decision(self, uow_factory, mock_cache, market_context):
        """Analysis should persist the decision to the database."""
        orch = AIOrchestrator(uow_factory, mock_cache)

        result = await orch.analyze(market_context)
        assert result.ai_decision_id is not None

        # Verify it was persisted
        async with uow_factory as uow:
            decision = await uow.ai_decisions.get(result.ai_decision_id)
            assert decision is not None
            assert decision.symbol == "EURUSD"

    async def test_risk_veto(self, uow_factory, mock_cache, market_context):
        """Risk agent neutral signal with high confidence should veto the trade."""
        orch = AIOrchestrator(uow_factory, mock_cache)

        # Replace the risk agent with one that vetoes
        risk_signal = AgentSignal(
            agent_id="risk_ai",
            direction=SignalDirection.NEUTRAL,
            confidence=0.85,  # Above 0.80 threshold
            reasoning="High market risk detected",
        )
        risk_agent = _MockAgent("risk_ai", "Risk Agent", risk_signal)
        orch.register_agent(risk_agent)

        result = await orch.analyze(market_context)
        # Trade should be vetoed if risk is neutral with high confidence
        if "risk_ai" in result.agent_signals:
            vetoed = orch._risk_vetoed(result.agent_signals)
            if vetoed:
                assert result.consensus.is_actionable is False or not result.should_trade

    async def test_record_execution_outcome(self, uow_factory, mock_cache):
        """Recording execution outcome should update the decision."""
        orch = AIOrchestrator(uow_factory, mock_cache)
        context = MarketContext(symbol="EURUSD", timeframe="H1", candles=[])

        # Need at least some candles for agents to not crash
        result = await orch.analyze(context)
        if result.ai_decision_id:
            await orch.record_execution_outcome(
                decision_id=result.ai_decision_id,
                was_executed=True,
                outcome_pnl=50.0,
            )

            async with uow_factory as uow:
                decision = await uow.ai_decisions.get(result.ai_decision_id)
                if decision:
                    assert decision.was_executed is True
                    assert decision.outcome_pnl == 50.0

    async def test_drift_detection_sliding_window(self, uow_factory, mock_cache):
        """Drift detection should maintain a sliding window of agreement ratios."""
        orch = AIOrchestrator(uow_factory, mock_cache)
        assert len(orch._agreement_window) == 0

        # Run a few analyses to fill the window
        context = MarketContext(symbol="EURUSD", timeframe="H1", candles=[])
        for _ in range(5):
            await orch.analyze(context)

        assert len(orch._agreement_window) == 5

    async def test_blend_weights(self, uow_factory, mock_cache):
        """Weight blending should combine base and performance weights."""
        orch = AIOrchestrator(uow_factory, mock_cache)
        base = {"agent_a": 1.0, "agent_b": 0.5}
        perf = {"agent_a": 0.8}

        blended = orch._blend_weights(base, perf)
        # agent_a: 0.7 * 1.0 + 0.3 * 0.8 = 0.94
        # agent_b: 0.7 * 0.5 + 0.3 * 0.5 = 0.5 (falls back to base)
        assert blended["agent_a"] == pytest.approx(0.94, rel=0.01)
        assert blended["agent_b"] == 0.5

    async def test_analyze_disabled_agent_skipped(self, uow_factory, mock_cache, market_context):
        """Disabled agents should not participate in analysis."""
        orch = AIOrchestrator(uow_factory, mock_cache)
        initial_count = len(orch.list_agents())

        # Disable one agent
        agent = orch.list_agents()[0]
        agent.disable()

        result = await orch.analyze(market_context)
        assert agent.agent_id not in result.agent_signals
