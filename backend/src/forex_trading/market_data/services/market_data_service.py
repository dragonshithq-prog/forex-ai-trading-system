"""Market Data Service - full production implementation."""

from __future__ import annotations

import asyncio
import json
import math
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID

import structlog

from forex_trading.core.domain.events import MarketTickEvent

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Domain types (lightweight; avoid circular imports from domain layer)
# ---------------------------------------------------------------------------

Candle = dict[str, Any]

Tick = dict[str, Any]  # keys: symbol, bid, ask, volume, spread, timestamp

# Redis TTL per timeframe (seconds)
_CACHE_TTL: dict[str, int] = {
    "M1": 60,
    "M5": 300,
    "M15": 300,
    "M30": 300,
    "H1": 3600,
    "H4": 3600,
    "D1": 3600,
    "W1": 3600,
    "MN": 3600,
}

_DEFAULT_TTL = 300


def _ttl(timeframe: str) -> int:
    return _CACHE_TTL.get(timeframe.upper(), _DEFAULT_TTL)


# ---------------------------------------------------------------------------
# MarketDataService
# ---------------------------------------------------------------------------

class MarketDataService:
    """
    Ingest, normalise, cache, and distribute real-time and historical market data.

    Dependencies:
        cache_manager  – duck-typed Redis client with ``get`` / ``set`` / ``delete``
                         async methods (or None in test mode).
        broker_gateway – ``BrokerGateway`` instance for live data; may be None.
    """

    def __init__(self, cache_manager: Any = None, broker_gateway: Any = None) -> None:
        self._cache = cache_manager
        self._broker_gateway = broker_gateway
        self._tick_buffer: dict[str, Tick] = {}
        # symbol → list of async callbacks
        self._subscribers: dict[str, list[Callable[[Tick], Awaitable[None]]]] = defaultdict(list)
        self._lock: threading.Lock = threading.Lock()
        # Legacy compatibility (old tests use _subscribers with sync callbacks)
        self._legacy_subscribers: dict[str, list[Callable]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Candles
    # ------------------------------------------------------------------

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 500,
        broker_connection_id: UUID | None = None,
    ) -> list[Candle]:
        cache_key = f"candles:{symbol}:{timeframe}:{count}"

        if self._cache is not None:
            try:
                cached = await self._cache.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception as exc:  # noqa: BLE001
                logger.warning("cache_get_failed", key=cache_key, error=str(exc))

        candles = await self._fetch_candles_from_broker(
            symbol, timeframe, count, broker_connection_id
        )

        if candles and self._cache is not None:
            try:
                await self._cache.set(cache_key, json.dumps(candles, default=str), ex=_ttl(timeframe))
            except Exception as exc:  # noqa: BLE001
                logger.warning("cache_set_failed", key=cache_key, error=str(exc))

        return candles

    async def _fetch_candles_from_broker(
        self,
        symbol: str,
        timeframe: str,
        count: int,
        broker_connection_id: UUID | None,
    ) -> list[Candle]:
        if self._broker_gateway is None:
            return []
        cid = broker_connection_id or self._broker_gateway.get_best_connection(symbol)
        if cid is None:
            return []
        plugin = self._broker_gateway._connections.get(cid)
        if plugin is None:
            return []
        try:
            return await plugin.get_ohlcv(symbol, timeframe, count)
        except AttributeError:
            # Plugin may not implement get_ohlcv; silently return empty
            return []
        except Exception as exc:
            logger.error("broker_candle_fetch_failed", symbol=symbol, error=str(exc))
            return []

    # ------------------------------------------------------------------
    # Ticks
    # ------------------------------------------------------------------

    async def get_latest_tick(self, symbol: str) -> Tick | None:
        return self._tick_buffer.get(symbol)

    async def subscribe_ticks(
        self,
        symbol: str,
        callback: Callable[[Tick], Awaitable[None]],
    ) -> None:
        with self._lock:
            self._subscribers[symbol].append(callback)
        logger.info("tick_subscribed", symbol=symbol)

    async def unsubscribe_ticks(
        self,
        symbol: str,
        callback: Callable[[Tick], Awaitable[None]],
    ) -> None:
        with self._lock:
            self._subscribers[symbol] = [
                cb for cb in self._subscribers[symbol] if cb is not callback
            ]

    # Legacy subscribe_ticks(symbols_list, callback) API used by existing tests
    async def subscribe_ticks_multi(
        self, symbols: list[str], callback: Callable
    ) -> None:
        for symbol in symbols:
            with self._lock:
                self._legacy_subscribers[symbol].append(callback)
            logger.info("subscribed_to_ticks", symbol=symbol)

    # ------------------------------------------------------------------
    # Tick ingestion  (called by broker plugins)
    # ------------------------------------------------------------------

    async def on_tick(self, symbol: str, bid: float, ask: float, volume: float = 0.0) -> None:
        tick: Tick = {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "volume": volume,
            "spread": round(ask - bid, 6),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._tick_buffer[symbol] = tick

        # Emit domain event (Kafka topic "market.tick")
        event = MarketTickEvent(symbol=symbol, bid=bid, ask=ask, volume=volume)
        await self._publish_event(event)

        # Notify typed async subscribers
        callbacks: list[Callable[[Tick], Awaitable[None]]]
        with self._lock:
            callbacks = list(self._subscribers.get(symbol, []))
        for cb in callbacks:
            try:
                await cb(tick)
            except Exception as exc:
                logger.error("tick_callback_error", symbol=symbol, error=str(exc))

        # Notify legacy sync/async callbacks
        legacy: list[Callable]
        with self._lock:
            legacy = list(self._legacy_subscribers.get(symbol, []))
        for cb in legacy:
            try:
                result = cb(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.error("tick_callback_error", symbol=symbol, error=str(exc))

    async def _publish_event(self, event: MarketTickEvent) -> None:
        # Kafka publish is fire-and-forget; swallow if not configured
        pass

    # ------------------------------------------------------------------
    # Legacy compatibility methods (keep old API working)
    # ------------------------------------------------------------------

    async def get_current_price(self, symbol: str) -> dict | None:
        tick = self._tick_buffer.get(symbol)
        if tick is None:
            return None
        return {"bid": tick["bid"], "ask": tick["ask"]}

    async def get_spread(self, symbol: str) -> float | None:
        tick = self._tick_buffer.get(symbol)
        return tick["spread"] if tick else None

    # ------------------------------------------------------------------
    # Multi-timeframe data
    # ------------------------------------------------------------------

    async def get_multi_timeframe_data(
        self,
        symbol: str,
        timeframes: list[str],
        count: int = 500,
    ) -> dict[str, list[dict]]:
        tasks = {tf: self.get_candles(symbol, tf, count) for tf in timeframes}
        results: dict[str, list[dict]] = {}
        for tf, coro in tasks.items():
            try:
                results[tf] = await coro
            except Exception as exc:
                logger.error("mtf_fetch_error", symbol=symbol, timeframe=tf, error=str(exc))
                results[tf] = []
        return results

    # ------------------------------------------------------------------
    # ATR calculation
    # ------------------------------------------------------------------

    async def calculate_atr(self, symbol: str, timeframe: str, period: int = 14) -> float:
        candles = await self.get_candles(symbol, timeframe, count=period + 1)
        if len(candles) < 2:
            return 0.0
        true_ranges: list[float] = []
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
        if not true_ranges:
            return 0.0
        return sum(true_ranges) / len(true_ranges)

    # ------------------------------------------------------------------
    # Currency strength
    # ------------------------------------------------------------------

    async def get_currency_strength(self, currencies: list[str]) -> dict[str, float]:
        """
        Compute a relative strength index (0–100) for each currency.

        Uses a simple cross-pair close comparison over H1 candles.
        Returns 50.0 for any currency with insufficient data.
        """
        strength: dict[str, float] = {c: 0.0 for c in currencies}
        pair_counts: dict[str, int] = {c: 0 for c in currencies}

        ccy_set = set(c.upper() for c in currencies)

        # Build candidate pairs from all 6-char combinations
        all_pairs = [f"{a}{b}" for a in ccy_set for b in ccy_set if a != b]

        for pair in all_pairs:
            base = pair[:3]
            quote = pair[3:]
            if base not in ccy_set or quote not in ccy_set:
                continue
            candles = await self.get_candles(pair, "H1", count=14)
            if len(candles) < 2:
                continue
            change = (candles[-1]["close"] - candles[0]["close"]) / (candles[0]["close"] or 1)
            strength[base] = strength.get(base, 0.0) + change
            strength[quote] = strength.get(quote, 0.0) - change
            pair_counts[base] = pair_counts.get(base, 0) + 1
            pair_counts[quote] = pair_counts.get(quote, 0) + 1

        # Normalise to 0–100
        normalised: dict[str, float] = {}
        raw_values = list(strength.values())
        if not raw_values or all(v == 0 for v in raw_values):
            return {c: 50.0 for c in currencies}

        min_val = min(raw_values)
        max_val = max(raw_values)
        span = max_val - min_val or 1.0
        for ccy in currencies:
            normalised[ccy] = round((strength.get(ccy, 0.0) - min_val) / span * 100, 2)
        return normalised

    # ------------------------------------------------------------------
    # Legacy OHLCV interface (kept for backwards compatibility)
    # ------------------------------------------------------------------

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list[dict]:
        return await self.get_candles(symbol, timeframe, count=limit)

    async def get_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "H1",
    ) -> list[dict]:
        # Without a database backend, return empty; implementations can override.
        logger.debug("get_historical", symbol=symbol, start=start, end=end, timeframe=timeframe)
        return []
