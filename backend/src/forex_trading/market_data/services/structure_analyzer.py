"""Market Structure Analyzer - SMC, liquidity zones, order blocks.

Provides both the legacy ``StructureAnalyzer`` (preserved for backwards
compatibility) and the new ``MarketStructureAnalyzer`` with its typed
``MarketStructure`` dataclass as specified in the design document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Legacy types (kept for backwards compatibility with existing tests)
# ---------------------------------------------------------------------------

class StructureType(str, Enum):
    """Market structure classification."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    CONSOLIDATING = "consolidating"


class BreakType(str, Enum):
    """Structure break types."""
    BOS = "break_of_structure"
    CHOCH = "change_of_character"
    NONE = "none"


@dataclass
class OrderBlock:
    """Represents an order block (institutional footprint)."""
    type: str
    high: float
    low: float
    timestamp: datetime
    mitigated: bool = False


@dataclass
class FairValueGap:
    """Represents a Fair Value Gap (imbalance)."""
    type: str
    high: float
    low: float
    timestamp: datetime
    filled: bool = False


@dataclass
class LiquidityZone:
    """Represents a liquidity zone (stop loss clusters)."""
    type: str
    price_level: float
    strength: float
    timestamp: datetime


@dataclass
class MarketStructure:
    """Complete market structure analysis result (legacy + new combined)."""
    symbol: str
    timeframe: str
    # Legacy fields
    structure_type: StructureType = StructureType.RANGING
    break_type: BreakType = BreakType.NONE
    order_blocks: list[OrderBlock] = field(default_factory=list)
    fair_value_gaps: list[FairValueGap] = field(default_factory=list)
    liquidity_zones: list[LiquidityZone] = field(default_factory=list)
    trend_direction: str = "neutral"
    strength: float = 0.0
    last_break_price: float = 0.0
    analysis_time: datetime = field(default_factory=datetime.utcnow)
    # New design-doc fields
    swing_highs: list[StructureLevel] = field(default_factory=list)
    swing_lows: list[StructureLevel] = field(default_factory=list)
    support_levels: list[StructureLevel] = field(default_factory=list)
    resistance_levels: list[StructureLevel] = field(default_factory=list)
    last_bos: dict | None = None
    last_choch: dict | None = None
    analyzed_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# New design-doc type
# ---------------------------------------------------------------------------

@dataclass
class StructureLevel:
    """A detected price structure level."""
    price: float
    level_type: str  # "support" | "resistance" | "swing_high" | "swing_low"
    strength: float  # 0-1
    timeframe: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candle_ts(candle: dict, fallback: datetime | None = None) -> datetime:
    ts = candle.get("timestamp")
    if isinstance(ts, datetime):
        return ts
    if ts is not None:
        try:
            return datetime.fromisoformat(str(ts))
        except ValueError:
            pass
    return fallback or datetime.utcnow()


# ---------------------------------------------------------------------------
# MarketStructureAnalyzer  (new)
# ---------------------------------------------------------------------------

