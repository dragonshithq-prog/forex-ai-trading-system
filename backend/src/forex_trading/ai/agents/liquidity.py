"""Liquidity Agent - detects order blocks, fair value gaps and liquidity pools."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import structlog

from forex_trading.ai.agents.base import (
    AgentSignal,
    BaseAgent,
    MarketContext,
    MarketRegime,
    SignalDirection,
)

logger = structlog.get_logger()

_MIN_CANDLES = 30
_PROXIMITY_FACTOR = 0.002  # price within 0.20% of zone is "near"
_SWING_LOOKBACK = 5


@dataclass(frozen=True)
class OrderBlock:
    """An order block zone."""

    kind: str  # 'bullish' | 'bearish'
    high: float
    low: float
    candle_index: int


@dataclass(frozen=True)
class FairValueGap:
    """A fair value gap zone."""

    kind: str  # 'bullish' | 'bearish'
    upper: float
    lower: float
    candle_index: int


def _build_dataframe(candles: list[dict]) -> pd.DataFrame:
    """Convert candle dicts to typed DataFrame."""
    df = pd.DataFrame(candles)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _find_order_blocks(df: pd.DataFrame) -> list[OrderBlock]:
    """
    Detect order blocks.

    Bullish OB: last bearish candle before a strong bullish impulse (next candle closes
    more than its range above the OB candle high).
    Bearish OB: last bullish candle before a strong bearish impulse.
    """
    blocks: list[OrderBlock] = []
    n = len(df)

    for i in range(1, n - 1):
        prev_open = float(df["open"].iloc[i])
        prev_close = float(df["close"].iloc[i])
        next_open = float(df["open"].iloc[i + 1])
        next_close = float(df["close"].iloc[i + 1])
        prev_range = abs(prev_high := float(df["high"].iloc[i])) - abs(
            prev_low := float(df["low"].iloc[i])
        )
        prev_high = float(df["high"].iloc[i])
        prev_low = float(df["low"].iloc[i])
        prev_range = prev_high - prev_low

        # Bullish OB: current candle is bearish, next is strongly bullish
        if prev_close < prev_open and next_close > next_open:
            impulse = next_close - next_open
            if prev_range > 0 and impulse > prev_range:
                blocks.append(OrderBlock(kind="bullish", high=prev_high, low=prev_low, candle_index=i))

        # Bearish OB: current candle is bullish, next is strongly bearish
        elif prev_close > prev_open and next_close < next_open:
            impulse = next_open - next_close
            if prev_range > 0 and impulse > prev_range:
                blocks.append(OrderBlock(kind="bearish", high=prev_high, low=prev_low, candle_index=i))

    return blocks


def _find_fvgs(df: pd.DataFrame) -> list[FairValueGap]:
    """
    Detect Fair Value Gaps (FVG).

    Bullish FVG: candle[i-2].high < candle[i].low (gap between them).
    Bearish FVG: candle[i-2].low > candle[i].high.
    """
    fvgs: list[FairValueGap] = []
    n = len(df)

    for i in range(2, n):
        h_minus2 = float(df["high"].iloc[i - 2])
        l_minus2 = float(df["low"].iloc[i - 2])
        l_i = float(df["low"].iloc[i])
        h_i = float(df["high"].iloc[i])

        if h_minus2 < l_i:
            fvgs.append(FairValueGap(kind="bullish", upper=l_i, lower=h_minus2, candle_index=i))
        elif l_minus2 > h_i:
            fvgs.append(FairValueGap(kind="bearish", upper=l_minus2, lower=h_i, candle_index=i))

    return fvgs


def _find_liquidity_pools(df: pd.DataFrame, lookback: int = _SWING_LOOKBACK) -> dict[str, list[float]]:
    """
    Find liquidity pools: clusters of swing highs (buy-side) and swing lows (sell-side).
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    buy_side: list[float] = []
    sell_side: list[float] = []

    for i in range(lookback, n - lookback):
        h_window = highs[i - lookback : i + lookback + 1]
        l_window = lows[i - lookback : i + lookback + 1]
        if highs[i] == h_window.max():
            buy_side.append(float(highs[i]))
        if lows[i] == l_window.min():
            sell_side.append(float(lows[i]))

    return {"buy_side": buy_side, "sell_side": sell_side}


def _price_near_zone(price: float, zone_high: float, zone_low: float, factor: float = _PROXIMITY_FACTOR) -> bool:
    """Return True if price is within the zone or within factor% distance of it."""
    mid = (zone_high + zone_low) / 2.0
    threshold = mid * factor
    return zone_low - threshold <= price <= zone_high + threshold


