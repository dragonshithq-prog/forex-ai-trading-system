"""Scalping strategy implementation."""

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

_MAX_SPREAD_PIPS = 1.5
_SL_ATR_MULTIPLIER = 0.5
_TP_ATR_MULTIPLIER = 1.0

# London/NY overlap: 12:00-17:00 UTC (London 08:00-17:00 intersects NY 13:00-22:00)
# Widened to 12:00-17:00 UTC to cover the full overlap window
_OVERLAP_START_UTC_HOUR = 12
_OVERLAP_END_UTC_HOUR = 17


class ScalpingStrategy(BaseStrategy):
    """
    Scalping strategy.

    Very tight SL/TP (ATR*0.5 / ATR*1.0), active only during the London/NY
    session overlap, with spread < 1.5 pips.  Uses order flow imbalance
    (bid/ask volume delta) as entry confirmation.
    """

    def __init__(self) -> None:
        super().__init__(strategy_type=StrategyType.SCALPING, name="Scalping")

    def get_optimal_regime(self) -> list[MarketRegime]:
        return [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN, MarketRegime.RANGING]

    def validate_signal(self, context: MarketContext, signal: TradeSignal) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if signal.entry_price <= 0:
            errors.append("entry_price must be positive")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        metadata = signal.parameters.metadata

        # Session check: London/NY overlap
        utc_hour = metadata.get("utc_hour")
        if utc_hour is not None:
            if not (_OVERLAP_START_UTC_HOUR <= int(utc_hour) < _OVERLAP_END_UTC_HOUR):
                errors.append(
                    f"Scalping only active during London/NY overlap "
                    f"({_OVERLAP_START_UTC_HOUR}:00-{_OVERLAP_END_UTC_HOUR}:00 UTC); "
                    f"current hour: {utc_hour}"
                )
        elif context is not None and context.session_info is not None:
            session = getattr(context.session_info, "name", "")
            if "london" not in str(session).lower() and "new_york" not in str(session).lower():
                errors.append(
                    f"Scalping only active during London or New York sessions; current: {session}"
                )
        else:
            warnings.append("Session info not provided; skipping session check")

        # Spread check
        current_spread = metadata.get("current_spread_pips")
        if current_spread is not None:
            if current_spread > _MAX_SPREAD_PIPS:
                errors.append(
                    f"Spread {current_spread:.2f} pips exceeds scalping maximum {_MAX_SPREAD_PIPS} pips"
                )
        else:
            warnings.append("current_spread_pips not provided; skipping spread check")

        # Order flow imbalance (bid/ask volume delta)
        bid_volume = metadata.get("bid_volume")
        ask_volume = metadata.get("ask_volume")

        if bid_volume is not None and ask_volume is not None:
            total = bid_volume + ask_volume
            if total <= 0:
                warnings.append("Total tick volume is zero; skipping order flow check")
            else:
                imbalance = (bid_volume - ask_volume) / total
                if signal.direction == SignalDirection.LONG and imbalance <= 0:
                    errors.append(
                        f"Order flow imbalance ({imbalance:.2f}) does not support LONG entry; "
                        f"need buy pressure (imbalance > 0)"
                    )
                elif signal.direction == SignalDirection.SHORT and imbalance >= 0:
                    errors.append(
                        f"Order flow imbalance ({imbalance:.2f}) does not support SHORT entry; "
                        f"need sell pressure (imbalance < 0)"
                    )
        else:
            warnings.append("Tick volume data not provided; skipping order flow check")

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
        params.stop_loss_pips = (atr * _SL_ATR_MULTIPLIER) / 0.0001
        params.take_profit_pips = (atr * _TP_ATR_MULTIPLIER) / 0.0001
        params.max_holding_time_minutes = 30
        return params
