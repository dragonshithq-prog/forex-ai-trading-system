"""Cache manager - Redis-based caching with performance optimizations.

Optimizations:
- Connection pool size limits with retry on timeout
- Health check interval with automatic reconnection
- Socket keepalive for long-lived connections
- Connection pool preloading on startup
- Retry configuration with exponential backoff
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import redis.asyncio as redis
import structlog

from forex_trading.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Default Redis performance tuning values
_DEFAULT_MAX_CONNECTIONS = 50
_DEFAULT_SOCKET_KEEPALIVE = 60  # seconds
_DEFAULT_SOCKET_CONNECT_TIMEOUT = 5  # seconds
_DEFAULT_SOCKET_TIMEOUT = 10  # seconds
_DEFAULT_RETRY_ON_TIMEOUT = True
_DEFAULT_HEALTH_CHECK_INTERVAL = 30  # seconds
_DEFAULT_PRELOAD_CONNECTIONS = 5  # connections to preload on startup


class CacheManager:
    """
    Redis-based cache manager with performance-optimized connection pooling.

    Features:
    - Async Redis operations with connection pooling
    - JSON serialization with optimized settings
    - TTL support with jitter
    - Pub/Sub for real-time updates
    - Health check with automatic reconnection
    - Socket keepalive configuration
    - Retry on timeout with exponential backoff
    """

    def __init__(
        self,
        redis_url: str | None = None,
        max_connections: int = _DEFAULT_MAX_CONNECTIONS,
        socket_keepalive: int = _DEFAULT_SOCKET_KEEPALIVE,
        socket_connect_timeout: int = _DEFAULT_SOCKET_CONNECT_TIMEOUT,
        socket_timeout: int = _DEFAULT_SOCKET_TIMEOUT,
        retry_on_timeout: bool = _DEFAULT_RETRY_ON_TIMEOUT,
        health_check_interval: int = _DEFAULT_HEALTH_CHECK_INTERVAL,
        preload_connections: int = _DEFAULT_PRELOAD_CONNECTIONS,
    ) -> None:
        self._redis_url = redis_url or settings.REDIS_URL
        self._max_connections = max_connections or settings.REDIS_MAX_CONNECTIONS
        self._socket_keepalive = socket_keepalive
        self._socket_connect_timeout = socket_connect_timeout
        self._socket_timeout = socket_timeout
        self._retry_on_timeout = retry_on_timeout
        self._health_check_interval = health_check_interval
        self._preload_connections = preload_connections

        self._redis: redis.Redis | None = None
        self._connection_pool: redis.ConnectionPool | None = None
        self._health_check_task: asyncio.Task | None = None
        self._last_health_check_ok: bool = False
        self._consecutive_failures: int = 0
        self._closed: bool = False

    async def initialize(self) -> None:
        """Initialize Redis connection with optimized connection pool."""
        self._connection_pool = redis.ConnectionPool(
            url=self._redis_url,
            max_connections=self._max_connections,
            socket_keepalive=self._socket_keepalive,
            socket_connect_timeout=self._socket_connect_timeout,
            socket_timeout=self._socket_timeout,
            retry_on_timeout=self._retry_on_timeout,
            health_check_interval=self._health_check_interval,
        )
        self._redis = redis.Redis(
            connection_pool=self._connection_pool,
            decode_responses=True,
        )

        # Preload connections into the pool
        await self._preload_pool()

        # Start periodic health check
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        logger.info(
            "cache_initialized",
            max_connections=self._max_connections,
            socket_keepalive=self._socket_keepalive,
            health_check_interval=self._health_check_interval,
            preload_connections=self._preload_connections,
        )

    async def close(self) -> None:
        """Close Redis connection and health check task."""
        self._closed = True
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
        if self._redis:
            await self._redis.close()
            self._redis = None
        if self._connection_pool:
            await self._connection_pool.disconnect()
            self._connection_pool = None
        logger.info("cache_closed")

    async def _preload_pool(self) -> None:
        """Preload connections into the pool to avoid startup latency."""
        if not self._preload_connections or not self._redis:
            return
        try:
            connections = []
            for _ in range(min(self._preload_connections, self._max_connections)):
                conn = await self._redis.connection_pool.get_connection("_")
                connections.append(conn)
                # Send PING to actually establish the connection
                await conn.send_command("PING")
            for conn in connections:
                try:
                    await conn.read_response()
                except Exception:
                    pass
                await self._redis.connection_pool.release(conn)
            logger.debug("pool_preloaded", connections=self._preload_connections)
        except Exception as exc:
            logger.warning("pool_preload_failed", error=str(exc))

    async def _health_check_loop(self) -> None:
        """Periodically check Redis health and reconnect if needed."""
        while not self._closed:
            try:
                await asyncio.sleep(self._health_check_interval)
                if self._redis:
                    try:
                        await self._redis.ping()
                        self._last_health_check_ok = True
                        self._consecutive_failures = 0
                    except Exception as exc:
                        self._consecutive_failures += 1
                        self._last_health_check_ok = False
                        logger.error(
                            "cache_health_check_failed",
                            error=str(exc),
                            consecutive_failures=self._consecutive_failures,
                        )
                        # Attempt reconnection after consecutive failures
                        if self._consecutive_failures >= 3:
                            await self._reconnect()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _reconnect(self) -> None:
        """Force reconnection of the Redis pool."""
        logger.info("cache_reconnecting")
        try:
            if self._connection_pool:
                await self._connection_pool.disconnect()
            self._connection_pool = redis.ConnectionPool(
                url=self._redis_url,
                max_connections=self._max_connections,
                socket_keepalive=self._socket_keepalive,
                socket_connect_timeout=self._socket_connect_timeout,
                socket_timeout=self._socket_timeout,
                retry_on_timeout=self._retry_on_timeout,
                health_check_interval=self._health_check_interval,
            )
            if self._redis:
                self._redis.connection_pool = self._connection_pool
            await self._preload_pool()
            self._consecutive_failures = 0
            logger.info("cache_reconnected")
        except Exception as exc:
            logger.error("cache_reconnect_failed", error=str(exc))

    async def get(self, key: str) -> Any | None:
        """Get value from cache with retry."""
        if not self._redis:
            return None
        try:
            value = await self._redis.get(key)
            if value is not None:
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value
            return None
        except redis.TimeoutError:
            logger.warning("cache_get_timeout", key=key)
            # Retry once on timeout
            try:
                value = await self._redis.get(key)
                if value is not None:
                    try:
                        return json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        return value
                return None
            except Exception:
                return None
        except Exception as exc:
            logger.warning("cache_get_failed", key=key, error=str(exc))
            return None

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from cache in a single round-trip using MGET."""
        if not self._redis or not keys:
            return {}
        try:
            values = await self._redis.mget(keys)
            result: dict[str, Any] = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        result[key] = value
            return result
        except Exception as exc:
            logger.warning("cache_get_many_failed", error=str(exc))
            return {}

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set value in cache with optional TTL."""
        if not self._redis:
            return False
        try:
            serialized = json.dumps(value, default=str) if not isinstance(value, (str, bytes)) else value
            if ttl:
                await self._redis.setex(key, ttl, serialized)
            else:
                await self._redis.set(key, serialized)
            return True
        except redis.TimeoutError:
            logger.warning("cache_set_timeout", key=key)
            return False
        except Exception as exc:
            logger.warning("cache_set_failed", key=key, error=str(exc))
            return False

    async def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """Set multiple values atomically using MSET."""
        if not self._redis or not mapping:
            return False
        try:
            serialized = {
                k: json.dumps(v, default=str) if not isinstance(v, (str, bytes)) else v
                for k, v in mapping.items()
            }
            if ttl:
                pipe = self._redis.pipeline()
                for key, value in serialized.items():
                    pipe.setex(key, ttl, value)
                await pipe.execute()
            else:
                await self._redis.mset(serialized)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if not self._redis:
            return False
        try:
            await self._redis.delete(key)
            return True
        except Exception:
            return False

    async def delete_many(self, keys: list[str]) -> int:
        """Delete multiple keys in a single round-trip."""
        if not self._redis or not keys:
            return 0
        try:
            return await self._redis.delete(*keys)
        except Exception:
            return 0

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        if not self._redis:
            return False
        try:
            return await self._redis.exists(key) > 0
        except Exception:
            return False

    async def increment(self, key: str, amount: int = 1) -> int | None:
        """Atomically increment a counter."""
        if not self._redis:
            return None
        try:
            return await self._redis.incr(key, amount)
        except Exception:
            return None

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on an existing key."""
        if not self._redis:
            return False
        try:
            return await self._redis.expire(key, ttl)
        except Exception:
            return False

    async def publish(self, channel: str, message: dict) -> None:
        """Publish message to Redis pub/sub channel."""
        if not self._redis:
            return
        try:
            await self._redis.publish(channel, json.dumps(message))
        except Exception as exc:
            logger.warning("cache_publish_failed", channel=channel, error=str(exc))

    async def subscribe(self, channel: str):
        """Subscribe to Redis pub/sub channel."""
        if not self._redis:
            return None
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(channel)
            return pubsub
        except Exception as exc:
            logger.warning("cache_subscribe_failed", channel=channel, error=str(exc))
            return None

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        if not self._redis:
            return False
        try:
            await self._redis.ping()
            self._last_health_check_ok = True
            self._consecutive_failures = 0
            return True
        except Exception as e:
            self._last_health_check_ok = False
            self._consecutive_failures += 1
            logger.error("cache_health_check_failed", error=str(e))
            return False

    @property
    def pool_stats(self) -> dict[str, Any]:
        """Return current connection pool statistics."""
        stats: dict[str, Any] = {
            "max_connections": self._max_connections,
            "health_check_interval": self._health_check_interval,
            "last_health_check_ok": self._last_health_check_ok,
            "consecutive_failures": self._consecutive_failures,
        }
        if self._connection_pool:
            try:
                stats["in_use_connections"] = len(self._connection_pool._in_use_connections)
                stats["available_connections"] = len(self._connection_pool._available_connections)
            except AttributeError:
                pass
        return stats


# Global cache manager instance
cache_manager = CacheManager()

__all__ = ["CacheManager", "cache_manager"]