class MarketStructureAnalyzer:
    """
    Analyse market structure using Smart Money Concepts (SMC).

    Detects swing highs/lows, support/resistance, Break of Structure (BOS),
    Change of Character (CHoCH), order blocks, and Fair Value Gaps.
    """

    def analyze(
        self, candles: list[dict], timeframe: str, symbol: str
    ) -> MarketStructure:
        result = MarketStructure(symbol=symbol, timeframe=timeframe)
        result.trend_direction = "ranging"

        if len(candles) < 10:
            return result

        swing_highs = self._find_swing_highs(candles)
        swing_lows = self._find_swing_lows(candles)

        result.swing_highs = swing_highs
        result.swing_lows = swing_lows
        result.trend_direction = self._determine_trend(swing_highs, swing_lows)

        # Map StructureLevel → legacy StructureType
        if result.trend_direction == "bullish":
            result.structure_type = StructureType.TRENDING_UP
        elif result.trend_direction == "bearish":
            result.structure_type = StructureType.TRENDING_DOWN
        else:
            result.structure_type = StructureType.RANGING

        result.support_levels = [
            StructureLevel(
                price=sl.price,
                level_type="support",
                strength=sl.strength,
                timeframe=timeframe,
                timestamp=sl.timestamp,
            )
            for sl in swing_lows
        ]
        result.resistance_levels = [
            StructureLevel(
                price=sh.price,
                level_type="resistance",
                strength=sh.strength,
                timeframe=timeframe,
                timestamp=sh.timestamp,
            )
            for sh in swing_highs
        ]

        result.last_bos = self._detect_bos(candles, swing_highs, swing_lows)
        result.last_choch = self._detect_choch(candles, swing_highs, swing_lows)

        if result.last_bos:
            result.break_type = BreakType.BOS
        elif result.last_choch:
            result.break_type = BreakType.CHOCH

        obs = self._find_order_blocks(candles)
        result.order_blocks = [
            OrderBlock(
                type=ob["type"],
                high=ob["high"],
                low=ob["low"],
                timestamp=ob["timestamp"],
                mitigated=ob.get("mitigated", False),
            )
            for ob in obs
        ]

        fvgs = self._find_fair_value_gaps(candles)
        result.fair_value_gaps = [
            FairValueGap(
                type=fvg["type"],
                high=fvg["high"],
                low=fvg["low"],
                timestamp=fvg["timestamp"],
                filled=fvg.get("filled", False),
            )
            for fvg in fvgs
        ]

        lz = self._find_liquidity_zones(candles, swing_highs, swing_lows)
        result.liquidity_zones = lz

        result.analyzed_at = datetime.utcnow()
        result.analysis_time = result.analyzed_at
        return result

    # ------------------------------------------------------------------
    # Swing detection
    # ------------------------------------------------------------------

    def _find_swing_highs(
        self, candles: list[dict], lookback: int = 5
    ) -> list[StructureLevel]:
        highs: list[StructureLevel] = []
        n = len(candles)
        for i in range(lookback, n - lookback):
            pivot = candles[i]["high"]
            left_ok = all(candles[i - j]["high"] < pivot for j in range(1, lookback + 1))
            right_ok = all(candles[i + j]["high"] < pivot for j in range(1, lookback + 1))
            if left_ok and right_ok:
                # Strength = count of candles in window that closed below the pivot
                window = candles[max(0, i - lookback * 2): i + lookback * 2 + 1]
                touches = sum(1 for c in window if c["high"] >= pivot * 0.9999)
                strength = min(touches / max(len(window), 1), 1.0)
                highs.append(
                    StructureLevel(
                        price=pivot,
                        level_type="swing_high",
                        strength=strength,
                        timeframe="",
                        timestamp=_candle_ts(candles[i]),
                    )
                )
        return highs

    def _find_swing_lows(
        self, candles: list[dict], lookback: int = 5
    ) -> list[StructureLevel]:
        lows: list[StructureLevel] = []
        n = len(candles)
        for i in range(lookback, n - lookback):
            pivot = candles[i]["low"]
            left_ok = all(candles[i - j]["low"] > pivot for j in range(1, lookback + 1))
            right_ok = all(candles[i + j]["low"] > pivot for j in range(1, lookback + 1))
            if left_ok and right_ok:
                window = candles[max(0, i - lookback * 2): i + lookback * 2 + 1]
                touches = sum(1 for c in window if c["low"] <= pivot * 1.0001)
                strength = min(touches / max(len(window), 1), 1.0)
                lows.append(
                    StructureLevel(
                        price=pivot,
                        level_type="swing_low",
                        strength=strength,
                        timeframe="",
                        timestamp=_candle_ts(candles[i]),
                    )
                )
        return lows

    # ------------------------------------------------------------------
    # Trend direction
    # ------------------------------------------------------------------

    def _determine_trend(
        self,
        swing_highs: list[StructureLevel],
        swing_lows: list[StructureLevel],
    ) -> str:
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "ranging"

        hh = sum(
            1 for i in range(1, len(swing_highs))
            if swing_highs[i].price > swing_highs[i - 1].price
        )
        hl = sum(
            1 for i in range(1, len(swing_lows))
            if swing_lows[i].price > swing_lows[i - 1].price
        )
        lh = sum(
            1 for i in range(1, len(swing_highs))
            if swing_highs[i].price < swing_highs[i - 1].price
        )
        ll = sum(
            1 for i in range(1, len(swing_lows))
            if swing_lows[i].price < swing_lows[i - 1].price
        )

        total = (len(swing_highs) - 1) + (len(swing_lows) - 1) or 1
        bullish_score = (hh + hl) / total
        bearish_score = (lh + ll) / total

        if bullish_score > 0.55:
            return "bullish"
        if bearish_score > 0.55:
            return "bearish"
        return "ranging"

    # ------------------------------------------------------------------
    # Break of Structure
    # ------------------------------------------------------------------

    def _detect_bos(
        self,
        candles: list[dict],
        swing_highs: list[StructureLevel],
        swing_lows: list[StructureLevel],
    ) -> dict | None:
        if len(candles) < 2 or not swing_highs or not swing_lows:
            return None

        last_close = candles[-1]["close"]
        prev_close = candles[-2]["close"]

        last_high = swing_highs[-1].price
        last_low = swing_lows[-1].price

        # Bullish BOS: close breaks above last swing high
        if prev_close <= last_high < last_close:
            return {
                "direction": "bullish",
                "type": "BOS",
                "broken_level": last_high,
                "candle_index": len(candles) - 1,
                "timestamp": _candle_ts(candles[-1]),
            }

        # Bearish BOS: close breaks below last swing low
        if prev_close >= last_low > last_close:
            return {
                "direction": "bearish",
                "type": "BOS",
                "broken_level": last_low,
                "candle_index": len(candles) - 1,
                "timestamp": _candle_ts(candles[-1]),
            }

        return None

    # ------------------------------------------------------------------
    # Change of Character
    # ------------------------------------------------------------------

    def _detect_choch(
        self,
        candles: list[dict],
        swing_highs: list[StructureLevel],
        swing_lows: list[StructureLevel],
        trend: str | None = None,
    ) -> dict | None:
        """
        CHoCH occurs when price breaks the *opposing* structure level:
        - In a bullish trend, price breaks below the last swing low → bearish CHoCH.
        - In a bearish trend, price breaks above the last swing high → bullish CHoCH.
        """
        if len(candles) < 2 or not swing_highs or not swing_lows:
            return None

        current_trend = trend or self._determine_trend(swing_highs, swing_lows)
        last_close = candles[-1]["close"]
        prev_close = candles[-2]["close"]

        if current_trend == "bullish":
            last_low = swing_lows[-1].price
            if prev_close >= last_low > last_close:
                return {
                    "direction": "bearish",
                    "type": "CHoCH",
                    "broken_level": last_low,
                    "candle_index": len(candles) - 1,
                    "timestamp": _candle_ts(candles[-1]),
                }

        elif current_trend == "bearish":
            last_high = swing_highs[-1].price
            if prev_close <= last_high < last_close:
                return {
                    "direction": "bullish",
                    "type": "CHoCH",
                    "broken_level": last_high,
                    "candle_index": len(candles) - 1,
                    "timestamp": _candle_ts(candles[-1]),
                }

        return None

    # ------------------------------------------------------------------
    # Order Blocks
    # ------------------------------------------------------------------

    def _find_order_blocks(self, candles: list[dict]) -> list[dict]:
        obs: list[dict] = []
        for i in range(2, len(candles)):
            prev = candles[i - 1]
            curr = candles[i]

            # Bullish OB: bearish candle → strong bullish displacement above prev open
            if (
                prev["close"] < prev["open"]  # bearish candle
                and curr["close"] > curr["open"]  # bullish candle
                and curr["close"] > prev["open"]  # displacement
            ):
                obs.append({
                    "type": "bullish_ob",
                    "high": prev["open"],
                    "low": prev["low"],
                    "timestamp": _candle_ts(prev),
                    "mitigated": _is_ob_mitigated(candles[i:], prev["low"], prev["open"], "bullish"),
                })

            # Bearish OB: bullish candle → strong bearish displacement below prev open
            if (
                prev["close"] > prev["open"]  # bullish candle
                and curr["close"] < curr["open"]  # bearish candle
                and curr["close"] < prev["open"]  # displacement
            ):
                obs.append({
                    "type": "bearish_ob",
                    "high": prev["high"],
                    "low": prev["close"],
                    "timestamp": _candle_ts(prev),
                    "mitigated": _is_ob_mitigated(candles[i:], prev["close"], prev["high"], "bearish"),
                })

        return obs[-5:]

    # ------------------------------------------------------------------
    # Fair Value Gaps
    # ------------------------------------------------------------------

    def _find_fair_value_gaps(self, candles: list[dict]) -> list[dict]:
        fvgs: list[dict] = []
        for i in range(2, len(candles)):
            c0, c1, c2 = candles[i - 2], candles[i - 1], candles[i]

            # Bullish FVG: gap between c0.high and c2.low
            if c2["low"] > c0["high"]:
                fvgs.append({
                    "type": "bullish_fvg",
                    "high": c2["low"],
                    "low": c0["high"],
                    "timestamp": _candle_ts(c1),
                    "filled": False,
                })

            # Bearish FVG: gap between c2.high and c0.low
            if c2["high"] < c0["low"]:
                fvgs.append({
                    "type": "bearish_fvg",
                    "high": c0["low"],
                    "low": c2["high"],
                    "timestamp": _candle_ts(c1),
                    "filled": False,
                })

        # Mark filled gaps
        for fvg in fvgs:
            fvg["filled"] = _is_fvg_filled(candles, fvg)

        return fvgs[-5:]

    # ------------------------------------------------------------------
    # Liquidity zones (legacy helper kept for StructureAnalyzer)
    # ------------------------------------------------------------------

    def _find_liquidity_zones(
        self,
        candles: list[dict],
        swing_highs: list[StructureLevel],
        swing_lows: list[StructureLevel],
    ) -> list[LiquidityZone]:
        zones: list[LiquidityZone] = []
        for sh in swing_highs[-3:]:
            zones.append(LiquidityZone(
                type="sell_liquidity",
                price_level=sh.price,
                strength=sh.strength,
                timestamp=sh.timestamp,
            ))
        for sl in swing_lows[-3:]:
            zones.append(LiquidityZone(
                type="buy_liquidity",
                price_level=sl.price,
                strength=sl.strength,
                timestamp=sl.timestamp,
            ))
        return zones


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _is_ob_mitigated(
    future_candles: list[dict],
    ob_low: float,
    ob_high: float,
    ob_direction: str,
) -> bool:
    for c in future_candles:
        if ob_direction == "bullish" and c["low"] <= ob_high:
            return True
        if ob_direction == "bearish" and c["high"] >= ob_low:
            return True
    return False


