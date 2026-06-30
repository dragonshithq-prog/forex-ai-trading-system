"""Cache manager - Redis-based caching."""

from typing import Any
import json

import redis.asyncio as redis
import structlog

from forex_trading.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class CacheManager:
    """
    Redis-based cache manager.

    Features:
    - Async Redis operations
    - JSON serialization
    - TTL support
    - Pub/Sub for real-time updates
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis: redis.Redis | None = None

    async def initialize(self) -> None:
        """Initialize Redis connection."""
        self._redis = redis.from_url(
            self._redis_url,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
        )
        logger.info("cache_initialized")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            logger.info("cache_closed")

    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        if not self._redis:
            return None
        value = await self._redis.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set value in cache."""
        if not self._redis:
            return False
        serialized = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        if ttl:
            await self._redis.setex(key, ttl, serialized)
        else:
            await self._redis.set(key, serialized)
        return True

    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if not self._redis:
            return False
        await self._redis.delete(key)
        return True

    async def publish(self, channel: str, message: dict) -> None:
        """Publish message to Redis pub/sub channel."""
        if not self._redis:
            return
        await self._redis.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str):
        """Subscribe to Redis pub/sub channel."""
        if not self._redis:
            return None
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        return pubsub

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        if not self._redis:
            return False
        try:
            await self._redis.ping()
            return True
        except Exception as e:
            logger.error("cache_health_check_failed", error=str(e))
            return False


# Global cache manager instance
cache_manager = CacheManager()
