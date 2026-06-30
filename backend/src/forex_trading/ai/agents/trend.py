"""Trend Agent - EMA alignment, MACD, and ADX-based trend detection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import structlog
import ta
import ta.momentum
import ta.trend
import ta.volatility

from forex_trading.ai.agents.base import (
    AgentSignal,
    BaseAgent,
    MarketContext,
    MarketRegime,
    SignalDirection,
)

logger = structlog.get_logger()

_MIN_CANDLES = 220  # need 200 EMA + buffer
_EMA_FAST = 20
_EMA_MID = 50
_EMA_SLOW = 200
_ADX_STRONG = 25


def _build_dataframe(candles: list[dict]) -> pd.DataFrame:
    """Convert candle dicts to typed DataFrame."""
    df = pd.DataFrame(candles)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute EMA 20/50/200, MACD, and ADX on the DataFrame."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["ema20"] = ta.trend.EMAIndicator(close=close, window=_EMA_FAST).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(close=close, window=_EMA_MID).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(close=close, window=_EMA_SLOW).ema_indicator()

    macd_obj = ta.trend.MACD(close=close)
    df["macd"] = macd_obj.macd()
    df["macd_signal"] = macd_obj.macd_signal()
    df["macd_diff"] = macd_obj.macd_diff()

    adx_obj = ta.trend.ADXIndicator(high=high, low=low, close=close, window=14)
    df["adx"] = adx_obj.adx()
    df["adx_pos"] = adx_obj.adx_pos()
    df["adx_neg"] = adx_obj.adx_neg()

    return df


class TrendAgent(BaseAgent):
    """
    Detects trend direction and strength using EMA alignment, MACD, and ADX.

    LONG when EMA20 > EMA50 > EMA200 and price above EMA200 and MACD positive.
    SHORT when EMA20 < EMA50 < EMA200 and price below EMA200 and MACD negative.
    Confidence derived from ADX (strength) capped to [0, 1].
    """

    def __init__(self) -> None:
        super().__init__(agent_id="trend", name="Trend Agent")

    def required_data(self) -> list[str]:
        """Return required data keys."""
        return ["candles"]

    def get_weight(self, regime: MarketRegime) -> float:
        """Return agent weight; highest in trending regimes."""
        weights: dict[MarketRegime, float] = {
            MarketRegime.TRENDING_UP: 0.90,
            MarketRegime.TRENDING_DOWN: 0.90,
            MarketRegime.RANGING: 0.40,
            MarketRegime.VOLATILE: 0.55,
            MarketRegime.LOW_VOLATILITY: 0.50,
        }
        return weights.get(regime, 0.55)

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Analyze trend using EMA, MACD and ADX indicators."""
        log = logger.bind(agent=self.agent_id, symbol=context.symbol)

        if len(context.candles) < _MIN_CANDLES:
            log.warning("insufficient_candles", count=len(context.candles))
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

        df = _compute_indicators(df)
        last = df.iloc[-1]

        # Guard: NaN values from insufficient history
        required_cols = ["ema20", "ema50", "ema200", "macd_diff", "adx"]
        if any(pd.isna(last[c]) for c in required_cols):
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                reasoning="Indicator values contain NaN — need more history",
            )

        price = float(last["close"])
        ema20 = float(last["ema20"])
        ema50 = float(last["ema50"])
        ema200 = float(last["ema200"])
        macd_diff = float(last["macd_diff"])
        adx = float(last["adx"])
        adx_pos = float(last["adx_pos"])
        adx_neg = float(last["adx_neg"])

        # Confidence from ADX
        confidence = min(adx / 100.0, 1.0)

        # Bullish alignment: EMA20 > EMA50 > EMA200, price > EMA200, MACD positive
        bullish_ema = ema20 > ema50 > ema200
        bearish_ema = ema20 < ema50 < ema200

        bullish_conditions = [
            bullish_ema,
            price > ema200,
            macd_diff > 0,
            adx_pos > adx_neg,
        ]
        bearish_conditions = [
            bearish_ema,
            price < ema200,
            macd_diff < 0,
            adx_neg > adx_pos,
        ]

        bull_score = sum(bullish_conditions)
        bear_score = sum(bearish_conditions)

        if bull_score >= 3:
            direction = SignalDirection.LONG
            strength = "strong" if adx > _ADX_STRONG else "weak"
            reasoning = (
                f"Bullish trend: EMA alignment={bullish_ema}, price>EMA200={price > ema200}, "
                f"MACD diff={macd_diff:.5f}, ADX={adx:.1f} ({strength}). "
                f"{bull_score}/4 conditions met."
            )
        elif bear_score >= 3:
            direction = SignalDirection.SHORT
            strength = "strong" if adx > _ADX_STRONG else "weak"
            reasoning = (
                f"Bearish trend: EMA alignment={bearish_ema}, price<EMA200={price < ema200}, "
                f"MACD diff={macd_diff:.5f}, ADX={adx:.1f} ({strength}). "
                f"{bear_score}/4 conditions met."
            )
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0
            reasoning = (
                f"No clear trend. Bull score={bull_score}/4, Bear score={bear_score}/4. "
                f"ADX={adx:.1f}, EMA20={ema20:.5f}, EMA50={ema50:.5f}, EMA200={ema200:.5f}."
            )

        log.info(
            "trend_signal",
            direction=direction.value,
            confidence=confidence,
            adx=round(adx, 2),
            bull_score=bull_score,
            bear_score=bear_score,
        )

        return AgentSignal(
            agent_id=self.agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            supporting_data={
                "ema20": round(ema20, 5),
                "ema50": round(ema50, 5),
                "ema200": round(ema200, 5),
                "macd_diff": round(macd_diff, 6),
                "adx": round(adx, 2),
                "adx_pos": round(adx_pos, 2),
                "adx_neg": round(adx_neg, 2),
                "bull_score": bull_score,
                "bear_score": bear_score,
            },
        )
