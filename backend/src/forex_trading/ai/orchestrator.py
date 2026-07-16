"""AI Orchestrator — coordinate agents, persist decisions, detect drift.

Performance Optimizations (Phase 8):
- Per-agent timeout to prevent slow agents from blocking consensus
- Circuit breaker per-agent (disable after N consecutive failures)
- Agent result caching for identical contexts
- Semaphore to limit concurrent analyses
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time as time_module
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

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
from forex_trading.shared.database.uow import UnitOfWorkFactory
from forex_trading.shared.database.models_strategy import (
    AIDecision,
    AgentPerformance,
    AgentType,
    SignalDirection as DBSignalDirection,
)
from forex_trading.shared.cache import CacheManager
from forex_trading.shared.monitoring import (
    ai_agent_latency_seconds,
    ai_drift_alerts_total,
    ai_signal_confidence,
    ai_signals_generated_total,
)

logger = structlog.get_logger()

_DRIFT_WINDOW_SIZE = 20
_PERFORMANCE_LOOKBACK = 50
_BASE_WEIGHT_FACTOR = 0.7
_PERFORMANCE_WEIGHT_FACTOR = 0.3
_AGENT_ID_TO_DB_TYPE: dict[str, AgentType] = {
    "market_structure": AgentType.STRUCTURE,
    "trend_ai": AgentType.TREND,
    "sentiment_ai": AgentType.SENTIMENT,
    "liquidity_ai": AgentType.LIQUIDITY,
    "volatility_ai": AgentType.VOLATILITY,
}

# Performance tuning constants
_DEFAULT_AGENT_TIMEOUT = 10.0  # seconds per agent
_DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive failures before disabling
_DEFAULT_CIRCUIT_BREAKER_RESET_SECONDS = 300  # 5 minutes until retry
_DEFAULT_MAX_CONCURRENT_ANALYSES = 5  # semaphore limit
_DEFAULT_AGENT_CACHE_TTL = 60  # seconds to cache agent results for identical contexts


@dataclass
class AgentCircuitBreaker:
    """Circuit breaker state for a single agent."""
    consecutive_failures: int = 0
    is_open: bool = False
    opened_at: float | None = None
    last_error: str | None = None
    failure_threshold: int = _DEFAULT_CIRCUIT_BREAKER_THRESHOLD
    reset_after_seconds: float = _DEFAULT_CIRCUIT_BREAKER_RESET_SECONDS

    def record_failure(self, error: str) -> None:
        self.consecutive_failures += 1
        self.last_error = error
        if self.consecutive_failures >= self.failure_threshold:
            self.is_open = True
            self.opened_at = time_module.monotonic()

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.is_open = False
        self.opened_at = None
        self.last_error = None

    @property
    def can_try(self) -> bool:
        if not self.is_open:
            return True
        if self.opened_at is not None:
            elapsed = time_module.monotonic() - self.opened_at
            if elapsed >= self.reset_after_seconds:
                # Half-open: allow one trial
                self.is_open = False
                self.opened_at = None
                return True
        return False


@dataclass
class OrchestratorResult:
    consensus: ConsensusResult
    explanation: TradeExplanation
    should_trade: bool
    agent_signals: dict[str, AgentSignal]
    ai_decision_id: UUID | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class AIOrchestrator:
    """Orchestrate multiple AI agents to produce trade recommendations.

    Responsibilities:
    - Manage agent registry and lifecycle
    - Distribute market context to agents concurrently with per-agent timeout
    - Circuit breaker per-agent (disable after N consecutive failures)
    - Agent result caching for identical contexts
    - Semaphore to limit concurrent analyses
    - Aggregate agent signals using dynamic weighted consensus
    - Persist every decision to AIDecision table
    - Track agent agreement for drift detection
    - Generate XAI explanations
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        cache: CacheManager | None = None,
        agent_timeout: float = _DEFAULT_AGENT_TIMEOUT,
        circuit_breaker_threshold: int = _DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
        circuit_breaker_reset_seconds: float = _DEFAULT_CIRCUIT_BREAKER_RESET_SECONDS,
        max_concurrent_analyses: int = _DEFAULT_MAX_CONCURRENT_ANALYSES,
        agent_cache_ttl: int = _DEFAULT_AGENT_CACHE_TTL,
    ) -> None:
        self._uow_factory = uow_factory
        self._cache = cache
        self._agent_timeout = agent_timeout
        self._circuit_breaker_threshold = circuit_breaker_threshold
        self._circuit_breaker_reset_seconds = circuit_breaker_reset_seconds
        self._agent_cache_ttl = agent_cache_ttl

        self._agents: dict[str, BaseAgent] = {}
        self._consensus_engine = ConsensusEngine(
            min_agents=4,
            agreement_threshold=0.60,
        )
        self._explainer = TradeExplainer()

        self._last_explanation: TradeExplanation | None = None
        self._last_decision_id: UUID | None = None

        # Drift detection: sliding window of agreement ratios
        self._agreement_window: deque[float] = deque(maxlen=_DRIFT_WINDOW_SIZE)
        self._drift_alerted = False

        # Per-agent circuit breakers
        self._circuit_breakers: dict[str, AgentCircuitBreaker] = {}

        # Concurrency limiter
        self._semaphore = asyncio.Semaphore(max_concurrent_analyses)

        # Agent result cache: context_hash -> (result, timestamp)
        self._agent_result_cache: dict[str, tuple[AgentSignal, float]] = {}

        self._register_default_agents()

    def _get_circuit_breaker(self, agent_id: str) -> AgentCircuitBreaker:
        """Get or create circuit breaker for an agent."""
        if agent_id not in self._circuit_breakers:
            self._circuit_breakers[agent_id] = AgentCircuitBreaker(
                failure_threshold=self._circuit_breaker_threshold,
                reset_after_seconds=self._circuit_breaker_reset_seconds,
            )
        return self._circuit_breakers[agent_id]

    def _register_default_agents(self) -> None:
        agents: list[BaseAgent] = [
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
        for a in agents:
            self.register_agent(a)

    def register_agent(self, agent: BaseAgent) -> None:
        self._agents[agent.agent_id] = agent
        logger.info("agent_registered", agent_id=agent.agent_id, name=agent.name)

    def unregister_agent(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)
        self._circuit_breakers.pop(agent_id, None)
        logger.info("agent_unregistered", agent_id=agent_id)

    def get_agent(self, agent_id: str) -> BaseAgent | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[BaseAgent]:
        return list(self._agents.values())

    async def explain_last_decision(self) -> TradeExplanation | None:
        return self._last_explanation

    def get_circuit_breaker_states(self) -> dict[str, dict[str, Any]]:
        """Return circuit breaker states for all agents."""
        states: dict[str, dict[str, Any]] = {}
        for agent_id, cb in self._circuit_breakers.items():
            states[agent_id] = {
                "is_open": cb.is_open,
                "consecutive_failures": cb.consecutive_failures,
                "last_error": cb.last_error,
                "can_try": cb.can_try,
            }
        return states

    def reset_circuit_breaker(self, agent_id: str) -> None:
        """Manually reset circuit breaker for an agent."""
        cb = self._circuit_breakers.get(agent_id)
        if cb:
            cb.record_success()
            logger.info("circuit_breaker_reset", agent_id=agent_id)

    def _build_context_cache_key(self, context: MarketContext) -> str:
        """Build a deterministic cache key from the market context."""
        raw = (
            f"{context.symbol}:{context.timeframe}:{context.regime.value}:"
            f"{len(context.candles or [])}:"
            f"{context.candles[0].get('timestamp', '') if context.candles else ''}:"
            f"{context.candles[-1].get('timestamp', '') if context.candles else ''}"
        )
        return f"agent_ctx:{hashlib.md5(raw.encode()).hexdigest()}"

    async def analyze(
        self,
        context: MarketContext,
        strategy_id: UUID | None = None,
    ) -> OrchestratorResult:
        """Run all agents concurrently and produce a consensus recommendation.

        Every decision is persisted to the AIDecision table.
        """
        # Acquire concurrency semaphore
        async with self._semaphore:
            return await self._do_analyze(context, strategy_id)

    async def _do_analyze(
        self,
        context: MarketContext,
        strategy_id: UUID | None = None,
    ) -> OrchestratorResult:
        """Internal analyze method (runs under semaphore)."""
        log = logger.bind(
            symbol=context.symbol,
            timeframe=context.timeframe,
            regime=context.regime.value,
        )

        enabled = [a for a in self._agents.values() if a.is_enabled]
        if not enabled:
            log.error("no_agents_enabled")
            return await self._empty_result(context)

        # Build context cache key for agent result caching
        ctx_cache_key = self._build_context_cache_key(context)

        # Run agents concurrently with per-agent timeout and circuit breaker
        tasks: dict[str, asyncio.Task] = {}
        agent_start_times: dict[str, float] = {}

        for a in enabled:
            cb = self._get_circuit_breaker(a.agent_id)

            # Check circuit breaker
            if not cb.can_try:
                log.warning(
                    "agent_circuit_breaker_open",
                    agent_id=a.agent_id,
                    consecutive_failures=cb.consecutive_failures,
                    last_error=cb.last_error,
                )
                continue

            # Check agent result cache
            agent_cache_key = f"{ctx_cache_key}:{a.agent_id}"
            cached_result = self._check_agent_cache(agent_cache_key)
            if cached_result is not None:
                agent_start_times[a.agent_id] = time_module.monotonic()
                tasks[a.agent_id] = asyncio.create_task(
                    self._cached_agent_result(cached_result)
                )
                continue

            agent_start_times[a.agent_id] = time_module.monotonic()
            tasks[a.agent_id] = asyncio.create_task(
                self._run_agent_with_timeout(a, context, agent_cache_key)
            )

        if not tasks:
            log.error("all_agents_circuit_breakers_open")
            return await self._empty_result(context)

        # Gather results with timeout-aware handling
        raw_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        agent_signals: dict[str, AgentSignal] = {}
        signals: list[AgentSignal] = []
        for agent_id, result in zip(tasks.keys(), raw_results):
            elapsed = time_module.monotonic() - agent_start_times.get(agent_id, 0)
            ai_agent_latency_seconds.labels(agent_id=agent_id).observe(elapsed)

            if isinstance(result, asyncio.TimeoutError):
                log.warning("agent_timeout", agent_id=agent_id, timeout=self._agent_timeout)
                cb = self._get_circuit_breaker(agent_id)
                cb.record_failure(f"Timeout after {self._agent_timeout}s")
                continue
            elif isinstance(result, Exception):
                log.error("agent_failed", agent_id=agent_id, error=str(result))
                cb = self._get_circuit_breaker(agent_id)
                cb.record_failure(str(result))
                continue
            else:
                cb = self._get_circuit_breaker(agent_id)
                cb.record_success()
                agent_signals[agent_id] = result
                signals.append(result)

        if not signals:
            log.warning("no_agent_signals_collected")
            return await self._empty_result(context)

        # Dynamic weights: blend hardcoded regime weights with recent agreement
        base_weights = {
            a.agent_id: a.get_weight(context.regime) for a in enabled
            if a.agent_id in agent_signals
        }
        perf_weights = await self._load_agreement_rates(
            context.symbol, context.timeframe
        )
        weights = self._blend_weights(base_weights, perf_weights)

        consensus = await self._consensus_engine.aggregate(
            signals=signals,
            regime=context.regime,
            weights=weights,
        )

        # Drift tracking
        self._agreement_window.append(consensus.agreement_ratio)
        await self._check_drift(consensus, log)

        risk_assessment = self._build_risk_assessment(agent_signals, context)
        explanation = self._explainer.explain_decision(
            consensus=consensus,
            context=context,
            risk_assessment=risk_assessment,
        )
        self._last_explanation = explanation

        should_trade = consensus.is_actionable and not self._risk_vetoed(agent_signals)

        ai_signals_generated_total.labels(
            symbol=context.symbol,
            direction=consensus.direction.value,
            actionable=str(should_trade),
        ).inc()
        ai_signal_confidence.labels(symbol=context.symbol).observe(consensus.confidence)

        # Persist decision
        decision_id = await self._persist_decision(
            consensus=consensus,
            context=context,
            agent_signals=agent_signals,
            should_trade=should_trade,
            strategy_id=strategy_id,
            explanation=explanation,
        )
        self._last_decision_id = decision_id

        log.info(
            "orchestrator_result",
            direction=consensus.direction.value,
            confidence=round(consensus.confidence, 3),
            agreement=round(consensus.agreement_ratio, 3),
            actionable=consensus.is_actionable,
            should_trade=should_trade,
            agents_ran=len(signals),
            drift_alerted=self._drift_alerted,
        )

        return OrchestratorResult(
            consensus=consensus,
            explanation=explanation,
            should_trade=should_trade,
            agent_signals=agent_signals,
            ai_decision_id=decision_id,
        )

    async def _run_agent_with_timeout(
        self,
        agent: BaseAgent,
        context: MarketContext,
        cache_key: str,
    ) -> AgentSignal:
        """Run a single agent with a timeout and cache the result."""
        try:
            result = await asyncio.wait_for(
                agent.analyze(context),
                timeout=self._agent_timeout,
            )
            # Cache the successful result
            self._agent_result_cache[cache_key] = (result, time_module.monotonic())
            return result
        except asyncio.TimeoutError:
            raise
        except Exception:
            raise

    async def _cached_agent_result(self, result: AgentSignal) -> AgentSignal:
        """Return a cached agent result (used as a coroutine)."""
        return result

    def _check_agent_cache(self, key: str) -> AgentSignal | None:
        """Check if we have a cached result for this agent+context combo."""
        entry = self._agent_result_cache.get(key)
        if entry is None:
            return None
        result, timestamp = entry
        age = time_module.monotonic() - timestamp
        if age > self._agent_cache_ttl:
            self._agent_result_cache.pop(key, None)
            return None
        return result

    # ─── Persistence ──────────────────────────────────────────────────────────

    async def _persist_decision(
        self,
        consensus: ConsensusResult,
        context: MarketContext,
        agent_signals: dict[str, AgentSignal],
        should_trade: bool,
        strategy_id: UUID | None,
        explanation: TradeExplanation,
    ) -> UUID:
        agent_signals_json: dict[str, Any] = {}
        for agent_id, sig in agent_signals.items():
            agent_signals_json[agent_id] = {
                "direction": sig.direction.value,
                "confidence": sig.confidence,
                "reasoning": sig.reasoning,
                "supporting_data": sig.supporting_data,
            }

        async with self._uow_factory as uow:
            db_direction = {
                SignalDirection.LONG: DBSignalDirection.LONG,
                SignalDirection.SHORT: DBSignalDirection.SHORT,
                SignalDirection.NEUTRAL: DBSignalDirection.NEUTRAL,
            }[consensus.direction]

            entry_price = context.metadata.get("entry_price")
            decision = AIDecision(
                strategy_id=strategy_id,
                symbol=context.symbol,
                timeframe=context.timeframe,
                direction=db_direction,
                confidence=consensus.confidence,
                agreement_ratio=consensus.agreement_ratio,
                conflict_ratio=consensus.conflict_ratio,
                agents_responding=len(agent_signals),
                total_agents=len(self._agents),
                was_rejected=not should_trade,
                rejection_reason=(
                "risk_vetoed" if not should_trade and self._risk_vetoed(agent_signals)
                else "consensus_below_threshold" if not consensus.is_actionable
                else None
            ),
                market_regime=context.regime.value,
                session=context.metadata.get("session"),
                price_at_decision=entry_price,
                agent_signals=agent_signals_json,
                rationale=consensus.reasoning,
            )
            await uow.ai_decisions.add(decision)
            uow.add_event(
                aggregate_type="ai_decision",
                aggregate_id=decision.id,
                event_type="ai.decision.created",
                payload={
                    "symbol": context.symbol,
                    "direction": consensus.direction.value,
                    "confidence": consensus.confidence,
                    "should_trade": should_trade,
                },
            )
            await uow.commit()
            return decision.id

    async def record_execution_outcome(
        self,
        decision_id: UUID,
        was_executed: bool,
        outcome_pnl: float | None = None,
    ) -> None:
        """Update an AIDecision with execution result and PnL."""
        async with self._uow_factory as uow:
            decision = await uow.ai_decisions.get(decision_id)
            if decision is None:
                logger.warning("decision_not_found", decision_id=str(decision_id))
                return
            await uow.ai_decisions.update(decision, {
                "was_executed": was_executed,
                "outcome_pnl": outcome_pnl,
            })
            await uow.commit()

    async def get_recent_decisions(
        self, symbol: str, limit: int = 20
    ) -> list[AIDecision]:
        async with self._uow_factory as uow:
            return await uow.ai_decisions.get_by_symbol(symbol, limit=limit)

    # ─── Dynamic Weighting ────────────────────────────────────────────────────

    async def _load_agreement_rates(
        self, symbol: str, timeframe: str
    ) -> dict[str, float]:
        """Load trailing agreement rates per agent from recent AIDecision records."""
        rates: dict[str, float] = {}
        try:
            async with self._uow_factory as uow:
                from sqlalchemy import select
                stmt = (
                    select(AIDecision)
                    .order_by(AIDecision.decision_time.desc())
                    .limit(_PERFORMANCE_LOOKBACK)
                )
                result = await uow.session.execute(stmt)
                recent = list(result.scalars().all())
        except Exception:
            logger.warning("failed_to_load_agreement_rates", exc_info=True)
            return rates

        if len(recent) < 5:
            return rates

        agent_counts: dict[str, int] = {}
        agent_matches: dict[str, int] = {}

        for dec in recent:
            if not dec.agent_signals:
                continue
            for agent_id, sig_data in dec.agent_signals.items():
                if not isinstance(sig_data, dict):
                    continue
                agent_counts[agent_id] = agent_counts.get(agent_id, 0) + 1
                dir_str = sig_data.get("direction", "neutral")
                if dir_str == dec.direction.value:
                    agent_matches[agent_id] = agent_matches.get(agent_id, 0) + 1

        for agent_id in agent_counts:
            count = agent_counts[agent_id]
            matches = agent_matches.get(agent_id, 0)
            rates[agent_id] = matches / count if count > 0 else 0.0

        return rates

    def _blend_weights(
        self,
        base: dict[str, float],
        perf: dict[str, float],
    ) -> dict[str, float]:
        """Blend hardcoded regime weights with trailing agreement rates."""
        result: dict[str, float] = {}
        for agent_id, base_w in base.items():
            perf_w = perf.get(agent_id, base_w)
            result[agent_id] = (
                _BASE_WEIGHT_FACTOR * base_w
                + _PERFORMANCE_WEIGHT_FACTOR * perf_w
            )
        return result

    # ─── Drift Detection ──────────────────────────────────────────────────────

    async def _check_drift(
        self, consensus: ConsensusResult, log: Any
    ) -> None:
        """Detect declining agreement trend and emit alerts."""
        if len(self._agreement_window) < _DRIFT_WINDOW_SIZE:
            return
        recent = list(self._agreement_window)
        first_half = sum(recent[: _DRIFT_WINDOW_SIZE // 2]) / (_DRIFT_WINDOW_SIZE // 2)
        second_half = sum(recent[_DRIFT_WINDOW_SIZE // 2:]) / (_DRIFT_WINDOW_SIZE // 2)
        drift = second_half - first_half

        if drift < -0.1 and not self._drift_alerted:
            self._drift_alerted = True
            ai_drift_alerts_total.inc()
            log.warning(
                "drift_detected",
                drift=round(drift, 3),
                first_half_agreement=round(first_half, 3),
                second_half_agreement=round(second_half, 3),
                message=f"Agent agreement declining (delta={drift:.2f}) — possible regime change",
            )
            async with self._uow_factory as uow:
                from forex_trading.shared.database.models_risk import RiskAlert, RiskLevel
                alert = RiskAlert(
                    level=RiskLevel.WARNING,
                    category="ai_drift",
                    message=(
                        f"AI agent agreement declining: {drift:.1%} over "
                        f"last {_DRIFT_WINDOW_SIZE} decisions for {consensus.direction.value}"
                    ),
                    current_value=drift,
                    threshold_value=-0.1,
                    action_required=False,
                )
                await uow.risk_alerts.add(alert)
                await uow.commit()

        if drift >= -0.05:
            self._drift_alerted = False

    # ─── Risk Veto ────────────────────────────────────────────────────────────

    def _risk_vetoed(self, agent_signals: dict[str, AgentSignal]) -> bool:
        risk = agent_signals.get("risk_ai")
        if risk is None:
            return False
        return (
            risk.direction == SignalDirection.NEUTRAL
            and risk.confidence >= 0.80
        )

    def _build_risk_assessment(
        self,
        agent_signals: dict[str, AgentSignal],
        context: MarketContext,
    ) -> dict[str, Any]:
        risk = agent_signals.get("risk_ai")
        meta = context.metadata or {}
        assessment: dict[str, Any] = {
            "spread": meta.get("spread"),
            "current_drawdown_pct": meta.get("current_drawdown_pct"),
            "open_positions": len(meta.get("open_positions", [])),
            "news_events": meta.get("news_events", []),
            "risk_vetoed": self._risk_vetoed(agent_signals),
        }
        if risk:
            assessment["risk_agent_direction"] = risk.direction.value
            assessment["risk_agent_confidence"] = risk.confidence
            assessment["risk_agent_reasoning"] = risk.reasoning
            assessment["risk_flags"] = risk.supporting_data.get("red_flags", [])
        return assessment

    async def _empty_result(self, context: MarketContext) -> OrchestratorResult:
        consensus = ConsensusResult(
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            agreement_ratio=0.0,
            conflict_ratio=1.0,
            supporting_agents=[],
            conflicting_agents=[],
            is_actionable=False,
            reasoning="No agents enabled / All circuit breakers open.",
            agent_breakdown={},
        )
        explanation = self._explainer.explain_decision(
            consensus=consensus,
            context=context,
            risk_assessment={"error": "No agents available"},
        )
        return OrchestratorResult(
            consensus=consensus,
            explanation=explanation,
            should_trade=False,
            agent_signals={},
        )
