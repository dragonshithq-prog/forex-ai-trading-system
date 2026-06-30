"""Market Structure Agent - detects BOS, CHoCH, HH/HL, LH/LL patterns."""

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
_SWING_LOOKBACK = 5  # bars each side to qualify as swing high/low


def _build_dataframe(candles: list[dict]) -> pd.DataFrame:
    """Convert candle dicts to a typed DataFrame."""
    df = pd.DataFrame(candles)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _find_swing_highs(highs: np.ndarray, lookback: int = _SWING_LOOKBACK) -> list[int]:
    """Return indices that are swing highs (local maxima) with given lookback."""
    indices: list[int] = []
    n = len(highs)
    for i in range(lookback, n - lookback):
        window = highs[i - lookback : i + lookback + 1]
        if highs[i] == window.max():
            indices.append(i)
    return indices


def _find_swing_lows(lows: np.ndarray, lookback: int = _SWING_LOOKBACK) -> list[int]:
    """Return indices that are swing lows (local minima) with given lookback."""
    indices: list[int] = []
    n = len(lows)
    for i in range(lookback, n - lookback):
        window = lows[i - lookback : i + lookback + 1]
        if lows[i] == window.min():
            indices.append(i)
    return indices


def _classify_structure(
    swing_high_prices: list[float],
    swing_low_prices: list[float],
) -> tuple[str, int]:
    """
    Classify market structure as bullish or bearish using the last 3 swing points.

    Returns (structure_label, consecutive_confirms) where structure_label is one of:
    'bullish', 'bearish', 'unclear'.
    """
    if len(swing_high_prices) < 2 or len(swing_low_prices) < 2:
        return "unclear", 0

    bullish_confirms = 0
    bearish_confirms = 0

    # Higher Highs
    for i in range(1, min(len(swing_high_prices), 4)):
        if swing_high_prices[-i] > swing_high_prices[-(i + 1)]:
            bullish_confirms += 1
        else:
            break

    # Higher Lows
    for i in range(1, min(len(swing_low_prices), 4)):
        if swing_low_prices[-i] > swing_low_prices[-(i + 1)]:
            bullish_confirms += 1
        else:
            break

    # Lower Lows
    for i in range(1, min(len(swing_low_prices), 4)):
        if swing_low_prices[-i] < swing_low_prices[-(i + 1)]:
            bearish_confirms += 1
        else:
            break

    # Lower Highs
    for i in range(1, min(len(swing_high_prices), 4)):
        if swing_high_prices[-i] < swing_high_prices[-(i + 1)]:
            bearish_confirms += 1
        else:
            break

    if bullish_confirms > bearish_confirms and bullish_confirms >= 2:
        return "bullish", bullish_confirms
    if bearish_confirms > bullish_confirms and bearish_confirms >= 2:
        return "bearish", bearish_confirms
    return "unclear", 0


def _detect_bos(
    df: pd.DataFrame,
    sh_indices: list[int],
    sl_indices: list[int],
) -> tuple[str, str]:
    """
    Detect the most recent Break of Structure (BOS) or Change of Character (CHoCH).

    Returns (event_type, direction): event_type in {'BOS','CHoCH','none'},
    direction in {'bullish','bearish','none'}.
    """
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    if not sh_indices or not sl_indices:
        return "none", "none"

    last_sh_idx = sh_indices[-1]
    last_sl_idx = sl_indices[-1]
    last_sh_price = highs[last_sh_idx]
    last_sl_price = lows[last_sl_idx]

    # Check for BOS bullish: price closes above last swing high
    for i in range(last_sh_idx + 1, n):
        if closes[i] > last_sh_price:
            # Was this preceded by a bearish structure? Then it's CHoCH
            if len(sh_indices) >= 2 and highs[sh_indices[-1]] < highs[sh_indices[-2]]:
                return "CHoCH", "bullish"
            return "BOS", "bullish"

    # Check for BOS bearish: price closes below last swing low
    for i in range(last_sl_idx + 1, n):
        if closes[i] < last_sl_price:
            if len(sl_indices) >= 2 and lows[sl_indices[-1]] > lows[sl_indices[-2]]:
                return "CHoCH", "bearish"
            return "BOS", "bearish"

    return "none", "none"


