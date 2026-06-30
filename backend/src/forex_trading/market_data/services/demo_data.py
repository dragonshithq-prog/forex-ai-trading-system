"""Demo/fallback market data generator for development."""

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

BASE_PRICES: dict[str, float] = {
    "EURUSD": 1.0850, "GBPUSD": 1.2650, "USDJPY": 151.50, "USDCHF": 0.8850,
    "AUDUSD": 0.6550, "NZDUSD": 0.6000, "USDCAD": 1.3600, "EURJPY": 164.50,
    "GBPJPY": 191.50, "EURGBP": 0.8570, "GBPCHF": 1.1200, "EURAUD": 1.6550,
    "GBPNZD": 2.0750, "EURCHF": 0.9600, "GBPAUD": 1.9300,
}

TIMEFRAME_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440, "W1": 10080,
}

SESSION_VOLATILITY: dict[str, float] = {
    "sydney": 0.00015, "tokyo": 0.0002, "london": 0.00035, "new_york": 0.0003,
}

_SHUFFLE = 12345


def _random_walk(price: float, volatility: float, drift: float = 0.0) -> float:
    """Generate next price via random walk with optional drift."""
    change = random.gauss(drift, volatility)
    return price * (1 + change)


def generate_demo_candles(
    symbol: str,
    timeframe: str = "H1",
    count: int = 100,
) -> list[dict[str, Any]]:
    """Generate realistic demo candlestick data."""
    base_price = BASE_PRICES.get(symbol.upper(), 1.0)
    tf_minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
    volatility = _get_volatility(symbol, timeframe)

    is_jpy = symbol.upper().endswith("JPY")
    pip = 0.01 if is_jpy else 0.0001

    now = datetime.now(timezone.utc)
    now = now.replace(second=0, microsecond=0)

    candles: list[dict[str, Any]] = []
    price = base_price
    drift = 0.0

    for i in range(count):
        t = now - timedelta(minutes=tf_minutes * (count - i))

        drift = drift * 0.9 + random.gauss(0, volatility * 0.3)
        open_price = price
        high_price = open_price + abs(random.gauss(0, volatility * 1.5))
        low_price = open_price - abs(random.gauss(0, volatility * 1.5))
        close_price = _random_walk(open_price, volatility * 0.8, drift)

        close_price = max(close_price, low_price * 0.999)
        close_price = min(close_price, high_price * 1.001)
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)

        high_price = round(high_price / pip) * pip
        low_price = round(low_price / pip) * pip
        open_price = round(open_price / pip) * pip
        close_price = round(close_price / pip) * pip

        volume = random.randint(100, 10000)

        candles.append({
            "timestamp": t.isoformat(),
            "open": open_price,
            "high": max(high_price, open_price, close_price),
            "low": min(low_price, open_price, close_price),
            "close": close_price,
            "volume": volume,
            "timeframe": timeframe,
        })

        price = close_price

    return candles


def _get_volatility(symbol: str, timeframe: str) -> float:
    """Get appropriate volatility for symbol and timeframe."""
    tf_minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
    base_vol = 0.0002
    tf_mult = math.sqrt(tf_minutes / 60)
    return base_vol * tf_mult


def generate_demo_tick(symbol: str) -> dict[str, Any]:
    """Generate a realistic demo tick."""
    base_price = BASE_PRICES.get(symbol.upper(), 1.0)
    volatility = _get_volatility(symbol, "M1")
    spread = random.uniform(0.00005, 0.0003)

    mid = _random_walk(base_price, volatility * 0.1)
    bid = mid - spread / 2
    ask = mid + spread / 2

    is_jpy = symbol.upper().endswith("JPY")
    pip = 0.01 if is_jpy else 0.0001

    bid = round(bid / pip) * pip
    ask = round(ask / pip) * pip
    if ask <= bid:
        ask = bid + pip

    return {
        "symbol": symbol.upper(),
        "bid": bid,
        "ask": ask,
        "spread": round(ask - bid, 5),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
