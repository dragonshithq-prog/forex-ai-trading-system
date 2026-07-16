"""Tests for OutboxPublisher polling, publishing, and dead-letter logic."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from forex_trading.shared.database.outbox import (
    OutboxPublisher,
    create_outbox_entry,
)
from forex_trading.shared.database.models_trading import EventOutbox


pytestmark = pytest.mark.asyncio


class TestCreateOutboxEntry:
    """Tests for the create_outbox_entry helper."""

    def test_create_outbox_entry_basic(self):
        entry = create_outbox_entry(
            aggregate_type="order",
            aggregate_id=uuid4(),
            event_type="trading.order.placed",
            payload={"order_id": str(uuid4())},
            trace_id="trace-123",
            event_version=2,
        )
        assert entry["aggregate_type"] == "order"
        assert entry["event_type"] == "trading.order.placed"
        assert entry["event_version"] == 2
        assert entry["trace_id"] == "trace-123"
        assert "payload" in entry

    def test_create_outbox_entry_minimal(self):
        entry = create_outbox_entry(
            aggregate_type="position",
            aggregate_id=None,
            event_type="trading.position.opened",
            payload={"position_id": str(uuid4())},
        )
        assert entry["aggregate_id"] is None
        assert entry["event_version"] == 1


class TestOutboxPublisher:
    """Tests for the OutboxPublisher background worker."""

    async def test_start_stop(self, mock_event_bus, db_session):
        """OutboxPublisher should start and stop cleanly."""
        publisher = OutboxPublisher(
            kafka_producer=mock_event_bus,
            session_factory=lambda: db_session,
        )
        await publisher.start()
        assert publisher._running is True
        assert publisher._task is not None

        await publisher.stop()
        assert publisher._running is False

    async def test_publish_batch_processes_pending_events(
        self, mock_event_bus, db_session
    ):
        """Publish batch should process pending outbox entries."""
        # Create a pending outbox entry
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

        publisher = OutboxPublisher(
            kafka_producer=mock_event_bus,
            session_factory=lambda: db_session,
        )

        # Manually trigger a publish batch
        await publisher._publish_batch()

        # The event should have been published to the mock bus
        assert len(mock_event_bus.events) > 0
        assert mock_event_bus.events[0]["topic"] == "forex.trading.order"

    async def test_dead_letter_after_max_retries(self, mock_event_bus, db_session):
        """Events that fail repeatedly should be moved to dead-letter status."""
        # Create a producer that always fails
        failing_producer = AsyncMock()
        failing_producer.publish = AsyncMock(side_effect=Exception("Broker unavailable"))
        failing_producer.publish_batch = AsyncMock(side_effect=Exception("Broker unavailable"))

        # Create an entry with status=PENDING and publish_attempts at max-1,
        # so the next failure pushes it over the threshold to DEAD_LETTER.
        entry = EventOutbox(
            aggregate_type="order",
            aggregate_id=uuid4(),
            event_type="trading.order.placed",
            payload={"order_id": str(uuid4())},
            status=EventOutbox.OutboxStatus.PENDING,
            publish_attempts=4,  # One more attempt will trigger dead-letter (max = 5)
        )
        db_session.add(entry)
        await db_session.commit()

        publisher = OutboxPublisher(
            kafka_producer=failing_producer,
            session_factory=lambda: db_session,
        )

        await publisher._publish_batch()

        # Refresh or re-query the entry to get current state from the DB
        from sqlalchemy import select
        result = await db_session.execute(
            select(EventOutbox).where(EventOutbox.id == entry.id)
        )
        updated_entry = result.scalar_one_or_none()
        assert updated_entry is not None
        assert updated_entry.status == EventOutbox.OutboxStatus.DEAD_LETTER
        assert updated_entry.last_error is not None

    async def test_topic_resolution(self):
        """Topic resolution should map event types to correct Kafka topics."""
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
            assert topic == expected_topic, f"{event_type} → {topic}, expected {expected_topic}"

    async def test_publish_batch_empty(self, db_session):
        """Publish batch with no pending events should do nothing."""
        fresh_bus = AsyncMock()
        fresh_bus.publish = AsyncMock()
        publisher = OutboxPublisher(
            kafka_producer=fresh_bus,
            session_factory=lambda: db_session,
        )

        # Ensure no pending events — fresh_bus should never have been called
        await publisher._publish_batch()
        fresh_bus.publish.assert_not_called()

    async def test_publish_batch_updates_status(self, mock_event_bus, db_session):
        """Successfully published events should have their status updated."""
        entry = EventOutbox(
            aggregate_type="position",
            aggregate_id=uuid4(),
            event_type="trading.position.opened",
            payload={"position_id": str(uuid4())},
            status=EventOutbox.OutboxStatus.PENDING,
            publish_attempts=0,
        )
        db_session.add(entry)
        await db_session.commit()

        publisher = OutboxPublisher(
            kafka_producer=mock_event_bus,
            session_factory=lambda: db_session,
        )

        await publisher._publish_batch()

        # After successful publish, the entry should be deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(EventOutbox).where(EventOutbox.id == entry.id)
        )
        remaining = result.scalar_one_or_none()
        assert remaining is None, "Entry should have been deleted after successful publish"
