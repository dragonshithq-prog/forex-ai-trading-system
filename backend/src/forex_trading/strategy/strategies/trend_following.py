"""Trend Following strategy implementation."""

import structlog

from forex_trading.ai.agents.base import MarketContext, MarketRegime, SignalDirection
from forex_trading.strategy.engine import (
    BaseStrategy,
    StrategyParameters,
    StrategyType,
    TradeSignal,
    ValidationResult,
)

logger = structlog.get_logger()

_DEFAULT_SL_ATR_MULTIPLIER = 1.5
_DEFAULT_TP_ATR_MULTIPLIER = 3.0
_MIN_RR_RATIO = 2.0
_MIN_ADX = 20.0


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend Following strategy.

    Enters in the direction of the dominant trend, confirmed by EMA alignment,
    ADX strength, and favourable risk-reward.
    """

    def __init__(self) -> None:
        super().__init__(strategy_type=StrategyType.TREND_FOLLOWING, name="Trend Following")

    def get_optimal_regime(self) -> list[MarketRegime]:
        return [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]

    def validate_signal(self, context: MarketContext, signal: TradeSignal) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if signal.entry_price <= 0:
            errors.append("entry_price must be positive")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        metadata = signal.parameters.metadata

        # EMA alignment check
        ema20 = metadata.get("ema20")
        ema50 = metadata.get("ema50")
        ema200 = metadata.get("ema200")

        if ema20 is not None and ema50 is not None and ema200 is not None:
            if signal.direction == SignalDirection.LONG:
                if not (ema20 > ema50 > ema200):
                    errors.append(
                        f"EMA alignment invalid for LONG: ema20={ema20} ema50={ema50} ema200={ema200}"
                    )
            elif signal.direction == SignalDirection.SHORT:
                if not (ema20 < ema50 < ema200):
                    errors.append(
                        f"EMA alignment invalid for SHORT: ema20={ema20} ema50={ema50} ema200={ema200}"
                    )
        else:
            warnings.append("EMA values not provided; skipping EMA alignment check")

        # ADX check
        adx = metadata.get("adx")
        if adx is not None:
            if adx < _MIN_ADX:
                errors.append(f"ADX too low for trend trade: {adx:.1f} < {_MIN_ADX}")
        else:
            warnings.append("ADX not provided; skipping trend strength check")

        # Signal direction vs regime
        if context is not None:
            if context.regime == MarketRegime.TRENDING_UP and signal.direction == SignalDirection.SHORT:
                errors.append("Signal direction SHORT conflicts with TRENDING_UP regime")
            elif context.regime == MarketRegime.TRENDING_DOWN and signal.direction == SignalDirection.LONG:
                errors.append("Signal direction LONG conflicts with TRENDING_DOWN regime")

        # R:R ratio check
        if signal.entry_price > 0 and signal.stop_loss > 0 and signal.take_profit > 0:
            risk = abs(signal.entry_price - signal.stop_loss)
            reward = abs(signal.take_profit - signal.entry_price)
            if risk <= 0:
                errors.append("Stop loss equals entry price; zero risk defined")
            else:
                rr = reward / risk
                if rr < _MIN_RR_RATIO - 1e-9:
                    errors.append(f"R:R ratio {rr:.2f} below minimum {_MIN_RR_RATIO:.1f}")

        # Major resistance check (entry should not be within 5 pips of resistance)
        resistance = metadata.get("major_resistance")
        if resistance is not None and signal.entry_price > 0:
            distance_pips = abs(resistance - signal.entry_price) / 0.0001
            if distance_pips < 5.0:
                errors.append(
                    f"Entry too close to major resistance: {distance_pips:.1f} pips away"
                )

        log = logger.bind(
            strategy=self.name,
            symbol=getattr(signal, "symbol", ""),
            direction=signal.direction.value,
            valid=len(errors) == 0,
        )
        if errors:
            log.warning("signal_validation_failed", errors=errors)
        else:
            log.debug("signal_validated")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def get_parameters(self, symbol: str) -> StrategyParameters:
        params = super().get_parameters(symbol)
        atr = params.metadata.get("atr", 0.001)
        sl_pips = (atr * _DEFAULT_SL_ATR_MULTIPLIER) / 0.0001
        tp_pips = (atr * _DEFAULT_TP_ATR_MULTIPLIER) / 0.0001
        params.stop_loss_pips = sl_pips
        params.take_profit_pips = tp_pips
        return params
