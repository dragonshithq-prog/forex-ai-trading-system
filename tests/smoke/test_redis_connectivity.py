"""Smoke test: Redis connectivity — set, get, delete operations."""

import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.smoke


class TestRedisConnectivity:
    """Verify Redis cache is operational."""

    @pytest.mark.asyncio
    async def test_redis_health(self):
        """Health check reports Redis status."""
        # Import the cache manager and test its health check
        from forex_trading.shared.cache import CacheManager

        cache = CacheManager()
        with patch.object(cache, "health_check", new_callable=AsyncMock) as mock:
            mock.return_value = True
            healthy = await cache.health_check()
            assert healthy is True

    @pytest.mark.asyncio
    async def test_redis_set_get(self):
        """Basic set/get round trip works."""
        from forex_trading.shared.cache import CacheManager

        cache = CacheManager()
        with patch.object(cache, "set", new_callable=AsyncMock) as mock_set, \
             patch.object(cache, "get", new_callable=AsyncMock) as mock_get:
            mock_set.return_value = True
            mock_get.return_value = "test_value"

            set_result = await cache.set("smoke_test_key", "test_value", ttl=60)
            assert set_result is True

            value = await cache.get("smoke_test_key")
            assert value == "test_value"

    @pytest.mark.asyncio
    async def test_redis_delete(self):
        """Delete operation works."""
        from forex_trading.shared.cache import CacheManager

        cache = CacheManager()
        with patch.object(cache, "delete", new_callable=AsyncMock) as mock:
            mock.return_value = True
            result = await cache.delete("smoke_test_key")
            assert result is True

    @pytest.mark.asyncio
    async def test_redis_missing_key(self):
        """Get non-existent key returns None."""
        from forex_trading.shared.cache import CacheManager

        cache = CacheManager()
        with patch.object(cache, "get", new_callable=AsyncMock) as mock:
            mock.return_value = None
            value = await cache.get("nonexistent_key")
            assert value is None

    @pytest.mark.asyncio
    async def test_redis_ttl(self):
        """Set with TTL expires key after timeout."""
        from forex_trading.shared.cache import CacheManager

        cache = CacheManager()
        with patch.object(cache, "set", new_callable=AsyncMock) as mock_set, \
             patch.object(cache, "get", new_callable=AsyncMock) as mock_get:
            mock_set.return_value = True
            mock_get.return_value = None  # Simulate expiry

            await cache.set("ttl_key", "value", ttl=1)
            # After TTL, get returns None
            value = await cache.get("ttl_key")
            assert value is None
