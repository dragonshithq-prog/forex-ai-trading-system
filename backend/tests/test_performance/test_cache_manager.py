"""Tests for CacheManager performance optimizations.

Tests:
- Connection pool size limits
- Retry on timeout
- Health check interval
- Socket keepalive
- Connection pool preloading
- Batch operations (get_many, set_many, delete_many)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from forex_trading.shared.cache import CacheManager


pytestmark = pytest.mark.asyncio


class TestCacheManagerPerformance:
    """Tests for CacheManager performance optimizations."""

    async def test_initialization_with_custom_pool_params(self):
        """CacheManager should accept custom connection pool parameters."""
        cache = CacheManager(
            redis_url="redis://localhost:6379/0",
            max_connections=20,
            socket_keepalive=30,
            socket_connect_timeout=3,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=15,
            preload_connections=3,
        )
        assert cache._max_connections == 20
        assert cache._socket_keepalive == 30
        assert cache._socket_connect_timeout == 3
        assert cache._socket_timeout == 5
        assert cache._retry_on_timeout is True
        assert cache._health_check_interval == 15
        assert cache._preload_connections == 3

    async def test_default_parameters(self):
        """CacheManager should use sensible defaults."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        assert cache._max_connections >= 10
        assert cache._socket_keepalive > 0
        assert cache._socket_timeout > 0
        assert cache._retry_on_timeout is True
        assert cache._health_check_interval > 0

    async def test_get_many_empty(self):
        """get_many with empty list should return empty dict."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        result = await cache.get_many([])
        assert result == {}

    async def test_get_many_no_redis(self):
        """get_many should return empty dict when redis is not initialized."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        result = await cache.get_many(["key1", "key2"])
        assert result == {}

    async def test_set_many_empty(self):
        """set_many with empty mapping should return False."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        result = await cache.set_many({})
        assert result is False

    async def test_delete_many_empty(self):
        """delete_many with empty list should return 0."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        result = await cache.delete_many([])
        assert result == 0

    async def test_exists_no_redis(self):
        """exists should return False when redis is not initialized."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        result = await cache.exists("test_key")
        assert result is False

    async def test_increment_no_redis(self):
        """increment should return None when redis is not initialized."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        result = await cache.increment("test_counter")
        assert result is None

    async def test_expire_no_redis(self):
        """expire should return False when redis is not initialized."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        result = await cache.expire("test_key", 60)
        assert result is False

    async def test_publish_no_redis(self):
        """publish should not raise when redis is not initialized."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        # Should not raise
        await cache.publish("test_channel", {"data": "test"})

    async def test_subscribe_no_redis(self):
        """subscribe should return None when redis is not initialized."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        result = await cache.subscribe("test_channel")
        assert result is None

    async def test_pool_stats(self):
        """pool_stats should return connection pool diagnostics."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        stats = cache.pool_stats
        assert stats["max_connections"] > 0
        assert stats["health_check_interval"] > 0
        assert "last_health_check_ok" in stats
        assert "consecutive_failures" in stats

    async def test_health_check_no_redis(self):
        """health_check should return False when redis is not initialized."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        result = await cache.health_check()
        assert result is False

    async def test_get_retry_on_timeout(self):
        """get should retry once on timeout."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")

        # Mock redis to raise TimeoutError on first call
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(side_effect=[
            __import__("redis").TimeoutError("Timeout"),
            "cached_value",
        ])
        cache._redis = mock_redis

        result = await cache.get("test_key")
        assert result == "cached_value"
        assert mock_redis.get.call_count == 2

    async def test_set_handles_timeout(self):
        """set should return False on timeout."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")

        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock(side_effect=__import__("redis").TimeoutError("Timeout"))
        cache._redis = mock_redis

        result = await cache.set("test_key", "value", ttl=60)
        assert result is False

    async def test_health_check_increments_on_failure(self):
        """health_check should increment consecutive_failures on failure."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")

        # Set up a mock redis that fails
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("Connection failed"))
        cache._redis = mock_redis

        # Initial counter
        assert cache._consecutive_failures == 0

        # First failure
        result = await cache.health_check()
        assert result is False
        assert cache._consecutive_failures == 1

        # Second failure
        result = await cache.health_check()
        assert result is False
        assert cache._consecutive_failures == 2

    async def test_close_cleans_up(self):
        """close should clean up all resources."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        mock_redis = AsyncMock()
        cache._redis = mock_redis

        await cache.close()
        assert cache._closed is True
        mock_redis.close.assert_called_once()

    async def test_close_without_redis(self):
        """close should not raise when redis was never initialized."""
        cache = CacheManager(redis_url="redis://localhost:6379/0")
        # Should not raise
        await cache.close()
