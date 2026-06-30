"""Sentiment Agent - RSI, Stochastic, COT data, and divergence detection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import structlog
import ta.momentum

from forex_trading.ai.agents.base import (
    AgentSignal,
    BaseAgent,
    MarketContext,
    MarketRegime,
    SignalDirection,
)

logger = structlog.get_logger()

_MIN_CANDLES = 30
_RSI_PERIOD = 14
_STOCH_K = 14
_STOCH_D = 3
_STOCH_SMOOTH = 3
_RSI_OVERSOLD = 30.0
_RSI_OVERBOUGHT = 70.0
_STOCH_OVERSOLD = 20.0
_STOCH_OVERBOUGHT = 80.0
_DIVERGENCE_LOOKBACK = 10


def _build_dataframe(candles: list[dict]) -> pd.DataFrame:
    """Convert candle dicts to typed DataFrame."""
    df = pd.DataFrame(candles)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute RSI, Stochastic %K/%D."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    rsi_obj = ta.momentum.RSIIndicator(close=close, window=_RSI_PERIOD)
    df["rsi"] = rsi_obj.rsi()

    stoch_obj = ta.momentum.StochasticOscillator(
        high=high,
        low=low,
        close=close,
        window=_STOCH_K,
        smooth_window=_STOCH_SMOOTH,
    )
    df["stoch_k"] = stoch_obj.stoch()
    df["stoch_d"] = stoch_obj.stoch_signal()

    return df


def _detect_divergence(df: pd.DataFrame, lookback: int = _DIVERGENCE_LOOKBACK) -> str:
    """
    Detect RSI divergence over the last `lookback` candles.

    Bearish divergence: price makes HH but RSI makes LH.
    Bullish divergence: price makes LL but RSI makes HL.
    Returns 'bearish_divergence', 'bullish_divergence', or 'none'.
    """
    if len(df) < lookback + 2:
        return "none"

    window = df.tail(lookback)
    prices = window["close"].values
    rsi_vals = window["rsi"].values

    # Skip if any NaN in RSI
    if any(pd.isna(r) for r in rsi_vals):
        return "none"

    price_max_idx = int(np.argmax(prices))
    price_min_idx = int(np.argmin(prices))

    # Bearish divergence: price HH but RSI not HH
    # Check: is the most recent price near the high but RSI lower than RSI at the price high?
    recent_price = prices[-1]
    recent_rsi = rsi_vals[-1]
    price_at_high = prices[price_max_idx]
    rsi_at_high = rsi_vals[price_max_idx]

    # Last candle is near the high but RSI is declining
    if (
        price_max_idx < len(prices) - 2  # high was earlier
        and recent_price >= price_at_high * 0.999
        and recent_rsi < rsi_at_high * 0.97  # RSI meaningfully lower
    ):
        return "bearish_divergence"

    # Bullish divergence: price LL but RSI not LL
    price_at_low = prices[price_min_idx]
    rsi_at_low = rsi_vals[price_min_idx]

    if (
        price_min_idx < len(prices) - 2
        and recent_price <= price_at_low * 1.001
        and recent_rsi > rsi_at_low * 1.03
    ):
        return "bullish_divergence"

    return "none"


def _get_cot_bias(metadata: dict) -> tuple[str, float]:
    """
    Extract COT (Commitment of Traders) bias from metadata if available.

    Returns (bias, confidence_boost) where bias in {'bullish','bearish','neutral'}.
    """
    cot = metadata.get("cot_data")
    if not cot or not isinstance(cot, dict):
        return "neutral", 0.0

    net_noncommercial = cot.get("net_noncommercial", 0)
    if not isinstance(net_noncommercial, (int, float)):
        return "neutral", 0.0

    if net_noncommercial > 0:
        return "bullish", min(abs(net_noncommercial) / 100000.0, 0.15)
    if net_noncommercial < 0:
        return "bearish", min(abs(net_noncommercial) / 100000.0, 0.15)
    return "neutral", 0.0


class SentimentAgent(BaseAgent):
    """
    Analyzes market sentiment using RSI, Stochastic, divergence, and optional COT data.

    Oversold → LONG; Overbought → SHORT; divergence signals reinforce or reverse.
    Medium weight in all regimes, highest in RANGING.
    """

    def __init__(self) -> None:
        super().__init__(agent_id="sentiment", name="Sentiment Agent")

    def required_data(self) -> list[str]:
        """Return required data keys."""
        return ["candles"]

    def get_weight(self, regime: MarketRegime) -> float:
        """Return agent weight; highest in ranging regime."""
        weights: dict[MarketRegime, float] = {
            MarketRegime.RANGING: 0.80,
            MarketRegime.TRENDING_UP: 0.50,
            MarketRegime.TRENDING_DOWN: 0.50,
            MarketRegime.VOLATILE: 0.55,
            MarketRegime.LOW_VOLATILITY: 0.65,
        }
        return weights.get(regime, 0.55)

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Analyze sentiment indicators and return a signal."""
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

        df = _compute_indicators(df)
        last = df.iloc[-1]

        if any(pd.isna(last[c]) for c in ["rsi", "stoch_k", "stoch_d"]):
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                reasoning="Indicator NaN — need more history",
            )

        rsi = float(last["rsi"])
        stoch_k = float(last["stoch_k"])
        stoch_d = float(last["stoch_d"])

        divergence = _detect_divergence(df)
        cot_bias, cot_boost = _get_cot_bias(context.metadata)

        signals: list[tuple[SignalDirection, float, str]] = []

        # Oversold
        if rsi < _RSI_OVERSOLD and stoch_k < _STOCH_OVERSOLD:
            rsi_depth = (_RSI_OVERSOLD - rsi) / _RSI_OVERSOLD
            stoch_depth = (_STOCH_OVERSOLD - stoch_k) / _STOCH_OVERSOLD
            conf = min((rsi_depth + stoch_depth) / 2.0 * 1.5, 0.80)
            signals.append((SignalDirection.LONG, conf, f"RSI oversold={rsi:.1f}, Stoch oversold={stoch_k:.1f}"))
        elif rsi < _RSI_OVERSOLD:
            conf = min((_RSI_OVERSOLD - rsi) / _RSI_OVERSOLD, 0.60)
            signals.append((SignalDirection.LONG, conf, f"RSI oversold={rsi:.1f}"))

        # Overbought
        if rsi > _RSI_OVERBOUGHT and stoch_k > _STOCH_OVERBOUGHT:
            rsi_height = (rsi - _RSI_OVERBOUGHT) / (100.0 - _RSI_OVERBOUGHT)
            stoch_height = (stoch_k - _STOCH_OVERBOUGHT) / (100.0 - _STOCH_OVERBOUGHT)
            conf = min((rsi_height + stoch_height) / 2.0 * 1.5, 0.80)
            signals.append((SignalDirection.SHORT, conf, f"RSI overbought={rsi:.1f}, Stoch overbought={stoch_k:.1f}"))
        elif rsi > _RSI_OVERBOUGHT:
            conf = min((rsi - _RSI_OVERBOUGHT) / (100.0 - _RSI_OVERBOUGHT), 0.60)
            signals.append((SignalDirection.SHORT, conf, f"RSI overbought={rsi:.1f}"))

        # Divergence signals
        if divergence == "bearish_divergence":
            signals.append((SignalDirection.SHORT, 0.55, "Bearish RSI divergence detected"))
        elif divergence == "bullish_divergence":
            signals.append((SignalDirection.LONG, 0.55, "Bullish RSI divergence detected"))

        # COT alignment boost
        if cot_bias == "bullish" and signals:
            for i, (d, c, r) in enumerate(signals):
                if d == SignalDirection.LONG:
                    signals[i] = (d, min(c + cot_boost, 1.0), r + f" (COT bullish +{cot_boost:.0%})")
        elif cot_bias == "bearish" and signals:
            for i, (d, c, r) in enumerate(signals):
                if d == SignalDirection.SHORT:
                    signals[i] = (d, min(c + cot_boost, 1.0), r + f" (COT bearish +{cot_boost:.0%})")

        if not signals:
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                reasoning=f"No extreme sentiment. RSI={rsi:.1f}, Stoch={stoch_k:.1f}.",
                supporting_data={"rsi": rsi, "stoch_k": stoch_k, "stoch_d": stoch_d},
            )

        # Aggregate: pick dominant direction by summed confidence
        long_conf = sum(c for d, c, _ in signals if d == SignalDirection.LONG)
        short_conf = sum(c for d, c, _ in signals if d == SignalDirection.SHORT)

        if long_conf >= short_conf:
            direction = SignalDirection.LONG
            confidence = min(long_conf / max(len(signals), 1), 1.0)
            reasoning_parts = [r for d, _, r in signals if d == SignalDirection.LONG]
        else:
            direction = SignalDirection.SHORT
            confidence = min(short_conf / max(len(signals), 1), 1.0)
            reasoning_parts = [r for d, _, r in signals if d == SignalDirection.SHORT]

        reasoning = ". ".join(reasoning_parts) if reasoning_parts else "No clear sentiment signal."

        log.info(
            "sentiment_signal",
            direction=direction.value,
            confidence=confidence,
            rsi=round(rsi, 1),
            stoch_k=round(stoch_k, 1),
            divergence=divergence,
        )

        return AgentSignal(
            agent_id=self.agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            supporting_data={
                "rsi": round(rsi, 2),
                "stoch_k": round(stoch_k, 2),
                "stoch_d": round(stoch_d, 2),
                "divergence": divergence,
                "cot_bias": cot_bias,
            },
        )
