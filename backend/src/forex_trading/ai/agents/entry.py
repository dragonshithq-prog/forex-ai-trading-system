"""Entry Agent - evaluates precision entry timing using candlestick patterns and confluence."""

from __future__ import annotations

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

_MIN_CANDLES = 20
_MIN_RR_RATIO = 1.5
_PROXIMITY_PCT = 0.002  # 0.20% of price to be "at a level"
_SWING_LOOKBACK = 5


def _build_dataframe(candles: list[dict]) -> pd.DataFrame:
    """Convert candle dicts to typed DataFrame."""
    df = pd.DataFrame(candles)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _is_pin_bar(row: pd.Series, direction: str) -> tuple[bool, float]:
    """
    Detect pin bar candlestick pattern.

    Bullish pin bar: long lower wick, small body, closes in upper 1/3.
    Bearish pin bar: long upper wick, small body, closes in lower 1/3.
    Returns (is_pin_bar, quality_score 0-1).
    """
    o = float(row["open"])
    c = float(row["close"])
    h = float(row["high"])
    lo = float(row["low"])

    candle_range = h - lo
    if candle_range < 1e-8:
        return False, 0.0

    body = abs(c - o)
    body_ratio = body / candle_range

    if direction == "bullish":
        lower_wick = min(o, c) - lo
        upper_wick = h - max(o, c)
        lower_ratio = lower_wick / candle_range
        # Good pin bar: body < 40%, lower wick > 60%, closes in upper third
        if body_ratio < 0.40 and lower_ratio > 0.60 and c > (lo + candle_range * 0.66):
            quality = lower_ratio - body_ratio
            return True, min(quality, 1.0)

    elif direction == "bearish":
        upper_wick = h - max(o, c)
        upper_ratio = upper_wick / candle_range
        if body_ratio < 0.40 and upper_ratio > 0.60 and c < (lo + candle_range * 0.34):
            quality = upper_ratio - body_ratio
            return True, min(quality, 1.0)

    return False, 0.0


def _is_engulfing(prev: pd.Series, curr: pd.Series, direction: str) -> tuple[bool, float]:
    """
    Detect engulfing candlestick pattern.

    Bullish engulfing: current bullish candle body engulfs previous bearish body.
    Bearish engulfing: current bearish candle body engulfs previous bullish body.
    Returns (is_engulfing, quality_score 0-1).
    """
    prev_body = abs(float(prev["close"]) - float(prev["open"]))
    curr_body = abs(float(curr["close"]) - float(curr["open"]))

    if prev_body < 1e-8:
        return False, 0.0

    if direction == "bullish":
        # Prev bearish, curr bullish and engulfs
        if (float(prev["close"]) < float(prev["open"])
                and float(curr["close"]) > float(curr["open"])
                and float(curr["close"]) > float(prev["open"])
                and float(curr["open"]) < float(prev["close"])):
            quality = min(curr_body / prev_body, 1.0)
            return True, quality

    elif direction == "bearish":
        if (float(prev["close"]) > float(prev["open"])
                and float(curr["close"]) < float(curr["open"])
                and float(curr["close"]) < float(prev["open"])
                and float(curr["open"]) > float(prev["close"])):
            quality = min(curr_body / prev_body, 1.0)
            return True, quality

    return False, 0.0


def _find_sr_levels(df: pd.DataFrame, lookback: int = _SWING_LOOKBACK) -> tuple[list[float], list[float]]:
    """Find support (swing lows) and resistance (swing highs) levels."""
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    resistance: list[float] = []
    support: list[float] = []

    for i in range(lookback, n - lookback):
        if highs[i] == highs[i - lookback : i + lookback + 1].max():
            resistance.append(float(highs[i]))
        if lows[i] == lows[i - lookback : i + lookback + 1].min():
            support.append(float(lows[i]))

    return support, resistance


def _price_at_level(price: float, levels: list[float], factor: float = _PROXIMITY_PCT) -> bool:
    """Return True if price is within factor% of any level."""
    for lvl in levels:
        if abs(price - lvl) / lvl < factor:
            return True
    return False


def _check_volume_confirmation(df: pd.DataFrame, lookback: int = 10) -> bool:
    """Return True if last candle volume is above average of prior lookback candles."""
    if len(df) < lookback + 1:
        return False
    avg_vol = float(df["volume"].iloc[-(lookback + 1): -1].mean())
    last_vol = float(df["volume"].iloc[-1])
    if avg_vol < 1e-8:
        return False
    return last_vol > avg_vol


def _estimate_rr(
    entry: float,
    stop: float,
    target: float,
) -> float:
    """Estimate Risk:Reward ratio."""
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk < 1e-8:
        return 0.0
    return reward / risk


