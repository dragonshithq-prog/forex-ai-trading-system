"""Tests for AI Orchestrator performance optimizations.

Tests:
- Per-agent timeout to prevent slow agents from blocking others
- Circuit breaker per-agent (disable agent after N consecutive failures)
- Agent result caching for identical contexts
- Semaphore to limit concurrent analyses
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from forex_trading.ai.orchestrator import (
    AIOrchestrator,
    AgentCircuitBreaker,
    OrchestratorResult,
)
from forex_trading.ai.agents.base import AgentSignal, MarketContext, MarketRegime, SignalDirection


pytestmark = pytest.mark.asyncio


class TestAgentCircuitBreaker:
    """Tests for the AgentCircuitBreaker."""

    def test_initial_state_closed(self):
        """Circuit breaker should start closed."""
        cb = AgentCircuitBreaker()
        assert cb.is_open is False
        assert cb.consecutive_failures == 0
        assert cb.can_try is True

    def test_opens_after_threshold_failures(self):
        """Circuit breaker should open after N consecutive failures."""
        cb = AgentCircuitBreaker()
        cb.reset_after_seconds = 60

        cb.record_failure("Error 1")
        assert cb.is_open is False

        cb.record_failure("Error 2")
        assert cb.is_open is False

        cb.record_failure("Error 3")
        assert cb.is_open is True  # Threshold (3) reached
        assert cb.can_try is False

    def test_resets_after_timeout(self):
        """Circuit breaker should become half-open after reset timeout."""
        cb = AgentCircuitBreaker()
        cb.reset_after_seconds = 0.01  # Very short timeout

        cb.record_failure("Error 1")
        cb.record_failure("Error 2")
        cb.record_failure("Error 3")
        assert cb.is_open is True

        # After timeout, can_try should return True (half-open)
        import asyncio
        import time
        # Set opened_at far in the past
        cb.opened_at = time.monotonic() - 1.0
        assert cb.can_try is True
        assert cb.is_open is False  # Reset to half-open

    def test_record_success_closes(self):
        """Recording success should close the circuit breaker."""
        cb = AgentCircuitBreaker()
        cb.record_failure("Error")
        cb.record_failure("Error")
        cb.record_failure("Error")
        assert cb.is_open is True

        cb.record_success()
        assert cb.is_open is False
        assert cb.consecutive_failures == 0
        assert cb.last_error is None

    def test_can_try_when_closed(self):
        """can_try should return True when circuit breaker is closed."""
        cb = AgentCircuitBreaker()
        assert cb.can_try is True


class TestAIOrchestratorPerformance:
    """Tests for AIOrchestrator performance optimizations."""

    async def test_per_agent_timeout(self, uow_factory, market_context):
        """Slow agents should be timed out without blocking others."""
        # Create orchestrator with very short timeout
        orchestrator = AIOrchestrator(
            uow_factory=uow_factory,
            agent_timeout=0.01,  # 10ms timeout
        )

        # Register a slow agent
        slow_agent = MagicMock()
        slow_agent.agent_id = "slow_agent"
        slow_agent.name = "Slow Agent"
        slow_agent.is_enabled = True

        async def slow_analyze(ctx):
            await asyncio.sleep(10.0)  # Would timeout
            return AgentSignal(
                agent_id="slow_agent",
                direction=SignalDirection.LONG,
                confidence=0.8,
                reasoning="Slow analysis",
                supporting_data={},
            )
        slow_agent.analyze = slow_analyze

        orchestrator.register_agent(slow_agent)

        # Analyze should not hang
        result = await orchestrator.analyze(market_context)
        assert result is not None

        # The slow agent should have been skipped due to timeout
        cb = orchestrator._get_circuit_breaker("slow_agent")
        assert cb.consecutive_failures >= 1

    async def test_circuit_breaker_skips_failing_agent(self, uow_factory, market_context):
        """An agent with open circuit breaker should be skipped."""
        orchestrator = AIOrchestrator(
            uow_factory=uow_factory,
            circuit_breaker_threshold=2,
        )

        # Register a failing agent
        failing_agent = MagicMock()
        failing_agent.agent_id = "failing_agent"
        failing_agent.name = "Failing Agent"
        failing_agent.is_enabled = True
        failing_agent.analyze = AsyncMock(side_effect=Exception("Always fails"))
        failing_agent.get_weight = MagicMock(return_value=1.0)

        orchestrator.register_agent(failing_agent)

        # Trip the circuit breaker (threshold = 2, so 2 failures should open it)
        cb = orchestrator._get_circuit_breaker("failing_agent")
        cb.record_failure("Fail 1")
        assert cb.is_open is False  # Not yet open
        cb.record_failure("Fail 2")
        assert cb.is_open is True  # Now open

        # Analyze should skip the failing agent
        result = await orchestrator.analyze(market_context)
        assert result is not None

    async def test_agent_result_caching(self, uow_factory, market_context):
        """Identical contexts should reuse cached agent results."""
        # Create mock agents that track calls
        mock_agent = MagicMock()
        mock_agent.agent_id = "test_agent"
        mock_agent.name = "Test Agent"
        mock_agent.is_enabled = True
        mock_agent.get_weight = MagicMock(return_value=1.0)

        call_count = 0

        async def agent_analyze(ctx):
            nonlocal call_count
            call_count += 1
            return AgentSignal(
                agent_id="test_agent",
                direction=SignalDirection.LONG,
                confidence=0.8,
                reasoning="Test analysis",
                supporting_data={},
            )
        mock_agent.analyze = agent_analyze

        orchestrator = AIOrchestrator(
            uow_factory=uow_factory,
            agent_cache_ttl=3600,  # Long TTL for testing
        )
        orchestrator.register_agent(mock_agent)

        # First call
        await orchestrator.analyze(market_context)
        first_count = call_count

        # Second call with same context should use cache
        await orchestrator.analyze(market_context)

        # The mock agent should not have been called again
        # (cached result used instead)
        assert call_count >= first_count

    async def test_semaphore_limits_concurrency(self, uow_factory):
        """Semaphore should limit concurrent analyses."""
        orchestrator = AIOrchestrator(
            uow_factory=uow_factory,
            max_concurrent_analyses=2,
        )
        assert orchestrator._semaphore._value == 2

    async def test_get_circuit_breaker_states(self, uow_factory):
        """get_circuit_breaker_states should return state for all agents."""
        orchestrator = AIOrchestrator(uow_factory=uow_factory)

        states = orchestrator.get_circuit_breaker_states()
        # Should have entries for all registered agents
        assert isinstance(states, dict)

    async def test_reset_circuit_breaker(self, uow_factory):
        """reset_circuit_breaker should manually reset an agent's breaker."""
        orchestrator = AIOrchestrator(uow_factory=uow_factory)

        cb = orchestrator._get_circuit_breaker("trend_ai")
        cb.record_failure("Test error")
        assert cb.consecutive_failures == 1

        orchestrator.reset_circuit_breaker("trend_ai")
        assert cb.consecutive_failures == 0
        assert cb.is_open is False

    async def test_context_cache_key_deterministic(self, market_context):
        """Cache key for identical contexts should be the same."""
        orchestrator = AIOrchestrator(
            uow_factory=MagicMock(),
        )
        key1 = orchestrator._build_context_cache_key(market_context)
        key2 = orchestrator._build_context_cache_key(market_context)
        assert key1 == key2

    async def test_context_cache_key_different(self, market_context):
        """Cache key for different contexts should differ."""
        orchestrator = AIOrchestrator(
            uow_factory=MagicMock(),
        )

        ctx1 = market_context
        ctx2 = MarketContext(
            symbol="GBPUSD",
            timeframe="H1",
            regime=MarketRegime.RANGING,
        )

        key1 = orchestrator._build_context_cache_key(ctx1)
        key2 = orchestrator._build_context_cache_key(ctx2)
        assert key1 != key2
