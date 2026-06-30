"""London Open breakout strategy implementation."""

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

# Active window: 07:00-09:00 UTC
_ACTIVE_START_UTC_HOUR = 7
_ACTIVE_END_UTC_HOUR = 9

# Asian session range: 00:00-07:00 UTC
_TP_RANGE_MULTIPLIER = 1.5


class LondonOpenStrategy(BaseStrategy):
    """
    London Open breakout strategy.

    Active 07:00-09:00 UTC.  Uses the Asian session high/low as the reference
    range.  Goes long on Asian high breakout, short on Asian low breakout.
    TP is set at 1.5x the Asian range size.
    """

    def __init__(self) -> None:
        super().__init__(strategy_type=StrategyType.LONDON_OPEN, name="London Open")

    def get_optimal_regime(self) -> list[MarketRegime]:
        return [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN, MarketRegime.VOLATILE]

    def validate_signal(self, context: MarketContext, signal: TradeSignal) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if signal.entry_price <= 0:
            errors.append("entry_price must be positive")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        metadata = signal.parameters.metadata

        # Time window check
        utc_hour = metadata.get("utc_hour")
        if utc_hour is not None:
            hour = int(utc_hour)
            if not (_ACTIVE_START_UTC_HOUR <= hour < _ACTIVE_END_UTC_HOUR):
                errors.append(
                    f"London Open strategy only active {_ACTIVE_START_UTC_HOUR:02d}:00-"
                    f"{_ACTIVE_END_UTC_HOUR:02d}:00 UTC; current hour: {hour}"
                )
        else:
            warnings.append("utc_hour not provided; skipping time window check")

        # Asian range reference
        asian_high = metadata.get("asian_high")
        asian_low = metadata.get("asian_low")

        if asian_high is None or asian_low is None:
            warnings.append("Asian session range not provided; skipping range validation")
        else:
            if asian_high <= asian_low:
                errors.append(
                    f"Invalid Asian range: high {asian_high} <= low {asian_low}"
                )
            else:
                asian_range = asian_high - asian_low

                if signal.direction == SignalDirection.LONG:
                    if signal.entry_price < asian_high:
                        errors.append(
                            f"LONG entry {signal.entry_price} has not broken above "
                            f"Asian high {asian_high}"
                        )
                elif signal.direction == SignalDirection.SHORT:
                    if signal.entry_price > asian_low:
                        errors.append(
                            f"SHORT entry {signal.entry_price} has not broken below "
                            f"Asian low {asian_low}"
                        )

                # Validate TP is approximately 1.5x Asian range from breakout level
                if signal.take_profit > 0:
                    expected_tp_distance = asian_range * _TP_RANGE_MULTIPLIER
                    if signal.direction == SignalDirection.LONG:
                        actual_tp_distance = signal.take_profit - asian_high
                    else:
                        actual_tp_distance = asian_low - signal.take_profit

                    tolerance = asian_range * 0.5  # 50% tolerance on TP placement
                    if actual_tp_distance < expected_tp_distance - tolerance:
                        warnings.append(
                            f"TP distance {actual_tp_distance:.5f} is shorter than expected "
                            f"{expected_tp_distance:.5f} (1.5x Asian range)"
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
        params.stop_loss_pips = 25.0
        params.take_profit_pips = 50.0
        params.max_holding_time_minutes = 120
        return params