class EntryAgent(BaseAgent):
    """
    Evaluates precision entry quality: pin bars, engulfing patterns, S/R confluence,
    volume confirmation, and minimum R:R ratio.

    LONG/SHORT with confidence based on composite entry quality score.
    Highest weight in all regimes — must confirm the trade entry.
    """

    def __init__(self, min_rr_ratio: float = _MIN_RR_RATIO) -> None:
        super().__init__(agent_id="entry_ai", name="Entry Agent")
        self._min_rr_ratio = min_rr_ratio

    def required_data(self) -> list[str]:
        """Return required data keys."""
        return ["candles", "ticks"]

    def get_weight(self, regime: MarketRegime) -> float:
        """Return high weight in all regimes — entry quality must be confirmed."""
        return 0.80

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Evaluate entry conditions and return a signal."""
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

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = float(last["close"])
        atr_approx = float(df["high"].tail(14).max() - df["low"].tail(14).min()) / 14.0

        support_levels, resistance_levels = _find_sr_levels(df)
        volume_ok = _check_volume_confirmation(df)

        # Check patterns for both directions
        bull_pin, bull_pin_q = _is_pin_bar(last, "bullish")
        bear_pin, bear_pin_q = _is_pin_bar(last, "bearish")
        bull_eng, bull_eng_q = _is_engulfing(prev, last, "bullish")
        bear_eng, bear_eng_q = _is_engulfing(prev, last, "bearish")

        at_support = _price_at_level(price, support_levels)
        at_resistance = _price_at_level(price, resistance_levels)

        # R:R estimation using ATR-based stop and target
        stop_long = price - atr_approx * 1.5
        target_long = price + atr_approx * 1.5 * self._min_rr_ratio
        rr_long = _estimate_rr(price, stop_long, target_long)

        stop_short = price + atr_approx * 1.5
        target_short = price - atr_approx * 1.5 * self._min_rr_ratio
        rr_short = _estimate_rr(price, stop_short, target_short)

        # Scoring — 5 points max
        long_score: list[tuple[str, float]] = []
        short_score: list[tuple[str, float]] = []

        if bull_pin:
            long_score.append(("bullish_pin_bar", bull_pin_q))
        if bull_eng:
            long_score.append(("bullish_engulfing", bull_eng_q))
        if at_support:
            long_score.append(("at_support", 0.70))
        if volume_ok:
            long_score.append(("volume_confirmation", 0.60))
        if rr_long >= self._min_rr_ratio:
            long_score.append(("rr_acceptable", min(rr_long / 3.0, 1.0)))

        if bear_pin:
            short_score.append(("bearish_pin_bar", bear_pin_q))
        if bear_eng:
            short_score.append(("bearish_engulfing", bear_eng_q))
        if at_resistance:
            short_score.append(("at_resistance", 0.70))
        if volume_ok:
            short_score.append(("volume_confirmation", 0.60))
        if rr_short >= self._min_rr_ratio:
            short_score.append(("rr_acceptable", min(rr_short / 3.0, 1.0)))

        long_total = sum(q for _, q in long_score)
        short_total = sum(q for _, q in short_score)
        max_possible = 5 * 1.0  # max score

        if long_total > short_total and len(long_score) >= 2:
            confidence = min(long_total / max_possible, 1.0)
            direction = SignalDirection.LONG
            factors = [f for f, _ in long_score]
            reasoning = f"Entry quality LONG ({len(long_score)} factors): {', '.join(factors)}. RR={rr_long:.2f}."
        elif short_total > long_total and len(short_score) >= 2:
            confidence = min(short_total / max_possible, 1.0)
            direction = SignalDirection.SHORT
            factors = [f for f, _ in short_score]
            reasoning = f"Entry quality SHORT ({len(short_score)} factors): {', '.join(factors)}. RR={rr_short:.2f}."
        else:
            confidence = 0.0
            direction = SignalDirection.NEUTRAL
            reasoning = (
                f"No quality entry setup. Long factors={len(long_score)}, "
                f"Short factors={len(short_score)}. Price={price:.5f}."
            )

        log.info(
            "entry_signal",
            direction=direction.value,
            confidence=confidence,
            long_factors=len(long_score),
            short_factors=len(short_score),
        )

        return AgentSignal(
            agent_id=self.agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            supporting_data={
                "price": price,
                "at_support": at_support,
                "at_resistance": at_resistance,
                "volume_ok": volume_ok,
                "rr_long": round(rr_long, 2),
                "rr_short": round(rr_short, 2),
                "bull_pin": bull_pin,
                "bear_pin": bear_pin,
                "bull_engulfing": bull_eng,
                "bear_engulfing": bear_eng,
                "long_score_count": len(long_score),
                "short_score_count": len(short_score),
            },
        )
