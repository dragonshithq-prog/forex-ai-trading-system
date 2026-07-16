"""Transactional outbox — reliable event publication via the outbox pattern.

Every domain event that must be published to Kafka is first written to the
``event_outbox`` table in the *same* DB transaction as the aggregate write.

A background worker (``OutboxPublisher``) polls the table and publishes to
Kafka, deleting rows only after Kafka acknowledges receipt.

Performance Optimizations (Phase 8):
- Batch polling: fetches multiple pending events at once
- Concurrent publishing: semaphore-limited parallel publishes
- Adaptive poll interval: backs off when no events, polls faster when busy
- Batch size limits to prevent memory issues
- Exponential backoff on failure
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.models_trading import EventOutbox

logger = structlog.get_logger()

# Performance tuning constants
_MIN_POLL_INTERVAL = 0.05  # 50ms when busy
_MAX_POLL_INTERVAL = 2.0  # 2s when idle
_POLL_INTERVAL_SCALE = 1.5  # multiplicative backoff
_BATCH_SIZE = 100
_MAX_BATCH_SIZE = 500  # hard limit for memory protection
_MAX_CONCURRENT_PUBLISHES = 10  # semaphore limit
_ADAPTIVE_EMPTY_THRESHOLD = 3  # consecutive empty polls before backing off
_ADAPTIVE_BUSY_THRESHOLD = 2  # consecutive full polls before speeding up
_MAX_RETRIES = 5
_DEAD_LETTER_AFTER_RETRIES = 5
_METRICS_INTERVAL = 60  # report metrics every 60s

# Module-level state for adaptive polling
_adaptive_state: dict[str, Any] = {
    "consecutive_empty": 0,
    "consecutive_full": 0,
    "current_interval": _MIN_POLL_INTERVAL,
    "total_published": 0,
    "total_failed": 0,
    "last_metrics_report": 0.0,
}


class OutboxPublisher:
    """Polls the event_outbox table and publishes events to Kafka.

    Usage (called from DI container during startup)::

        publisher = OutboxPublisher(kafka_producer, uow_factory)
        asyncio.create_task(publisher.run())

    Performance features:
    - Batch polling with configurable batch size
    - Concurrent publishing with semaphore
    - Adaptive poll interval (backoff when empty, faster when busy)
    - Memory-safe batch size limits
    - Exponential backoff on publish failures
    """

    def __init__(
        self,
        kafka_producer: Any,  # KafkaEventBus
        session_factory: Any,  # callable that returns an AsyncSession
        batch_size: int = _BATCH_SIZE,
        max_concurrent: int = _MAX_CONCURRENT_PUBLISHES,
        min_interval: float = _MIN_POLL_INTERVAL,
        max_interval: float = _MAX_POLL_INTERVAL,
    ) -> None:
        self._producer = kafka_producer
        self._session_factory = session_factory
        self._batch_size = min(batch_size, _MAX_BATCH_SIZE)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_interval = min_interval
        self._max_interval = max_interval
        self._running = False
        self._task: asyncio.Task | None = None

        # Adaptive polling state (per-instance)
        self._consecutive_empty = 0
        self._consecutive_full = 0
        self._current_interval = min_interval
        self._total_published = 0
        self._total_failed = 0

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "outbox_publisher_started",
            batch_size=self._batch_size,
            max_concurrent=self._semaphore._value,
            min_interval=self._min_interval,
            max_interval=self._max_interval,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(
            "outbox_publisher_stopped",
            total_published=self._total_published,
            total_failed=self._total_failed,
        )

    async def _run_loop(self) -> None:
        """Main polling loop with adaptive interval."""
        while self._running:
            loop_start = time_monotonic()
            try:
                published_count = await self._publish_batch()
                self._adapt_interval(published_count)
                self._report_metrics_periodic()
            except Exception as exc:
                logger.error("outbox_publish_batch_error", error=str(exc))
                # On error, back off
                self._current_interval = min(
                    self._current_interval * _POLL_INTERVAL_SCALE,
                    self._max_interval,
                )

            elapsed = time_monotonic() - loop_start
            sleep_time = max(0.0, self._current_interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def _publish_batch(self) -> int:
        """Fetch a batch of pending events and publish them concurrently.

        Returns number of events successfully published.
        """
        events: list[EventOutbox] = []
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventOutbox)
                .where(EventOutbox.status == EventOutbox.OutboxStatus.PENDING)
                .order_by(EventOutbox.created_at.asc())
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            events = list(result.scalars().all())
            if not events:
                return 0

            # Mark all as PUBLISHING in one batch
            event_ids = [e.id for e in events]
            from sqlalchemy import update as sa_update
            await session.execute(
                sa_update(EventOutbox)
                .where(EventOutbox.id.in_(event_ids))
                .values(status=EventOutbox.OutboxStatus.PUBLISHING)
            )
            await session.commit()

        if not events:
            return 0

        # Concurrently publish all events using semaphore
        publish_tasks = []
        for event in events:
            task = asyncio.create_task(self._publish_single(event))
            publish_tasks.append(task)

        results = await asyncio.gather(*publish_tasks, return_exceptions=True)

        # Process results (mark published/dead-letter in DB)
        published_count = 0
        async with self._session_factory() as session:
            for event, result in zip(events, results):
                if isinstance(result, Exception):
                    await self._mark_failed(session, event, str(result))
                elif result is True:
                    await self._mark_published(session, event)
                    published_count += 1
                else:
                    await self._mark_failed(session, event, str(result) if result else "unknown error")
            await session.commit()

        self._total_published += published_count
        return published_count

    async def _publish_single(self, event: EventOutbox) -> bool:
        """Publish a single event to Kafka.

        Runs under the semaphore to limit concurrency.
        """
        async with self._semaphore:
            topic = self._resolve_topic(event.event_type)
            key = str(event.aggregate_id) if event.aggregate_id else str(event.id)
            try:
                await self._producer.publish(
                    topic=topic,
                    key=key,
                    value={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "event_version": event.event_version,
                        "aggregate_id": str(event.aggregate_id) if event.aggregate_id else None,
                        "aggregate_type": event.aggregate_type,
                        "payload": event.payload,
                        "trace_id": event.trace_id,
                        "timestamp": event.created_at.isoformat(),
                    },
                )
                return True
            except Exception as exc:
                logger.error(
                    "outbox_publish_failed",
                    event_id=str(event.id),
                    event_type=event.event_type,
                    error=str(exc),
                )
                return False

    async def _mark_published(self, session: AsyncSession, event: EventOutbox) -> None:
        """Mark event as published and delete it."""
        from sqlalchemy import delete as sa_delete
        await session.execute(
            sa_delete(EventOutbox).where(EventOutbox.id == event.id)
        )

    async def _mark_failed(self, session: AsyncSession, event: EventOutbox, error: str) -> None:
        """Increment retry count and move to dead-letter if exceeded."""
        from sqlalchemy import update as sa_update

        new_attempts = (event.publish_attempts or 0) + 1
        if new_attempts >= _DEAD_LETTER_AFTER_RETRIES:
            await session.execute(
                sa_update(EventOutbox)
                .where(EventOutbox.id == event.id)
                .values(
                    status=EventOutbox.OutboxStatus.DEAD_LETTER,
                    publish_attempts=new_attempts,
                    last_error=error,
                )
            )
            self._total_failed += 1
            logger.error(
                "outbox_dead_letter",
                event_id=str(event.id),
                event_type=event.event_type,
                error=error,
                attempts=new_attempts,
            )
        else:
            await session.execute(
                sa_update(EventOutbox)
                .where(EventOutbox.id == event.id)
                .values(
                    status=EventOutbox.OutboxStatus.FAILED,
                    publish_attempts=new_attempts,
                    last_error=error,
                )
            )

    def _adapt_interval(self, published_count: int) -> None:
        """Adapt poll interval based on whether we found events.

        - If empty for N consecutive polls, back off (increase interval)
        - If full for N consecutive polls, speed up (decrease interval)
        """
        if published_count == 0:
            self._consecutive_empty += 1
            self._consecutive_full = 0
            if self._consecutive_empty >= _ADAPTIVE_EMPTY_THRESHOLD:
                self._current_interval = min(
                    self._current_interval * _POLL_INTERVAL_SCALE,
                    self._max_interval,
                )
        else:
            self._consecutive_full += 1
            self._consecutive_empty = 0
            if self._consecutive_full >= _ADAPTIVE_BUSY_THRESHOLD and published_count >= self._batch_size // 2:
                self._current_interval = max(
                    self._current_interval / _POLL_INTERVAL_SCALE,
                    self._min_interval,
                )

    def _report_metrics_periodic(self) -> None:
        """Periodically log performance metrics."""
        from forex_trading.shared.monitoring import outbox_events_total, outbox_latency_seconds
        now = time_monotonic()
        if now - _adaptive_state["last_metrics_report"] >= _METRICS_INTERVAL:
            _adaptive_state["last_metrics_report"] = now
            outbox_events_total.labels(status="published").inc(self._total_published)
            outbox_events_total.labels(status="failed").inc(self._total_failed)
            logger.info(
                "outbox_metrics",
                total_published=self._total_published,
                total_failed=self._total_failed,
                current_interval_ms=round(self._current_interval * 1000, 1),
                batch_size=self._batch_size,
            )

    @staticmethod
    def _resolve_topic(event_type: str) -> str:
        prefix = "forex."
        topic_map: dict[str, str] = {
            "market.tick": f"{prefix}market.tick",
            "market.candle_closed": f"{prefix}market.candle",
            "trading.signal.generated": f"{prefix}trading.signal",
            "trading.order.placed": f"{prefix}trading.order",
            "trading.order.filled": f"{prefix}trading.order",
            "trading.order.rejected": f"{prefix}trading.order",
            "trading.order.cancelled": f"{prefix}trading.order",
            "trading.position.opened": f"{prefix}trading.position",
            "trading.position.closed": f"{prefix}trading.position",
            "trading.position.modified": f"{prefix}trading.position",
            "risk.alert": f"{prefix}risk.alert",
            "risk.circuit_breaker": f"{prefix}risk.circuit_breaker",
            "risk.override": f"{prefix}risk.override",
        }
        return topic_map.get(event_type, f"{prefix}event.{event_type}")


def create_outbox_entry(
    aggregate_type: str,
    aggregate_id: uuid.UUID | None,
    event_type: str,
    payload: dict[str, Any],
    trace_id: str | None = None,
    event_version: int = 1,
) -> dict[str, Any]:
    """Create the dict for an outbox entry (used by UnitOfWork)."""
    return {
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "event_type": event_type,
        "event_version": event_version,
        "payload": payload,
        "trace_id": trace_id,
    }


def time_monotonic() -> float:
    """Wrapper for monotonic clock, useful for testing."""
    import time
    return time.monotonic()


def _reset_adaptive_state() -> None:
    """Reset adaptive polling state (used in tests)."""
    global _adaptive_state
    _adaptive_state = {
        "consecutive_empty": 0,
        "consecutive_full": 0,
        "current_interval": _MIN_POLL_INTERVAL,
        "total_published": 0,
        "total_failed": 0,
        "last_metrics_report": 0.0,
    }
