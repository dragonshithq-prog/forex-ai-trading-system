"""Mean Reversion strategy implementation."""

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

_MIN_RR_RATIO = 1.0
_RSI_OVERSOLD = 30.0
_RSI_OVERBOUGHT = 70.0


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion strategy.

    Enters at Bollinger Band extremes within a ranging market, confirmed by
    RSI.  Targets the midpoint (VWAP / middle Bollinger Band) for exit.
    """

    def __init__(self) -> None:
        super().__init__(strategy_type=StrategyType.MEAN_REVERSION, name="Mean Reversion")

    def get_optimal_regime(self) -> list[MarketRegime]:
        return [MarketRegime.RANGING]

    def validate_signal(self, context: MarketContext, signal: TradeSignal) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if signal.entry_price <= 0:
            errors.append("entry_price must be positive")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # Regime must be RANGING
        if context is not None and context.regime != MarketRegime.RANGING:
            errors.append(
                f"Mean reversion requires RANGING regime; current: {context.regime.value}"
            )

        metadata = signal.parameters.metadata

        # Bollinger Band extreme confirmation
        bb_upper = metadata.get("bb_upper")
        bb_lower = metadata.get("bb_lower")
        bb_middle = metadata.get("bb_middle")

        if bb_upper is not None and bb_lower is not None:
            if signal.direction == SignalDirection.LONG:
                if signal.entry_price >= bb_lower:
                    errors.append(
                        f"LONG entry {signal.entry_price} not below BB lower band {bb_lower}; "
                        f"mean reversion requires price at band extreme"
                    )
            elif signal.direction == SignalDirection.SHORT:
                if signal.entry_price <= bb_upper:
                    errors.append(
                        f"SHORT entry {signal.entry_price} not above BB upper band {bb_upper}; "
                        f"mean reversion requires price at band extreme"
                    )
        else:
            warnings.append("Bollinger Band values not provided; skipping band extreme check")

        # RSI confirmation
        rsi = metadata.get("rsi")
        if rsi is not None:
            if signal.direction == SignalDirection.LONG and rsi >= _RSI_OVERSOLD:
                errors.append(
                    f"RSI {rsi:.1f} not below oversold threshold {_RSI_OVERSOLD} for LONG entry"
                )
            elif signal.direction == SignalDirection.SHORT and rsi <= _RSI_OVERBOUGHT:
                errors.append(
                    f"RSI {rsi:.1f} not above overbought threshold {_RSI_OVERBOUGHT} for SHORT entry"
                )
        else:
            warnings.append("RSI not provided; skipping RSI confirmation")

        # R:R ratio check (target = BB middle / VWAP)
        if signal.entry_price > 0 and signal.stop_loss > 0 and signal.take_profit > 0:
            risk = abs(signal.entry_price - signal.stop_loss)
            reward = abs(signal.take_profit - signal.entry_price)
            if risk <= 0:
                errors.append("Stop loss equals entry price; zero risk defined")
            else:
                rr = reward / risk
                if rr < _MIN_RR_RATIO - 1e-9:
                    errors.append(f"R:R ratio {rr:.2f} below minimum {_MIN_RR_RATIO:.1f}")

        # Take profit validation: TP should not exceed the midpoint in a range
        if bb_middle is not None and signal.take_profit > 0:
            if signal.direction == SignalDirection.LONG and signal.take_profit > bb_middle:
                warnings.append(
                    f"TP {signal.take_profit} exceeds BB midpoint {bb_middle}; "
                    f"consider targeting midpoint only"
                )
            elif signal.direction == SignalDirection.SHORT and signal.take_profit < bb_middle:
                warnings.append(
                    f"TP {signal.take_profit} below BB midpoint {bb_middle}; "
                    f"consider targeting midpoint only"
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
        params.stop_loss_pips = 20.0
        params.take_profit_pips = 20.0
        params.max_holding_time_minutes = 120
        return params
