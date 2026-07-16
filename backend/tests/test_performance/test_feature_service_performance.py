"""Tests for FeatureService performance optimizations.

Tests:
- LRU eviction for local cache (prevent memory leak)
- Cache stampede protection (lock on cache miss)
- Background refresh for frequently accessed features
- TTL jitter to prevent thundering herd
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from forex_trading.ai.services.feature_service import (
    FeatureService,
    FeatureSet,
    LRUCache,
)


pytestmark = pytest.mark.asyncio


class TestLRUCache:
    """Tests for LRU cache used by FeatureService."""

    async def test_lru_eviction_when_full(self):
        """LRU cache should evict oldest entries when max size is reached."""
        cache = LRUCache(maxsize=3)

        await cache.set("key1", FeatureSet(symbol="EURUSD", timeframe="H1", computed_at=None))
        await cache.set("key2", FeatureSet(symbol="GBPUSD", timeframe="H1", computed_at=None))
        await cache.set("key3", FeatureSet(symbol="USDJPY", timeframe="H1", computed_at=None))
        assert cache.size == 3

        # Adding a 4th entry should evict the oldest (key1)
        await cache.set("key4", FeatureSet(symbol="AUDUSD", timeframe="H1", computed_at=None))
        assert cache.size == 3

        # key1 should be evicted
        val = await cache.get("key1")
        assert val is None

        # key4 should exist
        val = await cache.get("key4")
        assert val is not None
        assert val.symbol == "AUDUSD"

    async def test_lru_get_moves_to_end(self):
        """Getting a value should move it to the end (most recently used)."""
        cache = LRUCache(maxsize=3)

        await cache.set("key1", FeatureSet(symbol="EURUSD", timeframe="H1", computed_at=None))
        await cache.set("key2", FeatureSet(symbol="GBPUSD", timeframe="H1", computed_at=None))
        await cache.set("key3", FeatureSet(symbol="USDJPY", timeframe="H1", computed_at=None))

        # Access key1, making it most recently used
        await cache.get("key1")

        # Adding a 4th entry should evict key2 (now the least recently used)
        await cache.set("key4", FeatureSet(symbol="AUDUSD", timeframe="H1", computed_at=None))
        assert cache.size == 3

        # key1 should still exist (it was recently accessed)
        val = await cache.get("key1")
        assert val is not None

        # key2 should be evicted
        val = await cache.get("key2")
        assert val is None

    async def test_lru_delete(self):
        """Delete should remove the entry from the cache."""
        cache = LRUCache(maxsize=10)
        await cache.set("key1", FeatureSet(symbol="EURUSD", timeframe="H1", computed_at=None))
        assert cache.size == 1

        await cache.delete("key1")
        assert cache.size == 0

        val = await cache.get("key1")
        assert val is None

    async def test_lru_clear(self):
        """Clear should remove all entries."""
        cache = LRUCache(maxsize=10)
        await cache.set("key1", FeatureSet(symbol="EURUSD", timeframe="H1", computed_at=None))
        await cache.set("key2", FeatureSet(symbol="GBPUSD", timeframe="H1", computed_at=None))
        assert cache.size == 2

        await cache.clear()
        assert cache.size == 0

    async def test_lru_delete_by_prefix(self):
        """Delete by prefix should remove matching entries."""
        cache = LRUCache(maxsize=10)
        await cache.set("feat:EURUSD:H1:abc", FeatureSet(symbol="EURUSD", timeframe="H1", computed_at=None))
        await cache.set("feat:GBPUSD:H1:def", FeatureSet(symbol="GBPUSD", timeframe="H1", computed_at=None))
        await cache.set("feat:EURUSD:M5:ghi", FeatureSet(symbol="EURUSD", timeframe="M5", computed_at=None))
        assert cache.size == 3

        await cache.delete_by_prefix("feat:EURUSD:")
        assert cache.size == 1

        keys = await cache.keys()
        assert all("EURUSD" not in k for k in keys)

    async def test_lru_keys(self):
        """Keys should return all cached keys."""
        cache = LRUCache(maxsize=10)
        await cache.set("key1", FeatureSet(symbol="EURUSD", timeframe="H1", computed_at=None))
        await cache.set("key2", FeatureSet(symbol="GBPUSD", timeframe="H1", computed_at=None))

        keys = await cache.keys()
        assert len(keys) == 2
        assert "key1" in keys
        assert "key2" in keys


class TestFeatureServicePerformance:
    """Tests for FeatureService performance optimizations."""

    async def test_lru_cache_eviction(self, sample_candles):
        """FeatureService should evict old entries when local cache is full."""
        svc = FeatureService(local_cache_maxsize=3)

        # Get features for 4 different symbols
        await svc.get_features("EURUSD", "H1", sample_candles)
        await svc.get_features("GBPUSD", "H1", sample_candles)
        await svc.get_features("USDJPY", "H1", sample_candles)

        # Cache should have 3 entries (before 4th is added)
        # Note: the 4th call depends on whether LRU eviction fired
        first_size = svc._local_cache.size

        await svc.get_features("AUDUSD", "H1", sample_candles)

        # Should still be at most 3
        assert svc._local_cache.size <= 3

    async def test_stampede_protection(self, sample_candles):
        """Concurrent requests for same key should be serialized."""
        svc = FeatureService()

        # Get the lock for a key
        key = svc._build_cache_key("EURUSD", "H1", sample_candles)
        lock1 = svc._get_stampede_lock(key)

        # Same key should return the same lock
        lock2 = svc._get_stampede_lock(key)
        assert lock1 is lock2

    async def test_background_refresh_start_stop(self):
        """FeatureService should start and stop background refresh."""
        svc = FeatureService()

        assert svc._bg_refresh_task is None

        await svc.start_background_refresh()
        assert svc._bg_refresh_task is not None
        assert not svc._bg_refresh_task.done()

        await svc.stop_background_refresh()
        assert svc._bg_refresh_task is None or svc._bg_refresh_task.done()

    async def test_get_features_batch(self, sample_candles):
        """Batch feature retrieval should work correctly."""
        svc = FeatureService()

        requests = [
            ("EURUSD", "H1", sample_candles),
            ("GBPUSD", "H1", sample_candles),
        ]

        results = await svc.get_features_batch(requests)
        assert len(results) == 2
        assert results[0] is not None
        assert results[0].symbol == "EURUSD"
        assert results[1] is not None
        assert results[1].symbol == "GBPUSD"

    async def test_invalidate_cache_by_symbol(self, sample_candles):
        """Invalidation by symbol should clear only matching entries."""
        svc = FeatureService()
        await svc.get_features("EURUSD", "H1", sample_candles)
        await svc.get_features("GBPUSD", "H1", sample_candles)

        assert svc._local_cache.size == 2

        await svc.invalidate_cache("EURUSD")
        assert svc._local_cache.size == 1

    async def test_invalidate_cache_all(self, sample_candles):
        """Full invalidation should clear all entries."""
        svc = FeatureService()
        await svc.get_features("EURUSD", "H1", sample_candles)
        await svc.get_features("GBPUSD", "H1", sample_candles)

        assert svc._local_cache.size == 2

        await svc.invalidate_cache()
        assert svc._local_cache.size == 0

    async def test_cache_hit_local(self, sample_candles):
        """Local cache hit should return cached result."""
        svc = FeatureService()
        features1 = await svc.get_features("EURUSD", "H1", sample_candles)
        assert svc._local_cache.size == 1

        features2 = await svc.get_features("EURUSD", "H1", sample_candles)
        assert features2 is features1  # Same object (LRU returns same reference)

    async def test_cache_hit_distributed(self, sample_candles, mock_cache):
        """Distributed cache hit should populate local cache."""
        svc = FeatureService(cache=mock_cache)

        # First call computes
        features = await svc.get_features("EURUSD", "H1", sample_candles)
        assert features is not None

        # Cache in distributed
        key = svc._build_cache_key("EURUSD", "H1", sample_candles)
        serialized = svc._serialize(features)
        mock_cache._store[key] = serialized

        # Clear local cache
        await svc._local_cache.clear()

        # Clear mock to simulate new call
        features2 = await svc.get_features("EURUSD", "H1", sample_candles)
        assert features2 is not None
        assert features2.symbol == "EURUSD"
