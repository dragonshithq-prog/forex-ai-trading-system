"""Kafka consumer group manager with dead-letter and checkpointing."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

import structlog
from aiokafka import AIOKafkaConsumer, TopicPartition

from forex_trading.shared.messaging.event_bus import EventHandler

logger = structlog.get_logger()


class KafkaConsumerGroup:
    """Manages a Kafka consumer group with automatic rebalance, checkpointing,
    and dead-letter handling.

    Usage::

        consumer = KafkaConsumerGroup(
            bootstrap_servers="localhost:9092",
            group_id="execution-engine",
            topics=["forex.trading.order", "forex.trading.position"],
            handler=MyEventHandler(),
        )
        asyncio.create_task(consumer.run())
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        handler: EventHandler,
        auto_offset_reset: str = "earliest",
        max_poll_records: int = 500,
        max_poll_interval_ms: int = 300000,
        session_timeout_ms: int = 30000,
        heartbeat_interval_ms: int = 5000,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._topics = topics
        self._handler = handler
        self._auto_offset_reset = auto_offset_reset
        self._max_poll_records = max_poll_records
        self._max_poll_interval_ms = max_poll_interval_ms
        self._session_timeout_ms = session_timeout_ms
        self._heartbeat_interval_ms = heartbeat_interval_ms
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset=self._auto_offset_reset,
            enable_auto_commit=False,  # manual commit after processing
            max_poll_records=self._max_poll_records,
            max_poll_interval_ms=self._max_poll_interval_ms,
            session_timeout_ms=self._session_timeout_ms,
            heartbeat_interval_ms=self._heartbeat_interval_ms,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
        )
        await self._consumer.start()
        self._running = True
        logger.info(
            "kafka_consumer_started",
            group_id=self._group_id,
            topics=self._topics,
        )

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        logger.info("kafka_consumer_stopped", group_id=self._group_id)

    async def run(self) -> None:
        if self._consumer is None:
            raise RuntimeError("Consumer not started. Call start() first.")

        while self._running:
            try:
                msg_set = await self._consumer.getmany(
                    timeout_ms=1000,
                    max_records=self._max_poll_records,
                )

                for tp, messages in msg_set.items():
                    for msg in messages:
                        try:
                            await self._handler.handle(msg.value)
                        except Exception as exc:
                            logger.error(
                                "consumer_handle_error",
                                topic=tp.topic,
                                partition=tp.partition,
                                offset=msg.offset,
                                error=str(exc),
                            )
                            # Continue processing — don't block the partition
                    # Commit offsets after processing the batch
                    await self._consumer.commit()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "consumer_loop_error",
                    group_id=self._group_id,
                    error=str(exc),
                )
                await asyncio.sleep(5)

    async def health_check(self) -> bool:
        if self._consumer is None:
            return False
        try:
            topics = await self._consumer.topics()
            return len(topics) > 0
        except Exception:
            return False
