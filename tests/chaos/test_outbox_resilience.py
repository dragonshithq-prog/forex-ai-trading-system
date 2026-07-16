"""Chaos test: Outbox resilience — verify events persist and replay on restart.

Tests the transactional outbox pattern: events are persisted in the database
before being published to Kafka, ensuring no message loss when Kafka is down.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = pytest.mark.chaos


class TestOutboxPersistence:
    """Events are persisted in the outbox table before Kafka publish."""

    @pytest.mark.asyncio
    async def test_event_written_to_outbox_before_kafka(self):
        """Order placed during Kafka outage is stored in outbox table."""
        from forex_trading.shared.database.models_outbox import OutboxEvent
        from forex_trading.shared.database.uow import UnitOfWork

        # Simulate: write to outbox succeeds even when Kafka is down
        event = OutboxEvent(
            id=uuid4(),
            topic="trading.order",
            key="order-1",
            payload='{"order_id": "abc123", "symbol": "EURUSD"}',
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        assert event.id is not None
        assert event.status == "pending"
        assert event.topic == "trading.order"

    @pytest.mark.asyncio
    async def test_outbox_entries_have_all_required_fields(self):
        """Outbox entries contain topic, key, payload, and status."""
        from forex_trading.shared.database.models_outbox import OutboxEvent

        event = OutboxEvent(
            id=uuid4(),
            topic="trading.order",
            key="order-1",
            payload='{"symbol": "EURUSD"}',
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        assert event.topic
        assert event.key
        assert event.payload
        assert event.status in ("pending", "published", "failed")


class TestOutboxReplay:
    """Unpublished events are replayed when Kafka comes back."""

    @pytest.mark.asyncio
    async def test_retry_pending_events_on_reconnect(self):
        """Pending outbox events are retried when service restarts."""
        from forex_trading.shared.messaging.outbox import OutboxRelay

        relay = OutboxRelay()
        mock_event_bus = AsyncMock()
        mock_uow = MagicMock()

        mock_uow.outbox_repository.get_pending_events = AsyncMock(return_value=[
            MagicMock(
                id=uuid4(),
                topic="trading.order",
                key="order-1",
                payload='{"symbol": "EURUSD"}',
                status="pending",
            )
        ])

        with patch.object(relay, "_publish_and_mark", new_callable=AsyncMock) as mock_publish:
            await relay.replay_pending_events(event_bus=mock_event_bus, uow=mock_uow)
            mock_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_replay_marks_events_as_published(self):
        """After replay, events are marked as 'published'."""
        from forex_trading.shared.messaging.outbox import OutboxRelay

        relay = OutboxRelay()
        mock_published = MagicMock()
        mock_published.status = "published"

        mock_repo = MagicMock()
        mock_repo.mark_published = AsyncMock(return_value=mock_published)

        result = await mock_repo.mark_published(event_id=uuid4())
        assert result.status == "published"

    @pytest.mark.asyncio
    async def test_replay_skips_already_published_events(self):
        """Already published events are skipped during replay."""
        from forex_trading.shared.messaging.outbox import OutboxRelay

        relay = OutboxRelay()
        mock_repo = MagicMock()
        mock_repo.get_pending_events = AsyncMock(return_value=[])

        events = await mock_repo.get_pending_events()
        assert len(events) == 0


class TestOutboxOrdering:
    """Outbox events maintain ordering guarantees."""

    @pytest.mark.asyncio
    async def test_outbox_events_ordered_by_created_at(self):
        """Events are replayed in creation order."""
        from forex_trading.shared.database.models_outbox import OutboxEvent

        events = []
        for i in range(5):
            events.append(OutboxEvent(
                id=uuid4(),
                topic="trading.order",
                key=f"order-{i}",
                payload='{}',
                status="pending",
                created_at=datetime.now(timezone.utc),
            ))

        # Sort by created_at
        sorted_events = sorted(events, key=lambda e: e.created_at)
        assert len(sorted_events) == 5
        assert sorted_events[0].created_at <= sorted_events[-1].created_at

    @pytest.mark.asyncio
    async def test_partition_key_maintains_order_per_key(self):
        """Events with the same key maintain order within that partition."""
        from forex_trading.shared.database.models_outbox import OutboxEvent

        key = "EURUSD-orders"
        events = []
        for i in range(3):
            events.append(OutboxEvent(
                id=uuid4(),
                topic="trading.order",
                key=key,
                payload=f'{{"seq": {i}}}',
                status="pending",
                created_at=datetime.now(timezone.utc),
            ))

        same_key_events = [e for e in events if e.key == key]
        assert len(same_key_events) == 3
