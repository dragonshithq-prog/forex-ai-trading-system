"""Pullback strategy implementation."""

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

_MIN_RR_RATIO = 1.5
_RSI_OVERBOUGHT = 70.0
_RSI_OVERSOLD = 30.0
_PULLBACK_PROXIMITY_PIPS = 10.0


class PullbackStrategy(BaseStrategy):
    """
    Pullback strategy.

    Enters on a retracement to EMA20 or EMA50 in a trending market,
    confirming the entry is not at an overbought/oversold RSI extreme.
    """

    def __init__(self) -> None:
        super().__init__(strategy_type=StrategyType.PULLBACK, name="Pullback")

    def get_optimal_regime(self) -> list[MarketRegime]:
        return [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]

    def validate_signal(self, context: MarketContext, signal: TradeSignal) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if signal.entry_price <= 0:
            errors.append("entry_price must be positive")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        metadata = signal.parameters.metadata

        # Pullback to EMA20 or EMA50
        ema20 = metadata.get("ema20")
        ema50 = metadata.get("ema50")

        if ema20 is not None or ema50 is not None:
            near_ema20 = (
                ema20 is not None
                and abs(signal.entry_price - ema20) / 0.0001 <= _PULLBACK_PROXIMITY_PIPS
            )
            near_ema50 = (
                ema50 is not None
                and abs(signal.entry_price - ema50) / 0.0001 <= _PULLBACK_PROXIMITY_PIPS
            )
            if not (near_ema20 or near_ema50):
                errors.append(
                    f"Entry not near EMA20 ({ema20}) or EMA50 ({ema50}); "
                    f"pullback threshold is {_PULLBACK_PROXIMITY_PIPS} pips"
                )
        else:
            warnings.append("EMA values not provided; skipping pullback proximity check")

        # Ensure market is actually trending (EMA200 alignment)
        ema200 = metadata.get("ema200")
        if ema20 is not None and ema50 is not None and ema200 is not None:
            if signal.direction == SignalDirection.LONG and not (ema20 > ema50 > ema200):
                errors.append("Market not in uptrend for LONG pullback entry")
            elif signal.direction == SignalDirection.SHORT and not (ema20 < ema50 < ema200):
                errors.append("Market not in downtrend for SHORT pullback entry")
        else:
            warnings.append("Full EMA stack not provided; skipping trend verification")

        # RSI not overbought/oversold at entry
        rsi = metadata.get("rsi")
        if rsi is not None:
            if signal.direction == SignalDirection.LONG and rsi > _RSI_OVERBOUGHT:
                errors.append(
                    f"RSI overbought ({rsi:.1f} > {_RSI_OVERBOUGHT}) on LONG pullback entry"
                )
            elif signal.direction == SignalDirection.SHORT and rsi < _RSI_OVERSOLD:
                errors.append(
                    f"RSI oversold ({rsi:.1f} < {_RSI_OVERSOLD}) on SHORT pullback entry"
                )
        else:
            warnings.append("RSI not provided; skipping overbought/oversold check")

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
        params.stop_loss_pips = 40.0
        params.take_profit_pips = 60.0
        return params