def _is_fvg_filled(candles: list[dict], fvg: dict) -> bool:
    fvg_ts = fvg["timestamp"]
    fvg_low = fvg["low"]
    fvg_high = fvg["high"]
    for c in candles:
        ts = c.get("timestamp")
        if ts is not None and isinstance(ts, datetime) and ts <= fvg_ts:
            continue
        if c["low"] <= fvg_low and c["high"] >= fvg_high:
            return True
    return False


# ---------------------------------------------------------------------------
# Legacy StructureAnalyzer (preserved for existing tests that import it)
# ---------------------------------------------------------------------------

class StructureAnalyzer:
    """
    Legacy analyzer - kept for backwards compatibility.

    New code should use ``MarketStructureAnalyzer``.
    """

    def __init__(self) -> None:
        self._analysis_cache: dict[str, MarketStructure] = {}
        self._new_analyzer = MarketStructureAnalyzer()

    async def analyze(
        self, symbol: str, candles: list[dict], timeframe: str
    ) -> MarketStructure:
        result = self._new_analyzer.analyze(candles, timeframe, symbol)
        self._analysis_cache[f"{symbol}_{timeframe}"] = result
        return result

    def _find_swings(
        self, candles: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        swing_highs = []
        swing_lows = []
        for i in range(2, len(candles) - 2):
            if (
                candles[i]["high"] > candles[i - 1]["high"]
                and candles[i]["high"] > candles[i - 2]["high"]
                and candles[i]["high"] > candles[i + 1]["high"]
                and candles[i]["high"] > candles[i + 2]["high"]
            ):
                swing_highs.append({
                    "price": candles[i]["high"],
                    "index": i,
                    "timestamp": candles[i].get("timestamp"),
                })
            if (
                candles[i]["low"] < candles[i - 1]["low"]
                and candles[i]["low"] < candles[i - 2]["low"]
                and candles[i]["low"] < candles[i + 1]["low"]
                and candles[i]["low"] < candles[i + 2]["low"]
            ):
                swing_lows.append({
                    "price": candles[i]["low"],
                    "index": i,
                    "timestamp": candles[i].get("timestamp"),
                })
        return swing_highs, swing_lows

    def _classify_structure(
        self,
        swing_highs: list[dict],
        swing_lows: list[dict],
        candles: list[dict],
    ) -> StructureType:
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return StructureType.RANGING
        hh = sum(
            1 for i in range(1, len(swing_highs))
            if swing_highs[i]["price"] > swing_highs[i - 1]["price"]
        )
        hl = sum(
            1 for i in range(1, len(swing_lows))
            if swing_lows[i]["price"] > swing_lows[i - 1]["price"]
        )
        lh = sum(
            1 for i in range(1, len(swing_highs))
            if swing_highs[i]["price"] < swing_highs[i - 1]["price"]
        )
        ll = sum(
            1 for i in range(1, len(swing_lows))
            if swing_lows[i]["price"] < swing_lows[i - 1]["price"]
        )
        total = len(swing_highs) + len(swing_lows) - 2
        if hh + hl > total * 0.6:
            return StructureType.TRENDING_UP
        if lh + ll > total * 0.6:
            return StructureType.TRENDING_DOWN
        return StructureType.RANGING

    def _detect_break(
        self,
        candles: list[dict],
        swing_highs: list[dict],
        swing_lows: list[dict],
    ) -> BreakType:
        if len(candles) < 2 or len(swing_highs) < 2 or len(swing_lows) < 2:
            return BreakType.NONE
        current_close = candles[-1]["close"]
        prev_close = candles[-2]["close"]
        last_high = swing_highs[-1]["price"]
        last_low = swing_lows[-1]["price"]
        if current_close > last_high and prev_close <= last_high:
            return BreakType.BOS
        if current_close < last_low and prev_close >= last_low:
            return BreakType.BOS
        return BreakType.NONE

    def _find_order_blocks(self, candles: list[dict]) -> list[OrderBlock]:
        obs: list[OrderBlock] = []
        for i in range(2, len(candles)):
            prev, curr = candles[i - 1], candles[i]
            if (
                prev["close"] < prev["open"]
                and curr["close"] > curr["open"]
                and curr["close"] > prev["open"]
            ):
                obs.append(OrderBlock(
                    type="bullish_ob",
                    high=prev["open"],
                    low=prev["low"],
                    timestamp=_candle_ts(prev),
                ))
            if (
                prev["close"] > prev["open"]
                and curr["close"] < curr["open"]
                and curr["close"] < prev["open"]
            ):
                obs.append(OrderBlock(
                    type="bearish_ob",
                    high=prev["high"],
                    low=prev["close"],
                    timestamp=_candle_ts(prev),
                ))
        return obs[-5:]

    def _find_fair_value_gaps(self, candles: list[dict]) -> list[FairValueGap]:
        fvgs: list[FairValueGap] = []
        for i in range(2, len(candles)):
            if candles[i]["low"] > candles[i - 2]["high"]:
                fvgs.append(FairValueGap(
                    type="bullish_fvg",
                    high=candles[i]["low"],
                    low=candles[i - 2]["high"],
                    timestamp=_candle_ts(candles[i - 1]),
                ))
            if candles[i]["high"] < candles[i - 2]["low"]:
                fvgs.append(FairValueGap(
                    type="bearish_fvg",
                    high=candles[i - 2]["low"],
                    low=candles[i]["high"],
                    timestamp=_candle_ts(candles[i - 1]),
                ))
        return fvgs[-5:]

    def _find_liquidity_zones(
        self,
        candles: list[dict],
        swing_highs: list[dict],
        swing_lows: list[dict],
    ) -> list[LiquidityZone]:
        zones: list[LiquidityZone] = []
        for high in swing_highs[-3:]:
            zones.append(LiquidityZone(
                type="sell_liquidity",
                price_level=high["price"],
                strength=0.8,
                timestamp=high.get("timestamp") or datetime.utcnow(),
            ))
        for low in swing_lows[-3:]:
            zones.append(LiquidityZone(
                type="buy_liquidity",
                price_level=low["price"],
                strength=0.8,
                timestamp=low.get("timestamp") or datetime.utcnow(),
            ))
        return zones
