"""Volatility Agent - ATR, Bollinger Bands, realized volatility regime classification."""

from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd
import structlog
import ta.volatility

from forex_trading.ai.agents.base import (
    AgentSignal,
    BaseAgent,
    MarketContext,
    MarketRegime,
    SignalDirection,
)

logger = structlog.get_logger()

_MIN_CANDLES = 30
_ATR_PERIOD = 14
_BB_PERIOD = 20
_BB_STD = 2.0
_REALIZED_VOL_PERIOD = 20


class VolatilityRegime(str, Enum):
    """Internal volatility regime classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


def _build_dataframe(candles: list[dict]) -> pd.DataFrame:
    """Convert candle dicts to typed DataFrame."""
    df = pd.DataFrame(candles)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _compute_volatility_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute ATR, Bollinger Bands, and realized volatility."""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    atr_obj = ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=_ATR_PERIOD)
    df["atr"] = atr_obj.average_true_range()

    bb_obj = ta.volatility.BollingerBands(
        close=close,
        window=_BB_PERIOD,
        window_dev=_BB_STD,
    )
    df["bb_high"] = bb_obj.bollinger_hband()
    df["bb_mid"] = bb_obj.bollinger_mavg()
    df["bb_low"] = bb_obj.bollinger_lband()
    df["bb_width"] = bb_obj.bollinger_wband()  # (bb_high - bb_low) / bb_mid
    df["bb_pct"] = bb_obj.bollinger_pband()    # (price - bb_low) / (bb_high - bb_low)

    # Realized volatility: rolling std of log returns, annualized
    log_returns = np.log(close / close.shift(1))
    df["realized_vol"] = log_returns.rolling(_REALIZED_VOL_PERIOD).std() * np.sqrt(252)

    return df


def _classify_volatility_regime(
    atr: float,
    atr_mean: float,
    bb_width: float,
    bb_width_mean: float,
    realized_vol: float,
) -> VolatilityRegime:
    """Classify current volatility into LOW/MEDIUM/HIGH/EXTREME."""
    atr_ratio = atr / atr_mean if atr_mean > 0 else 1.0
    bb_ratio = bb_width / bb_width_mean if bb_width_mean > 0 else 1.0

    # Weighted score: both ATR and BB width relative to their means
    vol_score = (atr_ratio + bb_ratio) / 2.0

    if vol_score > 2.0 or realized_vol > 0.30:
        return VolatilityRegime.EXTREME
    if vol_score > 1.4 or realized_vol > 0.20:
        return VolatilityRegime.HIGH
    if vol_score > 0.75:
        return VolatilityRegime.MEDIUM
    return VolatilityRegime.LOW


def _detect_bb_breakout_direction(df: pd.DataFrame) -> SignalDirection:
    """
    Detect potential breakout direction from Bollinger Band compression.

    Uses momentum of last 3 closes relative to BB midline.
    """
    if len(df) < 3:
        return SignalDirection.NEUTRAL

    recent = df.tail(3)
    closes = recent["close"].values
    bb_mids = recent["bb_mid"].values

    if any(pd.isna(v) for v in list(closes) + list(bb_mids)):
        return SignalDirection.NEUTRAL

    # Price momentum above or below midline signals direction
    above_mid = sum(1 for c, m in zip(closes, bb_mids) if c > m)
    if above_mid >= 2:
        return SignalDirection.LONG
    below_mid = sum(1 for c, m in zip(closes, bb_mids) if c < m)
    if below_mid >= 2:
        return SignalDirection.SHORT
    return SignalDirection.NEUTRAL


