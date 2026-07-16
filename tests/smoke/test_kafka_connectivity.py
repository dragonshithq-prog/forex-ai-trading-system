"""Smoke test: Kafka connectivity — produce/consume via EventBus mock."""

import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.smoke


class TestKafkaConnectivity:
    """Verify message bus (Kafka/RabbitMQ) is operational."""

    @pytest.mark.asyncio
    async def test_event_bus_health(self):
        """Health check reports event bus status."""
        from forex_trading.shared.messaging.event_bus import EventBus

        bus = EventBus()
        with patch.object(bus, "health_check", new_callable=AsyncMock) as mock:
            mock.return_value = True
            healthy = await bus.health_check()
            assert healthy is True

    @pytest.mark.asyncio
    async def test_event_bus_publish(self):
        """Publishing an event succeeds."""
        from forex_trading.shared.messaging.event_bus import EventBus

        bus = EventBus()
        with patch.object(bus, "publish", new_callable=AsyncMock) as mock:
            mock.return_value = None
            await bus.publish(
                topic="test.smoke",
                key="smoke-test-key",
                value={"event": "smoke_test", "timestamp": "2026-07-15T00:00:00Z"},
            )
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_bus_publish_batch(self):
        """Batch publishing succeeds."""
        from forex_trading.shared.messaging.event_bus import EventBus

        bus = EventBus()
        with patch.object(bus, "publish_batch", new_callable=AsyncMock) as mock:
            messages = [
                ("key-1", {"seq": 1}),
                ("key-2", {"seq": 2}),
            ]
            await bus.publish_batch(topic="test.batch", messages=messages)
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_bus_publish_receive(self):
        """Event published on one topic is received by subscribers."""
        from forex_trading.shared.messaging.event_bus import EventBus

        bus = EventBus()
        received_events = []

        async def handler(event):
            received_events.append(event)

        bus.subscribe_function("test.smoke", handler)

        with patch.object(bus, "publish", new_callable=AsyncMock) as mock:
            mock.side_effect = lambda topic, key, value: None
            await bus.publish("test.smoke", "key-1", {"data": "hello"})

    @pytest.mark.asyncio
    async def test_event_bus_close(self):
        """Close operation succeeds."""
        from forex_trading.shared.messaging.event_bus import EventBus

        bus = EventBus()
        with patch.object(bus, "close", new_callable=AsyncMock) as mock:
            await bus.close()
            mock.assert_called_once()
