"""Breakout strategy implementation."""

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

_MAX_SPREAD_MULTIPLIER = 2.0
_VOLUME_LOOKBACK = 20  # periods for average volume
_RETEST_PROXIMITY_PIPS = 5.0


class BreakoutStrategy(BaseStrategy):
    """
    Breakout strategy.

    Enters on confirmed breakouts above key resistance or below key support,
    requiring above-average volume and manageable spread.  Accepts both direct
    breakout entries and pullback-retest entries.
    """

    def __init__(self) -> None:
        super().__init__(strategy_type=StrategyType.BREAKOUT, name="Breakout")

    def get_optimal_regime(self) -> list[MarketRegime]:
        return [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN, MarketRegime.VOLATILE]

    def validate_signal(self, context: MarketContext, signal: TradeSignal) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if signal.entry_price <= 0:
            errors.append("entry_price must be positive")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        metadata = signal.parameters.metadata

        # Breakout level verification
        resistance = metadata.get("resistance_level")
        support_level = metadata.get("support_level")
        broken_level: float | None = None

        if signal.direction == SignalDirection.LONG:
            if resistance is None:
                warnings.append("resistance_level not provided; cannot verify breakout above resistance")
            elif signal.entry_price < resistance:
                errors.append(
                    f"Entry {signal.entry_price} has not broken above resistance {resistance}"
                )
            else:
                broken_level = resistance
        elif signal.direction == SignalDirection.SHORT:
            if support_level is None:
                warnings.append("support_level not provided; cannot verify breakout below support")
            elif signal.entry_price > support_level:
                errors.append(
                    f"Entry {signal.entry_price} has not broken below support {support_level}"
                )
            else:
                broken_level = support_level

        # Volume confirmation
        current_volume = metadata.get("current_volume")
        avg_volume = metadata.get("avg_volume_20")

        if current_volume is not None and avg_volume is not None:
            if avg_volume <= 0:
                warnings.append("avg_volume_20 is zero or negative; skipping volume check")
            elif current_volume <= avg_volume:
                errors.append(
                    f"Breakout volume {current_volume:.0f} not above {_VOLUME_LOOKBACK}-period "
                    f"average {avg_volume:.0f}"
                )
        else:
            warnings.append("Volume data not provided; skipping volume confirmation")

        # Spread check
        current_spread = metadata.get("current_spread_pips")
        avg_spread = metadata.get("avg_spread_pips")

        if current_spread is not None and avg_spread is not None:
            if avg_spread > 0 and current_spread > avg_spread * _MAX_SPREAD_MULTIPLIER:
                errors.append(
                    f"Spread {current_spread:.1f} pips exceeds {_MAX_SPREAD_MULTIPLIER}x "
                    f"average {avg_spread:.1f} pips"
                )
        else:
            warnings.append("Spread data not provided; skipping spread check")

        # Breakout confirmation: direct breakout or pullback retest
        confirmation_type = metadata.get("confirmation_type")  # "direct" | "retest"
        if confirmation_type is None:
            warnings.append("confirmation_type not provided; assuming direct breakout")
        elif confirmation_type == "retest" and broken_level is not None:
            retest_distance = abs(signal.entry_price - broken_level) / 0.0001
            if retest_distance > _RETEST_PROXIMITY_PIPS:
                errors.append(
                    f"Retest entry too far from broken level: "
                    f"{retest_distance:.1f} pips (max {_RETEST_PROXIMITY_PIPS})"
                )
        elif confirmation_type not in ("direct", "retest"):
            errors.append(f"Unknown confirmation_type: {confirmation_type}")

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
        params.stop_loss_pips = 30.0
        params.take_profit_pips = 90.0
        return params