class MarketStructureAgent(BaseAgent):
    """
    Detects market structure: BOS, CHoCH, HH/HL (bullish) and LH/LL (bearish).

    Produces LONG when bullish structure is confirmed, SHORT for bearish, NEUTRAL otherwise.
    Confidence is proportional to the number of consecutive confirming structure points.
    """

    def __init__(self) -> None:
        super().__init__(agent_id="market_structure", name="Market Structure Agent")

    def required_data(self) -> list[str]:
        """Return required data keys."""
        return ["candles"]

    def get_weight(self, regime: MarketRegime) -> float:
        """Return agent weight; highest in trending regimes."""
        weights: dict[MarketRegime, float] = {
            MarketRegime.TRENDING_UP: 0.90,
            MarketRegime.TRENDING_DOWN: 0.90,
            MarketRegime.RANGING: 0.50,
            MarketRegime.VOLATILE: 0.60,
            MarketRegime.LOW_VOLATILITY: 0.65,
        }
        return weights.get(regime, 0.60)

    async def analyze(self, context: MarketContext) -> AgentSignal:
        """Analyze candle data and return a market structure signal."""
        log = logger.bind(agent=self.agent_id, symbol=context.symbol)

        if len(context.candles) < _MIN_CANDLES:
            log.warning("insufficient_candles", count=len(context.candles), required=_MIN_CANDLES)
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

        highs = df["high"].values
        lows = df["low"].values

        sh_indices = _find_swing_highs(highs)
        sl_indices = _find_swing_lows(lows)

        sh_prices = [float(highs[i]) for i in sh_indices]
        sl_prices = [float(lows[i]) for i in sl_indices]

        structure_label, confirms = _classify_structure(sh_prices, sl_prices)
        bos_event, bos_direction = _detect_bos(df, sh_indices, sl_indices)

        # Confidence: number of confirms scaled, capped at 1.0
        # Max possible confirms = 6 (3 HH + 3 HL or 3 LH + 3 LL)
        raw_confidence = min(confirms / 6.0, 1.0)

        # Boost confidence if BOS/CHoCH aligns with structure
        if bos_event in ("BOS", "CHoCH"):
            aligned = (bos_direction == "bullish" and structure_label == "bullish") or (
                bos_direction == "bearish" and structure_label == "bearish"
            )
            if aligned:
                raw_confidence = min(raw_confidence + 0.15, 1.0)

        if structure_label == "bullish":
            direction = SignalDirection.LONG
            reasoning = (
                f"Bullish market structure: {confirms} confirming points "
                f"(HH+HL pattern). {bos_event} detected ({bos_direction})."
            )
        elif structure_label == "bearish":
            direction = SignalDirection.SHORT
            reasoning = (
                f"Bearish market structure: {confirms} confirming points "
                f"(LH+LL pattern). {bos_event} detected ({bos_direction})."
            )
        else:
            direction = SignalDirection.NEUTRAL
            raw_confidence = 0.0
            reasoning = "No clear market structure detected."

        log.info(
            "market_structure_signal",
            direction=direction.value,
            confidence=raw_confidence,
            structure=structure_label,
            bos=bos_event,
        )

        return AgentSignal(
            agent_id=self.agent_id,
            direction=direction,
            confidence=raw_confidence,
            reasoning=reasoning,
            supporting_data={
                "swing_highs": sh_prices[-5:],
                "swing_lows": sl_prices[-5:],
                "structure_label": structure_label,
                "consecutive_confirms": confirms,
                "bos_event": bos_event,
                "bos_direction": bos_direction,
            },
        )
