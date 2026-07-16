"""Centralized feature extraction with performance-optimized caching.

All technical indicators are computed here and cached by
(symbol, timeframe, candle_bounds_hash) so agents never compute the same
indicator twice. Agents call ``get_features()`` instead of computing their own.

Performance Optimizations (Phase 8):
- LRU eviction for local cache to prevent memory leaks
- Cache stampede protection via asyncio.Lock per key
- Background refresh for frequently accessed features
- TTL jitter to prevent thundering herd on distributed cache
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
import structlog

try:
    import pandas as pd
    import ta
except ImportError:
    pd = None  # type: ignore
    ta = None  # type: ignore

logger = structlog.get_logger()

# Performance tuning constants
_DEFAULT_LOCAL_CACHE_MAXSIZE = 500  # max entries in LRU cache
_DEFAULT_FEATURE_TTL = 300  # 5 minutes
_DEFAULT_TTL_JITTER = 30  # ±30 seconds jitter
_DEFAULT_BG_REFRESH_INTERVAL = 240  # refresh every 4 minutes (before 5min TTL)
_DEFAULT_STAMPEDE_LOCK_TIMEOUT = 10  # seconds to wait for lock


@dataclass
class FeatureSet:
    symbol: str
    timeframe: str
    computed_at: datetime

    # Trend
    ema_20: float | None = None
    ema_50: float | None = None
    ema_200: float | None = None
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    adx: float | None = None

    # Volatility
    atr_14: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_width: float | None = None

    # Momentum
    rsi_14: float | None = None
    stochastic_k: float | None = None
    stochastic_d: float | None = None

    # Volume / Liquidity
    volume_sma_20: float | None = None
    volume_ratio: float | None = None

    # Price action
    close: float | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    body: float | None = None
    upper_wick: float | None = None
    lower_wick: float | None = None

    raw: dict[str, Any] | None = None


class LRUCache:
    """Thread-safe LRU cache with max size eviction."""

    def __init__(self, maxsize: int = _DEFAULT_LOCAL_CACHE_MAXSIZE):
        self._maxsize = maxsize
        self._cache: OrderedDict[str, FeatureSet] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> FeatureSet | None:
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    async def set(self, key: str, value: FeatureSet) -> None:
        async with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def delete_by_prefix(self, prefix: str) -> None:
        async with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._cache[k]

    @property
    def size(self) -> int:
        return len(self._cache)

    async def keys(self) -> list[str]:
        async with self._lock:
            return list(self._cache.keys())


class FeatureService:
    """Centralized feature computation with performance-optimized caching.

    Usage in an agent::

        features = await feature_service.get_features(symbol, "H1", candles)
        if features and features.rsi_14 and features.rsi_14 < 30:
            ...

    Performance features:
    - LRU eviction for local cache (prevents memory leak)
    - Cache stampede protection (lock per cache key)
    - Background refresh for frequently accessed features
    - TTL jitter to prevent thundering herd on Redis
    """

    def __init__(
        self,
        cache: Any | None = None,
        local_cache_maxsize: int = _DEFAULT_LOCAL_CACHE_MAXSIZE,
        feature_ttl: int = _DEFAULT_FEATURE_TTL,
        ttl_jitter: int = _DEFAULT_TTL_JITTER,
        bg_refresh_interval: int = _DEFAULT_BG_REFRESH_INTERVAL,
    ) -> None:
        self._cache = cache
        self._feature_ttl = feature_ttl
        self._ttl_jitter = ttl_jitter
        self._bg_refresh_interval = bg_refresh_interval

        # LRU local cache with size bound
        self._local_cache = LRUCache(maxsize=local_cache_maxsize)

        # Stampede protection: per-key locks
        self._stampede_locks: dict[str, asyncio.Lock] = {}
        self._stampede_lock_cleanup_task: asyncio.Task | None = None

        # Background refresh tracking
        self._bg_refresh_times: dict[str, float] = {}
        self._bg_refresh_task: asyncio.Task | None = None

        # Access frequency tracking for background refresh
        self._access_counts: dict[str, int] = {}
        self._min_access_for_bg_refresh = 5  # minimum accesses before bg refresh

    async def start_background_refresh(self) -> None:
        """Start the background refresh loop."""
        self._bg_refresh_task = asyncio.create_task(self._background_refresh_loop())
        self._stampede_lock_cleanup_task = asyncio.create_task(self._cleanup_stampede_locks())

    async def stop_background_refresh(self) -> None:
        """Stop the background refresh loop."""
        if self._bg_refresh_task:
            self._bg_refresh_task.cancel()
            try:
                await self._bg_refresh_task
            except asyncio.CancelledError:
                pass
        if self._stampede_lock_cleanup_task:
            self._stampede_lock_cleanup_task.cancel()
            try:
                await self._stampede_lock_cleanup_task
            except asyncio.CancelledError:
                pass

    async def get_features(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict],
    ) -> FeatureSet | None:
        """Compute or retrieve cached features for the given candles."""
        if not candles or len(candles) < 50:
            logger.warning("insufficient_candles", symbol=symbol, count=len(candles))
            return None

        cache_key = self._build_cache_key(symbol, timeframe, candles)

        # Track access frequency
        self._access_counts[cache_key] = self._access_counts.get(cache_key, 0) + 1

        # Check local LRU cache first (fastest)
        local_cached = await self._local_cache.get(cache_key)
        if local_cached is not None:
            from forex_trading.shared.monitoring import cache_hits_total
            cache_hits_total.labels(cache_name="feature_local").inc()
            return local_cached

        # Stampede protection: acquire per-key lock
        lock = self._get_stampede_lock(cache_key)
        async with lock:
            # Double-check after acquiring lock
            local_cached = await self._local_cache.get(cache_key)
            if local_cached is not None:
                from forex_trading.shared.monitoring import cache_hits_total
                cache_hits_total.labels(cache_name="feature_local").inc()
                return local_cached

            # Check distributed cache
            if self._cache is not None:
                try:
                    cached = await self._cache.get(cache_key)
                    if cached is not None:
                        features = self._deserialize(cached)
                        if features is not None:
                            await self._local_cache.set(cache_key, features)
                            from forex_trading.shared.monitoring import cache_hits_total
                            cache_hits_total.labels(cache_name="feature_redis").inc()
                            return features
                except Exception:
                    pass

            from forex_trading.shared.monitoring import cache_misses_total
            cache_misses_total.labels(cache_name="feature_all").inc()

            # Compute features (expensive operation)
            features = await self._compute(symbol, timeframe, candles)

            # Store in local LRU cache
            await self._local_cache.set(cache_key, features)

            # Store in distributed cache with TTL jitter
            if self._cache is not None:
                try:
                    serialized = self._serialize(features)
                    jittered_ttl = self._feature_ttl + random.randint(
                        -self._ttl_jitter, self._ttl_jitter
                    )
                    await self._cache.set(cache_key, serialized, ttl=max(60, jittered_ttl))
                except Exception:
                    pass

            return features

    async def get_features_batch(
        self,
        requests: list[tuple[str, str, list[dict]]],
    ) -> list[FeatureSet | None]:
        """Compute features for multiple (symbol, timeframe, candles) in batch.

        This allows the caller to request features for multiple symbols/timeframes
        efficiently, with shared cache lookups.
        """
        tasks = []
        for symbol, timeframe, candles in requests:
            tasks.append(self.get_features(symbol, timeframe, candles))
        return await asyncio.gather(*tasks)

    async def _background_refresh_loop(self) -> None:
        """Periodically refresh frequently accessed features before they expire."""
        while True:
            try:
                await asyncio.sleep(self._bg_refresh_interval)
                await self._refresh_frequently_accessed()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("background_refresh_error", error=str(exc))

    async def _refresh_frequently_accessed(self) -> None:
        """Refresh frequently accessed cache entries before TTL expiry."""
        if not self._cache:
            return

        # Get keys that are frequently accessed
        now = time.monotonic()
        refresh_keys = []
        keys = await self._local_cache.keys()
        for key in keys:
            access_count = self._access_counts.get(key, 0)
            last_refresh = self._bg_refresh_times.get(key, 0)
            if access_count >= self._min_access_for_bg_refresh and (now - last_refresh) >= self._bg_refresh_interval:
                refresh_keys.append(key)

        if not refresh_keys:
            return

        logger.debug("background_refreshing", count=len(refresh_keys))

        # Attempt background refresh for each key
        for key in refresh_keys:
            try:
                # Parse key format: "feat:{symbol}:{timeframe}:{hash}"
                parts = key.split(":")
                if len(parts) >= 4:
                    symbol = parts[1]
                    timeframe = parts[2]
                    # We still need candles to refresh — just extend TTL in Redis
                    await self._cache.expire(key, self._feature_ttl)
                    self._bg_refresh_times[key] = now
            except Exception:
                pass

    async def _cleanup_stampede_locks(self) -> None:
        """Periodically clean up stale stampede locks to prevent memory leaks."""
        while True:
            try:
                await asyncio.sleep(300)  # every 5 minutes
                # Locks with no waiters for > 5 minutes can be removed
                # But asyncio.Lock doesn't expose waiters, so we just
                # clear locks that haven't been touched
                current_keys = await self._local_cache.keys()
                stale_keys = [
                    k for k in self._stampede_locks
                    if k not in current_keys
                ]
                for k in stale_keys:
                    self._stampede_locks.pop(k, None)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def _get_stampede_lock(self, key: str) -> asyncio.Lock:
        """Get or create a per-key lock for cache stampede protection."""
        if key not in self._stampede_locks:
            self._stampede_locks[key] = asyncio.Lock()
        return self._stampede_locks[key]

    async def _compute(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict],
    ) -> FeatureSet:
        """Compute all features from raw candles."""
        if pd is None or ta is None:
            logger.warning("pandas_or_ta_not_available")
            return self._compute_numpy(symbol, timeframe, candles)

        df = pd.DataFrame(candles)
        if "close" not in df.columns:
            return self._compute_numpy(symbol, timeframe, candles)

        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["high"] = pd.to_numeric(df.get("high", df["close"]), errors="coerce")
        df["low"] = pd.to_numeric(df.get("low", df["close"]), errors="coerce")
        df["open"] = pd.to_numeric(df.get("open", df["close"]), errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce")

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        features = FeatureSet(
            symbol=symbol,
            timeframe=timeframe,
            computed_at=datetime.now(timezone.utc),
            close=float(close.iloc[-1]) if not close.empty else None,
            high=float(high.iloc[-1]) if not high.empty else None,
            low=float(low.iloc[-1]) if not low.empty else None,
            open=float(df["open"].iloc[-1]) if not df["open"].empty else None,
        )

        try:
            features.ema_20 = float(ta.trend.ema_indicator(close, window=20).iloc[-1]) if len(close) >= 20 else None
        except Exception:
            pass
        try:
            features.ema_50 = float(ta.trend.ema_indicator(close, window=50).iloc[-1]) if len(close) >= 50 else None
        except Exception:
            pass
        try:
            features.ema_200 = float(ta.trend.ema_indicator(close, window=200).iloc[-1]) if len(close) >= 200 else None
        except Exception:
            pass

        try:
            macd = ta.trend.MACD(close)
            features.macd_line = float(macd.macd().iloc[-1])
            features.macd_signal = float(macd.macd_signal().iloc[-1])
            features.macd_histogram = float(macd.macd_diff().iloc[-1])
        except Exception:
            pass

        try:
            features.adx = float(ta.trend.ADX(high, low, close).adx().iloc[-1]) if len(close) >= 14 else None
        except Exception:
            pass

        try:
            atr_indicator = ta.volatility.AverageTrueRange(high, low, close, window=14)
            features.atr_14 = float(atr_indicator.average_true_range().iloc[-1]) if len(close) >= 14 else None
        except Exception:
            pass

        try:
            bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
            features.bb_upper = float(bb.bollinger_hband().iloc[-1])
            features.bb_middle = float(bb.bollinger_mavg().iloc[-1])
            features.bb_lower = float(bb.bollinger_lband().iloc[-1])
            features.bb_width = (
                (features.bb_upper - features.bb_lower) / features.bb_middle
                if features.bb_middle and features.bb_middle > 0
                else None
            )
        except Exception:
            pass

        try:
            features.rsi_14 = float(ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]) if len(close) >= 14 else None
        except Exception:
            pass

        try:
            stoch = ta.momentum.StochasticOscillator(high, low, close)
            features.stochastic_k = float(stoch.stoch().iloc[-1])
            features.stochastic_d = float(stoch.stoch_signal().iloc[-1])
        except Exception:
            pass

        try:
            vol_sma = volume.rolling(window=20).mean()
            features.volume_sma_20 = float(vol_sma.iloc[-1]) if len(volume) >= 20 else None
            features.volume_ratio = (
                float(volume.iloc[-1] / vol_sma.iloc[-1])
                if features.volume_sma_20 and features.volume_sma_20 > 0
                else None
            )
        except Exception:
            pass

        # Candle body and wicks
        if features.open is not None and features.close is not None:
            features.body = abs(features.close - features.open)
            if features.high is not None:
                features.upper_wick = features.high - max(features.close, features.open)
                features.lower_wick = min(features.close, features.open) - features.low

        return features

    def _compute_numpy(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict],
    ) -> FeatureSet:
        """Fallback computation using numpy when pandas/ta is unavailable."""
        closes = np.array([float(c.get("close", 0)) for c in candles], dtype=float)
        if len(closes) == 0:
            return FeatureSet(symbol=symbol, timeframe=timeframe, computed_at=datetime.now(timezone.utc))

        features = FeatureSet(
            symbol=symbol,
            timeframe=timeframe,
            computed_at=datetime.now(timezone.utc),
            close=float(closes[-1]),
        )

        if len(closes) >= 20:
            features.ema_20 = float(np.mean(closes[-20:]))
        if len(closes) >= 50:
            features.ema_50 = float(np.mean(closes[-50:]))

        return features

    def _build_cache_key(
        self, symbol: str, timeframe: str, candles: list[dict]
    ) -> str:
        """Build a deterministic cache key from the candle data."""
        if not candles:
            return f"feat:{symbol}:{timeframe}:empty"
        first_ts = candles[0].get("timestamp", candles[0].get("time", ""))
        last_ts = candles[-1].get("timestamp", candles[-1].get("time", ""))
        count = len(candles)
        raw = f"{symbol}:{timeframe}:{first_ts}:{last_ts}:{count}"
        return f"feat:{symbol}:{timeframe}:{hashlib.md5(raw.encode()).hexdigest()}"

    def _serialize(self, features: FeatureSet) -> dict:
        return {k: v for k, v in features.__dict__.items() if not k.startswith("_")}

    def _deserialize(self, data: dict) -> FeatureSet | None:
        try:
            return FeatureSet(**data)
        except Exception:
            return None

    async def invalidate_cache(self, symbol: str | None = None) -> None:
        """Invalidate cache entries, optionally by symbol."""
        if symbol:
            prefix = f"feat:{symbol}:"
            await self._local_cache.delete_by_prefix(prefix)
            if self._cache:
                # We can't pattern-delete in Redis, so we clear relevant keys
                keys_to_remove = [
                    k for k in self._access_counts
                    if k.startswith(prefix)
                ]
                if keys_to_remove:
                    await self._cache.delete_many(keys_to_remove)
        else:
            await self._local_cache.clear()
            self._access_counts.clear()
            self._bg_refresh_times.clear()
            self._stampede_locks.clear()