class VolatilityAgent(BaseAgent):
    """
    Classifies current volatility regime and produces trading signals based on it.

    EXTREME volatility → NEUTRAL (risk too high).
    LOW volatility + BB compression → potential breakout signal.
    MEDIUM/HIGH → signal based on ATR-filtered price position.
    """

    def __init__(self) -> None:
        super().__init__(agent_id="volatility", name="Volatility Agent")

    def required_data(self) -> list[str]:
        """Return required data keys."""
        return ["candles"]

    def get_weight(self, regime: MarketRegime) -> float:
        """Return agent weight; highest in volatile and low-volatility regimes."""
        weights: dict[MarketRegime, float] = {
            MarketRegime.VOLATILE: 0.85,
            MarketRegime.LOW_VOLATILITY: 0.85,
            MarketRegime.RANGING: 0.65,
            MarketRegime.TRENDING_UP: 0.55,
            MarketRegime.TRENDING_DOWN: 0.55,
        }
        return weights.get(regime, 0.60)

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Analyze volatility regime and return a signal."""
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

        df = _compute_volatility_indicators(df)
        last = df.iloc[-1]

        required = ["atr", "bb_width", "bb_pct", "realized_vol"]
        if any(pd.isna(last[c]) for c in required):
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.0,
                reasoning="Indicator NaN — need more history",
            )

        atr = float(last["atr"])
        bb_width = float(last["bb_width"])
        bb_pct = float(last["bb_pct"])
        realized_vol = float(last["realized_vol"])
        price = float(last["close"])

        # Historical means for ratio computation
        atr_mean = float(df["atr"].dropna().mean())
        bb_width_mean = float(df["bb_width"].dropna().mean())

        vol_regime = _classify_volatility_regime(atr, atr_mean, bb_width, bb_width_mean, realized_vol)

        if vol_regime == VolatilityRegime.EXTREME:
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.10,
                reasoning=(
                    f"EXTREME volatility: ATR={atr:.5f} ({atr / atr_mean:.1f}x mean), "
                    f"realized_vol={realized_vol:.2%}. Avoiding trade."
                ),
                supporting_data={"volatility_regime": vol_regime.value, "atr": atr, "realized_vol": realized_vol},
            )

        if vol_regime == VolatilityRegime.LOW:
            breakout_dir = _detect_bb_breakout_direction(df)
            bb_width_ratio = bb_width / bb_width_mean if bb_width_mean > 0 else 1.0
            # Confidence: tighter bands = higher breakout potential
            confidence = min(0.40 + (1.0 - bb_width_ratio) * 0.40, 0.75)
            confidence = max(confidence, 0.0)

            if breakout_dir != SignalDirection.NEUTRAL:
                return AgentSignal(
                    agent_id=self.agent_id,
                    direction=breakout_dir,
                    confidence=confidence,
                    reasoning=(
                        f"LOW volatility with BB compression (width ratio={bb_width_ratio:.2f}). "
                        f"Potential {breakout_dir.value} breakout. ATR={atr:.5f}."
                    ),
                    supporting_data={
                        "volatility_regime": vol_regime.value,
                        "atr": atr,
                        "bb_width": bb_width,
                        "bb_width_mean": bb_width_mean,
                        "realized_vol": realized_vol,
                    },
                )
            return AgentSignal(
                agent_id=self.agent_id,
                direction=SignalDirection.NEUTRAL,
                confidence=0.30,
                reasoning=f"LOW volatility, BB compressed, no clear breakout direction yet.",
                supporting_data={"volatility_regime": vol_regime.value, "atr": atr},
            )

        # MEDIUM / HIGH: use BB %B and ATR to gauge direction quality
        if bb_pct > 0.80:
            # Price near upper band in non-extreme volatility → overextended SHORT
            confidence = min((bb_pct - 0.80) / 0.20 * 0.60, 0.60)
            direction = SignalDirection.SHORT
            reasoning = (
                f"{vol_regime.value.upper()} volatility: price at {bb_pct:.0%} of BB "
                f"(overbought). ATR={atr:.5f}."
            )
        elif bb_pct < 0.20:
            confidence = min((0.20 - bb_pct) / 0.20 * 0.60, 0.60)
            direction = SignalDirection.LONG
            reasoning = (
                f"{vol_regime.value.upper()} volatility: price at {bb_pct:.0%} of BB "
                f"(oversold). ATR={atr:.5f}."
            )
        else:
            confidence = 0.0
            direction = SignalDirection.NEUTRAL
            reasoning = (
                f"{vol_regime.value.upper()} volatility: price within BB bands "
                f"({bb_pct:.0%}). No edge."
            )

        log.info(
            "volatility_signal",
            vol_regime=vol_regime.value,
            direction=direction.value,
            confidence=confidence,
            atr=round(atr, 5),
        )

        return AgentSignal(
            agent_id=self.agent_id,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            supporting_data={
                "volatility_regime": vol_regime.value,
                "atr": round(atr, 5),
                "bb_width": round(bb_width, 4),
                "bb_pct": round(bb_pct, 4),
                "realized_vol": round(realized_vol, 4),
            },
        )
