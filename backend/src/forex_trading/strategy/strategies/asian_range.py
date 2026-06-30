"""Asian Range strategy implementation."""

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

# Tokyo session hours UTC: 00:00-07:00
_TOKYO_START_UTC_HOUR = 0
_TOKYO_END_UTC_HOUR = 7

_PROXIMITY_PIPS = 10.0  # within 10 pips of range boundary to be valid entry


class AsianRangeStrategy(BaseStrategy):
    """
    Asian Range (Tokyo session) mean-reversion strategy.

    Buys at the lower bound of the Tokyo session range, sells at the upper
    bound.  Exit at the opposite bound or the midpoint.  Only valid while
    Tokyo session is active.
    """

    def __init__(self) -> None:
        super().__init__(strategy_type=StrategyType.ASIAN_RANGE, name="Asian Range")

    def get_optimal_regime(self) -> list[MarketRegime]:
        return [MarketRegime.RANGING, MarketRegime.LOW_VOLATILITY]

    def validate_signal(self, context: MarketContext, signal: TradeSignal) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if signal.entry_price <= 0:
            errors.append("entry_price must be positive")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        metadata = signal.parameters.metadata

        # Tokyo session time check
        utc_hour = metadata.get("utc_hour")
        if utc_hour is not None:
            hour = int(utc_hour)
            in_tokyo = _TOKYO_START_UTC_HOUR <= hour < _TOKYO_END_UTC_HOUR
            if not in_tokyo:
                errors.append(
                    f"Asian Range strategy only active during Tokyo session "
                    f"({_TOKYO_START_UTC_HOUR}:00-{_TOKYO_END_UTC_HOUR}:00 UTC); "
                    f"current hour: {hour}"
                )
        else:
            warnings.append("utc_hour not provided; skipping Tokyo session check")

        # Range bounds
        range_high = metadata.get("range_high")
        range_low = metadata.get("range_low")

        if range_high is None or range_low is None:
            warnings.append("range_high / range_low not provided; skipping range bound check")
        else:
            if range_high <= range_low:
                errors.append(
                    f"Invalid range: high {range_high} <= low {range_low}"
                )
            else:
                # LONG: entry should be near range low; SHORT: near range high
                if signal.direction == SignalDirection.LONG:
                    distance_pips = (signal.entry_price - range_low) / 0.0001
                    if distance_pips > _PROXIMITY_PIPS:
                        errors.append(
                            f"LONG entry {signal.entry_price} not near range low {range_low}; "
                            f"distance {distance_pips:.1f} pips > threshold {_PROXIMITY_PIPS}"
                        )
                    # TP should target range high (opposite bound) or midpoint
                    if signal.take_profit > 0 and signal.take_profit > range_high:
                        warnings.append(
                            f"TP {signal.take_profit} exceeds range high {range_high}; "
                            f"target should be opposite bound or midpoint"
                        )
                elif signal.direction == SignalDirection.SHORT:
                    distance_pips = (range_high - signal.entry_price) / 0.0001
                    if distance_pips > _PROXIMITY_PIPS:
                        errors.append(
                            f"SHORT entry {signal.entry_price} not near range high {range_high}; "
                            f"distance {distance_pips:.1f} pips > threshold {_PROXIMITY_PIPS}"
                        )
                    if signal.take_profit > 0 and signal.take_profit < range_low:
                        warnings.append(
                            f"TP {signal.take_profit} below range low {range_low}; "
                            f"target should be opposite bound or midpoint"
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
        params.stop_loss_pips = 15.0
        params.take_profit_pips = 30.0
        params.max_holding_time_minutes = 240
        return params