class LiquidityAgent(BaseAgent):
    """
    Detects order blocks, fair value gaps, and liquidity pools.

    Returns LONG when price is near a bullish OB or bullish FVG (demand zone).
    Returns SHORT when price is near a bearish OB or bearish FVG (supply zone).
    Confidence based on number of confluent zones price is near.
    """

    def __init__(self) -> None:
        super().__init__(agent_id="liquidity", name="Liquidity Agent")

    def required_data(self) -> list[str]:
        """Return required data keys."""
        return ["candles"]

    def get_weight(self, regime: MarketRegime) -> float:
        """Return agent weight; highest in ranging regime."""
        weights: dict[MarketRegime, float] = {
            MarketRegime.RANGING: 0.85,
            MarketRegime.TRENDING_UP: 0.65,
            MarketRegime.TRENDING_DOWN: 0.65,
            MarketRegime.VOLATILE: 0.50,
            MarketRegime.LOW_VOLATILITY: 0.70,
        }
        return weights.get(regime, 0.60)

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Analyze liquidity zones and return signal."""
        log = logger.bind(agent=self.agent_id, symbol=context.symbol)

        if len(context.candles) < _MIN_CANDLES:
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                reasoning=f"Insufficient candles: {len(context.candles)} < {_MIN_CANDLES}",
            )

        df = _build_dataframe(context.candles)
        if len(df) < _MIN_CANDLES:
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                reasoning="Candle data invalid after parsing",
            )

        price = float(df["close"].iloc[-1])
        order_blocks = _find_order_blocks(df)
        fvgs = _find_fvgs(df)
        liquidity_pools = _find_liquidity_pools(df)

        # Score proximity to each zone type
        bullish_hits: list[str] = []
        bearish_hits: list[str] = []

        for ob in order_blocks[-10:]:  # check last 10 OBs
            if _price_near_zone(price, ob.high, ob.low):
                if ob.kind == "bullish":
                    bullish_hits.append(f"Bullish OB at {ob.low:.5f}-{ob.high:.5f}")
                else:
                    bearish_hits.append(f"Bearish OB at {ob.low:.5f}-{ob.high:.5f}")

        for fvg in fvgs[-10:]:
            if _price_near_zone(price, fvg.upper, fvg.lower):
                if fvg.kind == "bullish":
                    bullish_hits.append(f"Bullish FVG at {fvg.lower:.5f}-{fvg.upper:.5f}")
                else:
                    bearish_hits.append(f"Bearish FVG at {fvg.lower:.5f}-{fvg.upper:.5f}")

        # Proximity to sell-side liquidity pools → potential LONG (price swept lows)
        for pool_price in liquidity_pools["sell_side"][-5:]:
            if abs(price - pool_price) / price < _PROXIMITY_FACTOR:
                bullish_hits.append(f"Near sell-side liquidity pool at {pool_price:.5f}")

        # Proximity to buy-side liquidity pools → potential SHORT
        for pool_price in liquidity_pools["buy_side"][-5:]:
            if abs(price - pool_price) / price < _PROXIMITY_FACTOR:
                bearish_hits.append(f"Near buy-side liquidity pool at {pool_price:.5f}")

        bull_count = len(bullish_hits)
        bear_count = len(bearish_hits)
        max_count = max(bull_count + bear_count, 1)

        if bull_count > bear_count and bull_count >= 1:
            confidence = min(bull_count / max_count * 0.85, 1.0)
            direction = SignalDirection.LONG
            reasoning = f"Price near {bull_count} bullish zone(s): {'; '.join(bullish_hits[:3])}."
        elif bear_count > bull_count and bear_count >= 1:
            confidence = min(bear_count / max_count * 0.85, 1.0)
            direction = SignalDirection.SHORT
            reasoning = f"Price near {bear_count} bearish zone(s): {'; '.join(bearish_hits[:3])}."
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0
            reasoning = f"No significant liquidity zone confluence. Price={price:.5f}."

        log.info(
            "liquidity_signal",
            direction=direction.value,
            confidence=confidence,
            bull_hits=bull_count,
            bear_hits=bear_count,
        )

        return AgentSignal(
            agent_id=self.agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            supporting_data={
                "current_price": price,
                "bullish_zones": bullish_hits[:5],
                "bearish_zones": bearish_hits[:5],
                "order_blocks_found": len(order_blocks),
                "fvgs_found": len(fvgs),
                "liquidity_pools": {
                    "buy_side_count": len(liquidity_pools["buy_side"]),
                    "sell_side_count": len(liquidity_pools["sell_side"]),
                },
            },
        )
