"""Smart Money Concepts (SMC) Agent - inducement, liquidity sweeps, OTE zones."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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

_MIN_CANDLES = 50
_SWING_LOOKBACK = 5
_FIB_OTE_LOW = 0.62  # Optimal Trade Entry zone low
_FIB_OTE_HIGH = 0.79  # Optimal Trade Entry zone high
_PROXIMITY_FACTOR = 0.0015  # 0.15% proximity


@dataclass(frozen=True)
class SmcOrderBlock:
    """Smart money order block."""

    kind: str  # 'bullish' | 'bearish'
    high: float
    low: float
    index: int


def _build_dataframe(candles: list[dict]) -> pd.DataFrame:
    """Convert candle dicts to typed DataFrame."""
    df = pd.DataFrame(candles)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _find_swings(df: pd.DataFrame, lookback: int = _SWING_LOOKBACK) -> tuple[list[int], list[int]]:
    """Return (swing_high_indices, swing_low_indices)."""
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    sh: list[int] = []
    sl: list[int] = []
    for i in range(lookback, n - lookback):
        if highs[i] == highs[i - lookback : i + lookback + 1].max():
            sh.append(i)
        if lows[i] == lows[i - lookback : i + lookback + 1].min():
            sl.append(i)
    return sh, sl


def _compute_premium_discount(df: pd.DataFrame, lookback: int = 100) -> dict[str, float]:
    """
    Compute equilibrium and premium/discount zones.

    Equilibrium = 50% of the swing range over lookback candles.
    """
    window = df.tail(lookback)
    range_high = float(window["high"].max())
    range_low = float(window["low"].min())
    equilibrium = (range_high + range_low) / 2.0
    return {
        "range_high": range_high,
        "range_low": range_low,
        "equilibrium": equilibrium,
    }


def _compute_ote_zone(
    swing_low: float,
    swing_high: float,
    direction: str,
) -> tuple[float, float]:
    """
    Compute Optimal Trade Entry (OTE) zone using Fibonacci 62-79% retracement.

    For a bullish OTE: price retraces from swing high down to 62-79% of range.
    For a bearish OTE: price retraces from swing low up to 62-79% of range.
    """
    full_range = swing_high - swing_low
    if direction == "bullish":
        ote_low = swing_high - full_range * _FIB_OTE_HIGH
        ote_high = swing_high - full_range * _FIB_OTE_LOW
    else:
        ote_low = swing_low + full_range * _FIB_OTE_LOW
        ote_high = swing_low + full_range * _FIB_OTE_HIGH
    return ote_low, ote_high


def _find_smc_order_blocks(df: pd.DataFrame) -> list[SmcOrderBlock]:
    """Identify SMC order blocks — same logic as liquidity but with stricter impulse filter."""
    blocks: list[SmcOrderBlock] = []
    n = len(df)
    for i in range(2, n - 1):
        o = float(df["open"].iloc[i])
        c = float(df["close"].iloc[i])
        hi = float(df["high"].iloc[i])
        lo = float(df["low"].iloc[i])
        next_c = float(df["close"].iloc[i + 1])
        next_o = float(df["open"].iloc[i + 1])
        candle_range = hi - lo
        if candle_range < 1e-8:
            continue
        impulse = abs(next_c - next_o)

        if c < o and next_c > next_o and impulse > candle_range * 1.5:
            blocks.append(SmcOrderBlock(kind="bullish", high=hi, low=lo, index=i))
        elif c > o and next_c < next_o and impulse > candle_range * 1.5:
            blocks.append(SmcOrderBlock(kind="bearish", high=hi, low=lo, index=i))

    return blocks


def _detect_liquidity_sweep(
    df: pd.DataFrame,
    sh_indices: list[int],
    sl_indices: list[int],
) -> tuple[str, float]:
    """
    Detect if the most recent candle swept buy-side or sell-side liquidity.

    A sweep occurs when price briefly exceeds a swing high/low but closes back.
    Returns ('buy_swept'|'sell_swept'|'none', price_level).
    """
    if not sh_indices or not sl_indices:
        return "none", 0.0

    last_candle = df.iloc[-1]
    last_high = float(last_candle["high"])
    last_low = float(last_candle["low"])
    last_close = float(last_candle["close"])

    prev_sh_price = float(df["high"].iloc[sh_indices[-1]])
    prev_sl_price = float(df["low"].iloc[sl_indices[-1]])

    # Wick above swing high but closed below = buy-side liquidity swept
    if last_high > prev_sh_price and last_close < prev_sh_price:
        return "buy_swept", prev_sh_price

    # Wick below swing low but closed above = sell-side liquidity swept
    if last_low < prev_sl_price and last_close > prev_sl_price:
        return "sell_swept", prev_sl_price

    return "none", 0.0


def _price_in_zone(price: float, zone_low: float, zone_high: float, factor: float = _PROXIMITY_FACTOR) -> bool:
    """Check if price is within or near a zone."""
    mid = (zone_low + zone_high) / 2.0
    threshold = mid * factor
    return (zone_low - threshold) <= price <= (zone_high + threshold)


class SmartMoneyAgent(BaseAgent):
    """
    Full SMC analysis: inducement, liquidity sweeps, premium/discount zones, OTE.

    LONG: price in discount zone + bullish OB + sell-side liquidity swept.
    SHORT: price in premium zone + bearish OB + buy-side liquidity swept.
    """

    def __init__(self) -> None:
        super().__init__(agent_id="smart_money", name="Smart Money Concepts Agent")

    def required_data(self) -> list[str]:
        """Return required data keys."""
        return ["candles"]

    def get_weight(self, regime: MarketRegime) -> float:
        """Return agent weight; high in trending, medium otherwise."""
        weights: dict[MarketRegime, float] = {
            MarketRegime.TRENDING_UP: 0.80,
            MarketRegime.TRENDING_DOWN: 0.80,
            MarketRegime.RANGING: 0.65,
            MarketRegime.VOLATILE: 0.55,
            MarketRegime.LOW_VOLATILITY: 0.65,
        }
        return weights.get(regime, 0.65)

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Analyze SMC concepts and return a signal."""
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

        sh_indices, sl_indices = _find_swings(df)
        pd_zones = _compute_premium_discount(df)
        order_blocks = _find_smc_order_blocks(df)
        sweep_type, sweep_price = _detect_liquidity_sweep(df, sh_indices, sl_indices)

        equilibrium = pd_zones["equilibrium"]
        range_high = pd_zones["range_high"]
        range_low = pd_zones["range_low"]

        in_discount = price < equilibrium
        in_premium = price > equilibrium

        # OTE zone calculation using last meaningful swing
        ote_bullish_hit = False
        ote_bearish_hit = False

        if sh_indices and sl_indices:
            last_sh = float(df["high"].iloc[sh_indices[-1]])
            last_sl = float(df["low"].iloc[sl_indices[-1]])
            bull_ote_low, bull_ote_high = _compute_ote_zone(last_sl, last_sh, "bullish")
            bear_ote_low, bear_ote_high = _compute_ote_zone(last_sl, last_sh, "bearish")
            ote_bullish_hit = _price_in_zone(price, bull_ote_low, bull_ote_high)
            ote_bearish_hit = _price_in_zone(price, bear_ote_low, bear_ote_high)
        else:
            bull_ote_low = bull_ote_high = bear_ote_low = bear_ote_high = price

        # Bullish OB near price
        near_bullish_ob = any(
            _price_in_zone(price, ob.low, ob.high)
            for ob in order_blocks[-10:]
            if ob.kind == "bullish"
        )
        near_bearish_ob = any(
            _price_in_zone(price, ob.low, ob.high)
            for ob in order_blocks[-10:]
            if ob.kind == "bearish"
        )

        # Scoring: each condition = 1 point
        long_score = sum([
            in_discount,
            near_bullish_ob,
            sweep_type == "sell_swept",
            ote_bullish_hit,
        ])
        short_score = sum([
            in_premium,
            near_bearish_ob,
            sweep_type == "buy_swept",
            ote_bearish_hit,
        ])

        max_score = 4

        if long_score > short_score and long_score >= 2:
            confidence = long_score / max_score
            direction = SignalDirection.LONG
            reasoning = (
                f"SMC LONG: discount={in_discount}, bullish_OB={near_bullish_ob}, "
                f"sweep={sweep_type}, OTE={ote_bullish_hit}. Score={long_score}/{max_score}."
            )
        elif short_score > long_score and short_score >= 2:
            confidence = short_score / max_score
            direction = SignalDirection.SHORT
            reasoning = (
                f"SMC SHORT: premium={in_premium}, bearish_OB={near_bearish_ob}, "
                f"sweep={sweep_type}, OTE={ote_bearish_hit}. Score={short_score}/{max_score}."
            )
        else:
            confidence = 0.0
            direction = SignalDirection.NEUTRAL
            reasoning = (
                f"Insufficient SMC confluence. Long={long_score}, Short={short_score}. "
                f"Price={price:.5f}, Eq={equilibrium:.5f}."
            )

        log.info(
            "smc_signal",
            direction=direction.value,
            confidence=confidence,
            long_score=long_score,
            short_score=short_score,
            sweep_type=sweep_type,
        )

        return AgentSignal(
            agent_id=self.agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            supporting_data={
                "price": price,
                "equilibrium": round(equilibrium, 5),
                "range_high": round(range_high, 5),
                "range_low": round(range_low, 5),
                "in_discount": in_discount,
                "in_premium": in_premium,
                "near_bullish_ob": near_bullish_ob,
                "near_bearish_ob": near_bearish_ob,
                "liquidity_sweep": sweep_type,
                "ote_bullish_hit": ote_bullish_hit,
                "ote_bearish_hit": ote_bearish_hit,
                "long_score": long_score,
                "short_score": short_score,
            },
        )
