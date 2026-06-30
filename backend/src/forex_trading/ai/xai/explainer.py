"""Trade Explainer - generates human-readable XAI explanations for trade decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog

from forex_trading.ai.agents.base import MarketContext, SignalDirection
from forex_trading.ai.consensus.engine import ConsensusResult

logger = structlog.get_logger()


@dataclass
class TradeExplanation:
    """Human-readable explanation of a trade decision."""

    decision_id: UUID
    confidence_score: float
    direction: str
    strategy_selected: str
    entry_rationale: str
    exit_rationale: str
    supporting_signals: list[dict]
    conflicting_signals: list[dict]
    risk_assessment: dict
    session_context: str
    market_regime: str
    timestamp: datetime


class TradeExplainer:
    """
    Produces structured explanations for trade decisions.

    Transforms ConsensusResult + MarketContext + risk assessment into a
    TradeExplanation suitable for audit logging, UI display, and compliance.
    """

    def explain_decision(
        self,
        consensus: ConsensusResult,
        context: MarketContext,
        risk_assessment: dict,
    ) -> TradeExplanation:
        """
        Generate a full explanation for a trade decision.

        Args:
            consensus: Aggregated consensus result from ConsensusEngine.
            context: Market context at decision time.
            risk_assessment: Dict with risk metrics (spread, drawdown, etc.).

        Returns:
            TradeExplanation dataclass with all fields populated.
        """
        log = logger.bind(symbol=context.symbol, direction=consensus.direction.value)

        direction_str = consensus.direction.value.upper()
        strategy = self._select_strategy(consensus, context)
        entry_rationale = self._build_entry_rationale(consensus, context)
        exit_rationale = self._build_exit_rationale(consensus, context)
        session_context = self._describe_session(context)

        supporting: list[dict] = []
        conflicting: list[dict] = []

        for agent_id, signal in consensus.agent_breakdown.items():
            record = {
                "agent": agent_id,
                "direction": signal.direction.value,
                "confidence": round(signal.confidence, 4),
                "reasoning": signal.reasoning,
            }
            if signal.direction == consensus.direction:
                supporting.append(record)
            elif signal.direction != SignalDirection.NEUTRAL:
                conflicting.append(record)

        # Sort by confidence descending
        supporting.sort(key=lambda x: x["confidence"], reverse=True)
        conflicting.sort(key=lambda x: x["confidence"], reverse=True)

        explanation = TradeExplanation(
            decision_id=uuid4(),
            confidence_score=round(consensus.confidence, 4),
            direction=direction_str,
            strategy_selected=strategy,
            entry_rationale=entry_rationale,
            exit_rationale=exit_rationale,
            supporting_signals=supporting,
            conflicting_signals=conflicting,
            risk_assessment=risk_assessment,
            session_context=session_context,
            market_regime=context.regime.value,
            timestamp=datetime.now(tz=timezone.utc),
        )

        log.info(
            "trade_explanation_generated",
            decision_id=str(explanation.decision_id),
            direction=direction_str,
            strategy=strategy,
            supporting_count=len(supporting),
            conflicting_count=len(conflicting),
        )

        return explanation

    def _select_strategy(self, consensus: ConsensusResult, context: MarketContext) -> str:
        """Infer the dominant strategy from contributing agents and regime."""
        regime = context.regime.value

        # Check which agents contributed most
        top_agents = consensus.supporting_agents[:3]

        strategy_hints: dict[str, str] = {
            "smart_money": "Smart Money Concepts (SMC)",
            "market_structure": "Market Structure Break",
            "trend": "Trend Following",
            "entry_ai": "Precision Entry",
            "liquidity": "Liquidity Zone Reversal",
            "sentiment": "Sentiment Mean Reversion",
            "volatility": "Volatility Breakout",
        }

        for agent_id in top_agents:
            if agent_id in strategy_hints:
                return strategy_hints[agent_id]

        return f"Multi-Agent Confluence ({regime})"

    def _build_entry_rationale(self, consensus: ConsensusResult, context: MarketContext) -> str:
        """Build a concise entry rationale from supporting signals."""
        if not consensus.supporting_agents:
            return "No supporting signals available."

        parts: list[str] = [
            f"{context.symbol} {consensus.direction.value.upper()} at "
            f"market (regime: {context.regime.value})."
        ]

        for agent_id in consensus.supporting_agents[:4]:
            sig = consensus.agent_breakdown.get(agent_id)
            if sig:
                parts.append(f"• {agent_id}: {sig.reasoning[:120]}")

        return " ".join(parts) if len(parts) == 1 else parts[0] + "\n" + "\n".join(parts[1:])

    def _build_exit_rationale(self, consensus: ConsensusResult, context: MarketContext) -> str:
        """Build exit rationale from exit_ai signal or consensus direction."""
        exit_sig = consensus.agent_breakdown.get("exit_ai")
        if exit_sig:
            return exit_sig.reasoning

        # Fallback: describe expected exit
        direction = consensus.direction
        if direction == SignalDirection.LONG:
            return (
                "Exit on reversal signal, trail stop activation, "
                "or take-profit at key resistance level."
            )
        if direction == SignalDirection.SHORT:
            return (
                "Exit on reversal signal, trail stop activation, "
                "or take-profit at key support level."
            )
        return "Exit managed by risk management system."

    def _describe_session(self, context: MarketContext) -> str:
        """Describe the trading session context."""
        session_info = context.session_info
        if session_info is None:
            return f"Symbol: {context.symbol} | Timeframe: {context.timeframe}"

        if hasattr(session_info, "name"):
            name = session_info.name
        elif isinstance(session_info, dict):
            name = session_info.get("name", "Unknown")
        else:
            name = str(session_info)

        return (
            f"Session: {name} | Symbol: {context.symbol} | "
            f"Timeframe: {context.timeframe}"
        )
