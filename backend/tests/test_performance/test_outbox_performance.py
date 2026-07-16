"""Tests for OutboxPublisher performance optimizations.

Tests:
- Batch polling (fetch multiple pending events at once)
- Concurrent publishing with semaphore
- Adaptive poll interval (backoff when empty, faster when busy)
- Batch size limit to avoid memory issues
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from forex_trading.shared.database.outbox import (
    OutboxPublisher,
    create_outbox_entry,
    time_monotonic,
    _reset_adaptive_state,
)
from forex_trading.shared.database.models_trading import EventOutbox


pytestmark = pytest.mark.asyncio


class TestOutboxPublisherPerformance:
    """Tests for OutboxPublisher performance optimizations."""

    async def test_batch_polling_fetches_multiple_events(self, db_session):
        """Batch polling should fetch all pending events in one query."""
        # Create multiple pending entries
        for i in range(5):
            entry = EventOutbox(
                aggregate_type="order",
                aggregate_id=uuid4(),
                event_type="trading.order.placed",
                payload={"order_id": str(uuid4())},
                status=EventOutbox.OutboxStatus.PENDING,
                publish_attempts=0,
            )
            db_session.add(entry)
        await db_session.commit()

        fresh_bus = AsyncMock()
        fresh_bus.publish = AsyncMock(return_value=True)

        publisher = OutboxPublisher(
            kafka_producer=fresh_bus,
            session_factory=lambda: db_session,
            batch_size=10,
        )

        # Publish batch
        count = await publisher._publish_batch()
        assert count > 0
        assert fresh_bus.publish.call_count >= 1

    async def test_concurrent_publishing_semaphore(self):
        """Publisher should use semaphore to limit concurrent publishes."""
        publisher = OutboxPublisher(
            kafka_producer=MagicMock(),
            session_factory=MagicMock(),
            max_concurrent=3,
        )
        assert publisher._semaphore._value == 3

    async def test_adaptive_poll_interval_backoff(self):
        """Adaptive poll interval should back off when no events found."""
        _reset_adaptive_state()

        # Create publisher starting at minimum interval
        publisher = OutboxPublisher(
            kafka_producer=MagicMock(),
            session_factory=MagicMock(),
            min_interval=0.05,
            max_interval=2.0,
        )

        # Simulate consecutive empty polls
        initial_interval = publisher._current_interval
        publisher._consecutive_empty = 3
        publisher._adapt_interval(0)

        assert publisher._current_interval > initial_interval

    async def test_adaptive_poll_interval_speedup(self):
        """Adaptive poll interval should speed up when busy."""
        _reset_adaptive_state()

        publisher = OutboxPublisher(
            kafka_producer=MagicMock(),
            session_factory=MagicMock(),
            min_interval=0.05,
            max_interval=2.0,
        )

        # Start with higher interval
        publisher._current_interval = 1.0
        publisher._consecutive_full = 3

        # Simulate busy poll (many events published)
        publisher._adapt_interval(50)

        assert publisher._current_interval < 1.0

    async def test_batch_size_limit_enforced(self):
        """Batch size should be capped at maximum to prevent memory issues."""
        publisher = OutboxPublisher(
            kafka_producer=MagicMock(),
            session_factory=MagicMock(),
            batch_size=10000,  # Exceeds max
        )
        # Should be capped
        from forex_trading.shared.database.outbox import _MAX_BATCH_SIZE
        assert publisher._batch_size <= _MAX_BATCH_SIZE

    async def test_publish_single_success(self, db_session):
        """Publishing a single event should succeed."""
        entry = EventOutbox(
            aggregate_type="order",
            aggregate_id=uuid4(),
            event_type="trading.order.placed",
            payload={"order_id": str(uuid4())},
            status=EventOutbox.OutboxStatus.PENDING,
            publish_attempts=0,
        )
        db_session.add(entry)
        await db_session.commit()

        fresh_bus = AsyncMock()
        fresh_bus.publish = AsyncMock(return_value=True)

        publisher = OutboxPublisher(
            kafka_producer=fresh_bus,
            session_factory=lambda: db_session,
        )

        result = await publisher._publish_single(entry)
        assert result is True

    async def test_publish_single_failure(self, db_session):
        """Publishing a single event should handle failure."""
        entry = EventOutbox(
            aggregate_type="order",
            aggregate_id=uuid4(),
            event_type="trading.order.placed",
            payload={"order_id": str(uuid4())},
            status=EventOutbox.OutboxStatus.PENDING,
            publish_attempts=0,
        )

        failing_bus = AsyncMock()
        failing_bus.publish = AsyncMock(side_effect=Exception("Kafka unavailable"))

        publisher = OutboxPublisher(
            kafka_producer=failing_bus,
            session_factory=lambda: db_session,
        )

        result = await publisher._publish_single(entry)
        assert result is False

    async def test_start_stop_cleans_up(self):
        """Publisher should start and stop cleanly."""
        publisher = OutboxPublisher(
            kafka_producer=MagicMock(),
            session_factory=MagicMock(),
        )

        assert publisher._running is False
        assert publisher._task is None

        await publisher.start()
        assert publisher._running is True
        assert publisher._task is not None

        await publisher.stop()
        assert publisher._running is False

    async def test_publish_batch_with_multiple_events(self, db_session):
        """Batch should handle multiple events concurrently."""
        entries = []
        for i in range(3):
            entry = EventOutbox(
                aggregate_type="order",
                aggregate_id=uuid4(),
                event_type=f"trading.order.{'placed' if i % 2 == 0 else 'filled'}",
                payload={"order_id": str(uuid4())},
                status=EventOutbox.OutboxStatus.PENDING,
                publish_attempts=0,
            )
            db_session.add(entry)
            entries.append(entry)
        await db_session.commit()

        fresh_bus = AsyncMock()
        fresh_bus.publish = AsyncMock(return_value=True)

        publisher = OutboxPublisher(
            kafka_producer=fresh_bus,
            session_factory=lambda: db_session,
            max_concurrent=5,
        )

        count = await publisher._publish_batch()
        assert count > 0

    async def test_topic_resolution(self):
        """Topic resolution should work correctly for all known event types."""
        publisher = OutboxPublisher(
            kafka_producer=MagicMock(),
            session_factory=MagicMock(),
        )

        test_cases = [
            ("market.tick", "forex.market.tick"),
            ("trading.order.placed", "forex.trading.order"),
            ("trading.position.opened", "forex.trading.position"),
            ("risk.alert", "forex.risk.alert"),
            ("unknown.event", "forex.event.unknown.event"),
        ]

        for event_type, expected_topic in test_cases:
            topic = publisher._resolve_topic(event_type)
            assert topic == expected_topic
