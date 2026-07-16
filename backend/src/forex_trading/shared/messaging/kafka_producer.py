"""Kafka event bus implementation using aiokafka."""

from __future__ import annotations

import json
from typing import Any

import structlog
from aiokafka import AIOKafkaProducer

from forex_trading.shared.messaging.event_bus import EventBus

logger = structlog.get_logger()


class KafkaEventBus(EventBus):
    """Production event bus backed by Apache Kafka.

    Uses ``aiokafka`` for async produce with idempotence and acks=all.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        client_id: str = "forex-trading-engine",
        acks: str = "all",
        retries: int = 5,
        max_in_flight: int = 5,
        enable_idempotence: bool = True,
        compression_type: str = "gzip",
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._client_id = client_id
        self._acks = acks
        self._retries = retries
        self._max_in_flight = max_in_flight
        self._enable_idempotence = enable_idempotence
        self._compression_type = compression_type
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            client_id=self._client_id,
            acks=self._acks,
            retries=self._retries,
            max_in_flight_requests_per_connection=self._max_in_flight,
            enable_idempotence=self._enable_idempotence,
            compression_type=self._compression_type,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )
        await self._producer.start()
        logger.info(
            "kafka_producer_started",
            bootstrap_servers=self._bootstrap_servers,
            client_id=self._client_id,
        )

    async def publish(
        self,
        topic: str,
        key: str,
        value: dict[str, Any],
    ) -> None:
        if self._producer is None:
            raise RuntimeError("KafkaEventBus not started. Call start() first.")
        try:
            await self._producer.send_and_wait(topic=topic, key=key, value=value)
            logger.debug("kafka_published", topic=topic, key=key)
        except Exception as exc:
            logger.error(
                "kafka_publish_failed",
                topic=topic,
                key=key,
                error=str(exc),
            )
            raise

    async def publish_batch(
        self,
        topic: str,
        messages: list[tuple[str, dict[str, Any]]],
    ) -> None:
        if self._producer is None:
            raise RuntimeError("KafkaEventBus not started. Call start() first.")
        try:
            batch = self._producer.create_batch()
            for key, value in messages:
                key_bytes = key.encode("utf-8") if key else None
                value_bytes = json.dumps(value).encode("utf-8")
                # Note: aiokafka batch API may differ; fallback to sequential sends
                pass  # using sequential send for reliability
            for key, value in messages:
                await self._producer.send_and_wait(topic=topic, key=key, value=value)
            logger.debug("kafka_batch_published", topic=topic, count=len(messages))
        except Exception as exc:
            logger.error(
                "kafka_batch_publish_failed",
                topic=topic,
                error=str(exc),
            )
            raise

    async def close(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("kafka_producer_stopped")

    async def health_check(self) -> bool:
        if self._producer is None:
            return False
        try:
            # aiokafka doesn't have a simple ping; check that the client is running
            return self._producer._sender is not None and self._producer._sender._ready
        except Exception:
            return False
