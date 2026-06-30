"""Consensus Engine - aggregates weighted agent signals into a single decision."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from forex_trading.ai.agents.base import (
    AgentSignal,
    MarketRegime,
    SignalDirection,
)

logger = structlog.get_logger()


@dataclass
class ConsensusResult:
    """Aggregated result from the consensus engine."""

    direction: SignalDirection
    confidence: float
    agreement_ratio: float
    conflict_ratio: float
    supporting_agents: list[str]
    conflicting_agents: list[str]
    is_actionable: bool
    reasoning: str
    agent_breakdown: dict[str, AgentSignal]


class ConsensusEngine:
    """
    Aggregates signals from multiple agents into a weighted consensus decision.

    Uses weighted voting where each agent's vote is (weight × confidence).
    Conflict is defined as meaningful opposing weight against the winning direction.
    """

    def __init__(
        self,
        min_agents: int = 4,
        agreement_threshold: float = 0.60,
    ) -> None:
        self._min_agents = min_agents
        self._agreement_threshold = agreement_threshold

    async def aggregate(
        self,
        signals: list[AgentSignal],
        regime: MarketRegime,
        weights: dict[str, float] | None = None,
    ) -> ConsensusResult:
        """
        Aggregate agent signals using weighted voting.

        Args:
            signals: List of AgentSignal from all enabled agents.
            regime: Current market regime (used for fallback weight=1.0 if weights absent).
            weights: Optional dict mapping agent_id → weight override.

        Returns:
            ConsensusResult with direction, confidence, actionability, and reasoning.
        """
        log = logger.bind(regime=regime.value, n_signals=len(signals))

        if len(signals) < self._min_agents:
            log.warning("insufficient_agents", count=len(signals), required=self._min_agents)
            return self._insufficient_result(signals, weights or {})

        effective_weights = self._resolve_weights(signals, weights)

        long_weight = 0.0
        short_weight = 0.0
        neutral_weight = 0.0

        for sig in signals:
            w = effective_weights.get(sig.agent_id, 1.0)
            weighted_conf = w * sig.confidence
            if sig.direction == SignalDirection.LONG:
                long_weight += weighted_conf
            elif sig.direction == SignalDirection.SHORT:
                short_weight += weighted_conf
            else:
                neutral_weight += weighted_conf

        total_weight = long_weight + short_weight + neutral_weight

        if total_weight < 1e-8:
            return ConsensusResult(
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                agreement_ratio=0.0,
                conflict_ratio=1.0,
                supporting_agents=[],
                conflicting_agents=[sig.agent_id for sig in signals],
                is_actionable=False,
                reasoning="Total weighted confidence is zero — no actionable signal.",
                agent_breakdown={sig.agent_id: sig for sig in signals},
            )

        # Determine winning direction
        if long_weight > short_weight and long_weight > neutral_weight:
            direction = SignalDirection.LONG
            winner_weight = long_weight
            loser_weight = short_weight
        elif short_weight > long_weight and short_weight > neutral_weight:
            direction = SignalDirection.SHORT
            winner_weight = short_weight
            loser_weight = long_weight
        else:
            direction = SignalDirection.NEUTRAL
            winner_weight = neutral_weight
            loser_weight = min(long_weight, short_weight)

        agreement_ratio = winner_weight / total_weight
        conflict_ratio = loser_weight / total_weight

        # Separate supporting and conflicting agents
        supporting_agents: list[str] = []
        conflicting_agents: list[str] = []

        for sig in signals:
            if sig.direction == direction:
                supporting_agents.append(sig.agent_id)
            elif sig.direction != SignalDirection.NEUTRAL:
                conflicting_agents.append(sig.agent_id)

        # Weighted average confidence from supporting agents only
        if direction != SignalDirection.NEUTRAL:
            support_conf_total = sum(
                effective_weights.get(sig.agent_id, 1.0) * sig.confidence
                for sig in signals
                if sig.direction == direction
            )
            support_weight_total = sum(
                effective_weights.get(sig.agent_id, 1.0)
                for sig in signals
                if sig.direction == direction
            )
            confidence = (
                support_conf_total / support_weight_total
                if support_weight_total > 0 else 0.0
            )
        else:
            confidence = 0.0

        # Actionability checks
        non_neutral_signals = [s for s in signals if s.direction != SignalDirection.NEUTRAL]
        too_many_neutral = len(non_neutral_signals) < self._min_agents

        is_actionable = (
            confidence >= self._agreement_threshold
            and agreement_ratio >= self._agreement_threshold
            and not too_many_neutral
            and direction != SignalDirection.NEUTRAL
        )

        reasoning = self._build_reasoning(
            direction=direction,
            confidence=confidence,
            agreement_ratio=agreement_ratio,
            conflict_ratio=conflict_ratio,
            signals=signals,
            effective_weights=effective_weights,
            is_actionable=is_actionable,
        )

        log.info(
            "consensus_result",
            direction=direction.value,
            confidence=round(confidence, 3),
            agreement=round(agreement_ratio, 3),
            conflict=round(conflict_ratio, 3),
            actionable=is_actionable,
            supporting=supporting_agents,
            conflicting=conflicting_agents,
        )

        return ConsensusResult(
            direction=direction,
            confidence=confidence,
            agreement_ratio=agreement_ratio,
            conflict_ratio=conflict_ratio,
            supporting_agents=supporting_agents,
            conflicting_agents=conflicting_agents,
            is_actionable=is_actionable,
            reasoning=reasoning,
            agent_breakdown={sig.agent_id: sig for sig in signals},
        )

    def _resolve_weights(
        self,
        signals: list[AgentSignal],
        overrides: dict[str, float] | None,
    ) -> dict[str, float]:
        """Build effective weight dict from overrides or default to 1.0."""
        if not overrides:
            return {sig.agent_id: 1.0 for sig in signals}
        return {sig.agent_id: overrides.get(sig.agent_id, 1.0) for sig in signals}

    def _insufficient_result(
        self,
        signals: list[AgentSignal],
        weights: dict[str, float],
    ) -> ConsensusResult:
        """Return a non-actionable result when too few agents responded."""
        return ConsensusResult(
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            agreement_ratio=0.0,
            conflict_ratio=1.0,
            supporting_agents=[],
            conflicting_agents=[sig.agent_id for sig in signals],
            is_actionable=False,
            reasoning=(
                f"Insufficient agents: {len(signals)} responded, "
                f"minimum required is {self._min_agents}."
            ),
            agent_breakdown={sig.agent_id: sig for sig in signals},
        )

    def _build_reasoning(
        self,
        direction: SignalDirection,
        confidence: float,
        agreement_ratio: float,
        conflict_ratio: float,
        signals: list[AgentSignal],
        effective_weights: dict[str, float],
        is_actionable: bool,
    ) -> str:
        """Build a human-readable reasoning string from all agent signals."""
        lines: list[str] = [
            f"Consensus: {direction.value.upper()} | "
            f"Confidence: {confidence:.1%} | "
            f"Agreement: {agreement_ratio:.1%} | "
            f"Conflict: {conflict_ratio:.1%} | "
            f"Actionable: {is_actionable}",
            "",
            "Agent breakdown:",
        ]

        for sig in sorted(signals, key=lambda s: s.agent_id):
            w = effective_weights.get(sig.agent_id, 1.0)
            lines.append(
                f"  [{sig.agent_id}] {sig.direction.value.upper()} "
                f"conf={sig.confidence:.2f} wt={w:.2f} → {sig.reasoning[:100]}"
            )

        if not is_actionable:
            lines.append("")
            if confidence < self._agreement_threshold:
                lines.append(f"NOT ACTIONABLE: confidence {confidence:.1%} < threshold {self._agreement_threshold:.1%}")
            if agreement_ratio < self._agreement_threshold:
                lines.append(f"NOT ACTIONABLE: agreement {agreement_ratio:.1%} < threshold {self._agreement_threshold:.1%}")

        return "\n".join(lines)
