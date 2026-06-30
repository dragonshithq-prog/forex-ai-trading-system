"""AI Orchestrator - coordinate agents, aggregate signals, produce recommendations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from forex_trading.ai.agents.base import (
    AgentSignal,
    BaseAgent,
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
from forex_trading.ai.xai.explainer import TradeExplanation, TradeExplainer
from forex_trading.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


@dataclass
class OrchestratorResult:
    """Complete output from the AI orchestrator."""

    consensus: ConsensusResult
    explanation: TradeExplanation
    should_trade: bool
    agent_signals: dict[str, AgentSignal]
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class AIOrchestrator:
    """
    Orchestrate multiple AI agents to produce trade recommendations.

    Responsibilities:
    - Manage agent registry and lifecycle
    - Distribute market context to agents concurrently
    - Aggregate agent signals using weighted consensus
    - Detect and resolve conflicts
    - Generate XAI (Explainable AI) explanations
    """

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._consensus_engine = ConsensusEngine(
            min_agents=settings.AI_MIN_AGENTS,
            agreement_threshold=settings.AI_MIN_AGREEMENT_THRESHOLD,
        )
        self._explainer = TradeExplainer()
        self._last_explanation: TradeExplanation | None = None
        self._consensus_history: list[ConsensusResult] = []

        self._register_default_agents()

    def _register_default_agents(self) -> None:
        """Register all 9 production agents."""
        default_agents: list[BaseAgent] = [
            MarketStructureAgent(),
            TrendAgent(),
            LiquidityAgent(),
            VolatilityAgent(),
            SentimentAgent(),
            SmartMoneyAgent(),
            RiskAgent(),
            EntryAgent(),
            ExitAgent(),
        ]
        for agent in default_agents:
            self.register_agent(agent)

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an AI agent."""
        self._agents[agent.agent_id] = agent
        logger.info("agent_registered", agent_id=agent.agent_id, name=agent.name)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an AI agent by ID."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info("agent_unregistered", agent_id=agent_id)

    def get_agent(self, agent_id: str) -> BaseAgent | None:
        """Return a registered agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[BaseAgent]:
        """Return all registered agents."""
        return list(self._agents.values())

    async def analyze(self, context: MarketContext) -> OrchestratorResult:
        """
        Run all enabled agents concurrently and produce a consensus recommendation.

        Args:
            context: Current market context with candles, ticks, metadata.

        Returns:
            OrchestratorResult with consensus, explanation, and trade decision.
        """
        log = logger.bind(symbol=context.symbol, timeframe=context.timeframe, regime=context.regime.value)

        enabled_agents = [a for a in self._agents.values() if a.is_enabled]

        if not enabled_agents:
            log.error("no_agents_enabled")
            neutral_result = await self._empty_result(context)
            return neutral_result

        # Run all agents concurrently
        tasks = {
            agent.agent_id: agent.analyze(context)
            for agent in enabled_agents
        }

        task_results = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )

        agent_signals: dict[str, AgentSignal] = {}
        signals: list[AgentSignal] = []

        for agent_id, result in zip(tasks.keys(), task_results):
            if isinstance(result, Exception):
                log.error(
                    "agent_failed",
                    agent_id=agent_id,
                    error=str(result),
                    error_type=type(result).__name__,
                )
                continue
            agent_signals[agent_id] = result
            signals.append(result)

        # Build per-agent weight map for the current regime
        weights: dict[str, float] = {}
        for agent in enabled_agents:
            if agent.agent_id in agent_signals:
                weights[agent.agent_id] = agent.get_weight(context.regime)

        # Aggregate via consensus engine
        consensus = await self._consensus_engine.aggregate(
            signals=signals,
            regime=context.regime,
            weights=weights,
        )

        self._consensus_history.append(consensus)

        # Build risk assessment dict for explainer
        risk_assessment = self._build_risk_assessment(agent_signals, context)

        # Generate explanation
        explanation = self._explainer.explain_decision(
            consensus=consensus,
            context=context,
            risk_assessment=risk_assessment,
        )
        self._last_explanation = explanation

        should_trade = consensus.is_actionable and not self._risk_vetoed(agent_signals)

        log.info(
            "orchestrator_result",
            direction=consensus.direction.value,
            confidence=round(consensus.confidence, 3),
            agreement=round(consensus.agreement_ratio, 3),
            is_actionable=consensus.is_actionable,
            should_trade=should_trade,
            agents_ran=len(signals),
            agents_failed=len(enabled_agents) - len(signals),
        )

        return OrchestratorResult(
            consensus=consensus,
            explanation=explanation,
            should_trade=should_trade,
            agent_signals=agent_signals,
        )

    async def explain_last_decision(self) -> TradeExplanation | None:
        """Return the explanation for the most recent decision, or None."""
        return self._last_explanation

    def _risk_vetoed(self, agent_signals: dict[str, AgentSignal]) -> bool:
        """
        Return True if the risk agent produced a NEUTRAL signal (veto).

        A NEUTRAL from risk_ai with high confidence means the trade is blocked.
        """
        risk_signal = agent_signals.get("risk_ai")
        if risk_signal is None:
            return False
        return (
            risk_signal.direction == SignalDirection.NEUTRAL
            and risk_signal.confidence >= 0.80
        )

    def _build_risk_assessment(
        self,
        agent_signals: dict[str, AgentSignal],
        context: MarketContext,
    ) -> dict[str, Any]:
        """Compile risk metrics from the risk agent signal and context metadata."""
        risk_signal = agent_signals.get("risk_ai")
        metadata = context.metadata or {}

        assessment: dict[str, Any] = {
            "spread": metadata.get("spread"),
            "current_drawdown_pct": metadata.get("current_drawdown_pct"),
            "open_positions": len(metadata.get("open_positions", [])),
            "news_events": metadata.get("news_events", []),
            "risk_vetoed": self._risk_vetoed(agent_signals),
        }

        if risk_signal:
            assessment["risk_agent_direction"] = risk_signal.direction.value
            assessment["risk_agent_confidence"] = risk_signal.confidence
            assessment["risk_agent_reasoning"] = risk_signal.reasoning
            assessment["risk_flags"] = risk_signal.supporting_data.get("red_flags", [])

        return assessment

    async def _empty_result(self, context: MarketContext) -> OrchestratorResult:
        """Return a neutral result when no agents are available."""
        from forex_trading.ai.consensus.engine import ConsensusResult

        consensus = ConsensusResult(
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            agreement_ratio=0.0,
            conflict_ratio=1.0,
            supporting_agents=[],
            conflicting_agents=[],
            is_actionable=False,
            reasoning="No agents enabled.",
            agent_breakdown={},
        )
        explanation = self._explainer.explain_decision(
            consensus=consensus,
            context=context,
            risk_assessment={"error": "No agents enabled"},
        )
        return OrchestratorResult(
            consensus=consensus,
            explanation=explanation,
            should_trade=False,
            agent_signals={},
        )
