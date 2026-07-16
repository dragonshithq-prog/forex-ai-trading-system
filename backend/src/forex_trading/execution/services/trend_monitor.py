"""Trend Monitor - multi-timeframe trend detection for automated execution."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

from forex_trading.ai.agents.base import MarketRegime, SignalDirection
from forex_trading.market_data.services.market_data_service import MarketDataService
from forex_trading.strategy.engine import StrategyType

logger = structlog.get_logger()


class TrendStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


@dataclass
class TimeframeTrend:
    timeframe: str
    direction: SignalDirection
    strength: TrendStrength
    ema_alignment: str  # "bullish" | "bearish" | "mixed" | "flat"
    ema_short: float = 0.0
    ema_long: float = 0.0
    adx: float = 0.0
    rsi: float = 50.0
    macd_histogram: float = 0.0
    macd_signal: str = "neutral"  # "bullish_cross" | "bearish_cross" | "neutral"


@dataclass
class TrendSnapshot:
    symbol: str
    dominant_trend: SignalDirection
    confidence: float  # 0.0 - 1.0
    regime: MarketRegime
    timeframe_trends: dict[str, TimeframeTrend] = field(default_factory=dict)
    summary: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_bullish(self) -> bool:
        return self.dominant_trend == SignalDirection.LONG

    @property
    def is_bearish(self) -> bool:
        return self.dominant_trend == SignalDirection.SHORT

    @property
    def actionable(self) -> bool:
        return self.dominant_trend != SignalDirection.NEUTRAL and self.confidence >= 0.3

    def regime_to_strategy_type(self) -> StrategyType:
        mapping = {
            MarketRegime.TRENDING_UP: StrategyType.TREND_FOLLOWING,
            MarketRegime.TRENDING_DOWN: StrategyType.TREND_FOLLOWING,
            MarketRegime.RANGING: StrategyType.MEAN_REVERSION,
            MarketRegime.VOLATILE: StrategyType.BREAKOUT,
            MarketRegime.LOW_VOLATILITY: StrategyType.SCALPING,
        }
        return mapping.get(self.regime, StrategyType.TREND_FOLLOWING)


class TrendMonitor:
    """Monitors multi-timeframe trends using EMA, ADX, RSI, and MACD."""

    TIMEFRAMES = ["M5", "M15", "H1", "H4", "D1"]

    EMA_SHORT = {"M5": 20, "M15": 20, "H1": 20, "H4": 20, "D1": 10}
    EMA_LONG = {"M5": 50, "M15": 50, "H1": 50, "H4": 50, "D1": 30}

    def __init__(self, market_data: MarketDataService) -> None:
        self._market_data = market_data
        self._last_snapshot: dict[str, TrendSnapshot] = {}

    async def analyze(self, symbol: str) -> TrendSnapshot:
        candles_map = await self._market_data.get_multi_timeframe_data(
            symbol, self.TIMEFRAMES, count=100
        )

        tf_trends: dict[str, TimeframeTrend] = {}
        for tf in self.TIMEFRAMES:
            candles = candles_map.get(tf, [])
            if len(candles) < self.EMA_LONG.get(tf, 30) + 5:
                continue
            tf_trends[tf] = self._analyze_timeframe(candles, tf)

        dominant, confidence, regime = self._aggregate_trends(tf_trends)
        summary = self._build_summary(dominant, confidence, tf_trends)

        snapshot = TrendSnapshot(
            symbol=symbol,
            dominant_trend=dominant,
            confidence=confidence,
            regime=regime,
            timeframe_trends=tf_trends,
            summary=summary,
        )
        self._last_snapshot[symbol] = snapshot
        return snapshot

    def get_last_snapshot(self, symbol: str) -> TrendSnapshot | None:
        return self._last_snapshot.get(symbol)

    def _analyze_timeframe(self, candles: list[dict], tf: str) -> TimeframeTrend:
        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]

        short_period = self.EMA_SHORT.get(tf, 20)
        long_period = self.EMA_LONG.get(tf, 50)

        ema_short = self._ema(closes, short_period)
        ema_long = self._ema(closes, long_period)
        ema_alignment = self._classify_ema(ema_short, ema_long)

        adx = self._adx(highs, lows, closes, 14)
        rsi = self._rsi(closes, 14)
        macd_line, signal_line, histogram = self._macd(closes)
        macd_signal = (
            "bullish_cross" if macd_line > signal_line and histogram > 0
            else "bearish_cross" if macd_line < signal_line and histogram < 0
            else "neutral"
        )

        direction, strength = self._classify_direction_strength(
            ema_alignment, adx, rsi, histogram
        )

        return TimeframeTrend(
            timeframe=tf,
            direction=direction,
            strength=strength,
            ema_alignment=ema_alignment,
            ema_short=ema_short[-1] if ema_short else 0,
            ema_long=ema_long[-1] if ema_long else 0,
            adx=adx,
            rsi=rsi,
            macd_histogram=histogram,
            macd_signal=macd_signal,
        )

    def _aggregate_trends(
        self, tf_trends: dict[str, TimeframeTrend]
    ) -> tuple[SignalDirection, float, MarketRegime]:
        if not tf_trends:
            return SignalDirection.NEUTRAL, 0.0, MarketRegime.RANGING

        weights = {"D1": 0.35, "H4": 0.25, "H1": 0.20, "M15": 0.12, "M5": 0.08}
        bullish_score = 0.0
        bearish_score = 0.0
        total_weight = 0.0

        for tf, trend in tf_trends.items():
            w = weights.get(tf, 0.1)
            if trend.direction == SignalDirection.LONG:
                str_mult = {"strong": 1.0, "moderate": 0.65, "weak": 0.3}.get(
                    trend.strength.value, 0
                )
                bullish_score += w * str_mult
            elif trend.direction == SignalDirection.SHORT:
                str_mult = {"strong": 1.0, "moderate": 0.65, "weak": 0.3}.get(
                    trend.strength.value, 0
                )
                bearish_score += w * str_mult
            total_weight += w

        if total_weight == 0:
            return SignalDirection.NEUTRAL, 0.0, MarketRegime.RANGING

        bullish_score /= total_weight
        bearish_score /= total_weight

        if bullish_score > 0.5 and bullish_score > bearish_score:
            confidence = min(bullish_score, 1.0)
            return SignalDirection.LONG, confidence, MarketRegime.TRENDING_UP
        elif bearish_score > 0.5 and bearish_score > bullish_score:
            confidence = min(bearish_score, 1.0)
            return SignalDirection.SHORT, confidence, MarketRegime.TRENDING_DOWN
        else:
            return SignalDirection.NEUTRAL, 0.0, MarketRegime.RANGING

    def _build_summary(
        self,
        dominant: SignalDirection,
        confidence: float,
        tf_trends: dict[str, TimeframeTrend],
    ) -> str:
        parts = [f"dominant={dominant.value}", f"confidence={confidence:.2f}"]
        for tf, t in sorted(tf_trends.items()):
            parts.append(f"{tf}={t.direction.value}/{t.strength.value}")
        return " | ".join(parts)

    def _classify_ema(self, ema_short: list[float], ema_long: list[float]) -> str:
        if not ema_short or not ema_long:
            return "flat"
        s, l = ema_short[-1], ema_long[-1]
        if len(ema_short) >= 2:
            s_prev = ema_short[-2]
            if s > l and s_prev > ema_long[-2] if len(ema_long) >= 2 else s > l:
                return "bullish"
            if s < l and s_prev < ema_long[-2] if len(ema_long) >= 2 else s < l:
                return "bearish"
        return "bullish" if s > l else "bearish" if s < l else "flat"

    def _classify_direction_strength(
        self, ema_alignment: str, adx: float, rsi: float, macd_hist: float
    ) -> tuple[SignalDirection, TrendStrength]:
        if ema_alignment == "bullish" and adx >= 25:
            str_level = "strong" if adx >= 35 and 50 <= rsi <= 80 and macd_hist > 0 else "moderate"
            return SignalDirection.LONG, TrendStrength(str_level)
        if ema_alignment == "bullish" and adx >= 20:
            return SignalDirection.LONG, TrendStrength.WEAK
        if ema_alignment == "bearish" and adx >= 25:
            str_level = "strong" if adx >= 35 and 20 <= rsi <= 50 and macd_hist < 0 else "moderate"
            return SignalDirection.SHORT, TrendStrength(str_level)
        if ema_alignment == "bearish" and adx >= 20:
            return SignalDirection.SHORT, TrendStrength.WEAK
        return SignalDirection.NEUTRAL, TrendStrength.NONE

    def _ema(self, values: list[float], period: int) -> list[float]:
        if len(values) < period:
            return []
        result: list[float] = []
        multiplier = 2.0 / (period + 1)
        sma = sum(values[:period]) / period
        result.append(sma)
        for v in values[period:]:
            result.append((v - result[-1]) * multiplier + result[-1])
        return result

    def _adx(self, highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
        n = len(highs)
        if n < period + 2:
            return 0.0

        tr_values: list[float] = []
        plus_dm: list[float] = []
        minus_dm: list[float] = []

        for i in range(1, n):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            tr_values.append(tr)

            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0.0)
            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0.0)

        if len(tr_values) < period:
            return 0.0

        def _emaraw(vals: list[float], p: int) -> list[float]:
            multiplier = 1.0 / p
            smooth = [sum(vals[:p]) / p]
            for v in vals[p:]:
                smooth.append((v - smooth[-1]) * multiplier + smooth[-1])
            return smooth

        atr = _emaraw(tr_values, period)
        pdi = _emaraw(plus_dm, period)
        nde = _emaraw(minus_dm, period)

        dx_sum = 0.0
        count = 0
        for i in range(len(pdi)):
            if atr[i] != 0:
                pdi_norm = pdi[i] / atr[i] * 100
                nde_norm = nde[i] / atr[i] * 100
                diff = abs(pdi_norm - nde_norm)
                summ = pdi_norm + nde_norm
                if summ != 0:
                    dx_sum += diff / summ * 100
                    count += 1

        return dx_sum / count if count > 0 else 0.0

    def _rsi(self, values: list[float], period: int = 14) -> float:
        n = len(values)
        if n < period + 1:
            return 50.0
        gains = 0.0
        losses = 0.0
        for i in range(n - period, n):
            diff = values[i] - values[i - 1]
            if diff > 0:
                gains += diff
            else:
                losses -= diff
        if losses == 0:
            return 100.0
        rs = gains / losses
        return 100.0 - (100.0 / (1.0 + rs))

    def _macd(self, values: list[float]) -> tuple[float, float, float]:
        if len(values) < 26:
            return 0.0, 0.0, 0.0
        ema12 = self._ema(values, 12)
        ema26 = self._ema(values, 26)
        if not ema12 or not ema26:
            return 0.0, 0.0, 0.0
        macd_line = ema12[-1] - ema26[-1]
        signal = self._ema([ema12[i] - ema26[i] for i in range(len(ema26))], 9)
        signal_val = signal[-1] if signal else 0.0
        histogram = macd_line - signal_val
        return macd_line, signal_val, histogram
