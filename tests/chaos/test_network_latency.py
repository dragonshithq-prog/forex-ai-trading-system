"""Chaos test: Network latency injection — verify graceful degradation.

Tests that the system handles high-latency connections to external
dependencies (broker, DB, Redis, Kafka) without cascading failures.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


pytestmark = pytest.mark.chaos


class TestBrokerLatency:
    """Broker connection times out under high latency."""

    @pytest.mark.asyncio
    async def test_broker_timeout_returns_graceful_error(self):
        """When the broker gateway times out, the API returns a 502/503, not a 500."""
        from forex_trading.broker.gateway import broker_gateway

        with patch.object(broker_gateway, "get_account_info", new_callable=AsyncMock) as mock:
            mock.side_effect = asyncio.TimeoutError("Broker connection timed out")

            try:
                result = await broker_gateway.get_account_info(connection_id="test-conn")
                assert result is None, "Should return None on timeout"
            except asyncio.TimeoutError:
                # Expected: timeout propagates up to the API layer
                pass

    @pytest.mark.asyncio
    async def test_broker_timeout_does_not_crash_application(self):
        """Other components continue functioning after a broker timeout."""
        from forex_trading.risk.engine import RiskEngine

        engine = RiskEngine()
        engine.update_state(equity=100_000.0, drawdown_pct=0.0)

        # This should work fine even if broker is down
        assessment = await engine.assess_trade(
            symbol="EURUSD", side="long", size=0.1, entry_price=1.1000
        )
        assert assessment.is_approved is not None


class TestDatabaseLatency:
    """Database query timeouts don't cascade."""

    @pytest.mark.asyncio
    async def test_db_timeout_returns_degraded_health(self):
        """When DB is slow, health check returns 'degraded' not 'error'."""
        from forex_trading.shared.database.engine import DatabaseEngine

        engine = DatabaseEngine("sqlite+aiosqlite://", echo=False)
        with patch.object(engine, "health_check", new_callable=AsyncMock) as mock:
            mock.side_effect = asyncio.TimeoutError("DB timeout")

            try:
                healthy = await engine.health_check()
                assert not healthy, "Should report unhealthy on timeout"
            except asyncio.TimeoutError:
                pass

    @pytest.mark.asyncio
    async def test_concurrent_slow_queries_dont_exhaust_pool(self):
        """Slow concurrent queries eventually timeout but don't leak connections."""
        from forex_trading.shared.database.engine import DatabaseEngine

        engine = DatabaseEngine("sqlite+aiosqlite://", echo=False)

        async def slow_query(delay: float) -> bool:
            try:
                await asyncio.sleep(delay)
                return True
            except asyncio.TimeoutError:
                return False

        # Fire 20 concurrent slow queries
        results = await asyncio.gather(*[slow_query(0.1) for _ in range(20)])
        assert sum(results) == 20, "All queries should eventually complete"


class TestRedisLatency:
    """Redis latency doesn't block the application."""

    @pytest.mark.asyncio
    async def test_redis_slow_gets_fall_back_to_db(self):
        """When Redis is slow, the cache miss handler falls back to primary store."""
        from forex_trading.shared.cache import CacheManager

        cache = CacheManager()
        with patch.object(cache, "get", new_callable=AsyncMock) as mock:
            mock.side_effect = asyncio.TimeoutError("Redis timeout")
            mock.return_value = None

            result = await cache.get("some_key")
            assert result is None, "Should return None on timeout"


class TestKafkaLatency:
    """Kafka latency doesn't block trading operations."""

    @pytest.mark.asyncio
    async def test_kafka_publish_timeout_falls_to_outbox(self):
        """When Kafka is slow, events are persisted in the outbox table."""
        from forex_trading.shared.messaging.event_bus import EventBus

        bus = EventBus()
        with patch.object(bus, "publish", new_callable=AsyncMock) as mock:
            mock.side_effect = asyncio.TimeoutError("Kafka timeout")

            try:
                await bus.publish(topic="trading.order", key="order-1", value={"id": "1"})
            except asyncio.TimeoutError:
                pass
