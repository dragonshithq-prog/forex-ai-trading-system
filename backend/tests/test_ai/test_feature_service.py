"""Tests for FeatureService — feature computation and caching."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from forex_trading.ai.services.feature_service import FeatureService, FeatureSet


pytestmark = pytest.mark.asyncio


class TestFeatureService:
    """Tests for the centralized feature extraction service."""

    async def test_get_features_returns_feature_set(self, sample_candles):
        """Given enough candles, get_features should return a FeatureSet."""
        svc = FeatureService()
        features = await svc.get_features("EURUSD", "H1", sample_candles)
        assert features is not None
        assert isinstance(features, FeatureSet)
        assert features.symbol == "EURUSD"
        assert features.timeframe == "H1"
        assert features.computed_at is not None

    async def test_insufficient_candles_returns_none(self):
        """Fewer than 50 candles should return None."""
        svc = FeatureService()
        features = await svc.get_features("EURUSD", "H1", [{"close": 1.1}] * 10)
        assert features is None

    async def test_empty_candles_returns_none(self):
        """No candles should return None."""
        svc = FeatureService()
        features = await svc.get_features("EURUSD", "H1", [])
        assert features is None

    async def test_local_cache_hit(self, sample_candles):
        """Repeated requests with the same candles should use the local cache."""
        svc = FeatureService()
        features1 = await svc.get_features("EURUSD", "H1", sample_candles)
        assert svc._local_cache.size == 1

        features2 = await svc.get_features("EURUSD", "H1", sample_candles)
        assert svc._local_cache.size == 1  # Still just one entry
        assert features2 is features1  # Same object from cache

    async def test_distributed_cache(self, sample_candles, mock_cache):
        """Cached results in distributed cache should be returned."""
        svc = FeatureService(cache=mock_cache)

        # First call computes and caches
        features1 = await svc.get_features("EURUSD", "H1", sample_candles)
        assert features1 is not None

        # Clear local cache to force distributed cache lookup
        await svc._local_cache.clear()

        # Mock the distributed cache to return the serialized features
        serialized = svc._serialize(features1)
        mock_cache.get = AsyncMock(return_value=serialized)

        # Second call should hit distributed cache
        features2 = await svc.get_features("EURUSD", "H1", sample_candles)
        assert features2 is not None
        assert features2.symbol == "EURUSD"

    async def test_local_cache_invalidation_by_symbol(self, sample_candles):
        """Invalidation by symbol should remove only matching entries."""
        svc = FeatureService()
        await svc.get_features("EURUSD", "H1", sample_candles)
        await svc.get_features("GBPUSD", "H1", sample_candles)
        assert svc._local_cache.size == 2

        await svc.invalidate_cache("EURUSD")
        assert svc._local_cache.size == 1

    async def test_local_cache_full_invalidation(self, sample_candles):
        """Full invalidation should clear all cache entries."""
        svc = FeatureService()
        await svc.get_features("EURUSD", "H1", sample_candles)
        await svc.invalidate_cache()
        assert svc._local_cache.size == 0

    async def test_feature_values_populated(self, sample_candles):
        """Feature values should be populated when enough data is available."""
        svc = FeatureService()
        features = await svc.get_features("EURUSD", "H1", sample_candles)

        if features:
            # With 200 candles, these should all be populated
            assert features.close is not None
            assert features.high is not None
            assert features.low is not None
            assert features.open is not None
            assert features.body is not None

    async def test_cache_key_deterministic(self, sample_candles):
        """Same inputs should produce the same cache key."""
        svc = FeatureService()
        key1 = svc._build_cache_key("EURUSD", "H1", sample_candles)
        key2 = svc._build_cache_key("EURUSD", "H1", sample_candles)
        assert key1 == key2

    async def test_cache_key_different_inputs(self, sample_candles):
        """Different inputs should produce different cache keys."""
        svc = FeatureService()
        key1 = svc._build_cache_key("EURUSD", "H1", sample_candles)
        key2 = svc._build_cache_key("GBPUSD", "H1", sample_candles)
        assert key1 != key2

    async def test_serialize_deserialize_roundtrip(self, sample_candles):
        """Serialization and deserialization should roundtrip correctly."""
        svc = FeatureService()
        features = await svc.get_features("EURUSD", "H1", sample_candles)
        if features:
            data = svc._serialize(features)
            restored = svc._deserialize(data)
            assert restored is not None
            assert restored.symbol == features.symbol
            assert restored.timeframe == features.timeframe

    async def test_numpy_fallback(self, sample_candles):
        """When pandas/ta is unavailable, numpy fallback should still work."""
        svc = FeatureService()
        with pytest.MonkeyPatch.context() as mp:
            import forex_trading.ai.services.feature_service as fs_mod
            mp.setattr(fs_mod, "pd", None)
            mp.setattr(fs_mod, "ta", None)

            features = await svc._compute("EURUSD", "H1", sample_candles)
            assert features is not None
            assert features.symbol == "EURUSD"
            # Some basic fields should be populated
            if features.close:
                assert features.close > 0
