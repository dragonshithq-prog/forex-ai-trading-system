"""Position Sizer - institutional fixed-fractional position sizing with ATR adjustment."""

from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

# Pip sizes per symbol (fractional price move per pip)
_PIP_SIZE: dict[str, float] = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "AUDUSD": 0.0001,
    "NZDUSD": 0.0001,
    "USDCHF": 0.0001,
    "USDCAD": 0.0001,
    "USDJPY": 0.01,
    "EURJPY": 0.01,
    "GBPJPY": 0.01,
    "AUDJPY": 0.01,
    "CHFJPY": 0.01,
    "CADJPY": 0.01,
    "NZDJPY": 0.01,
}

# Pip value per standard lot in USD for USD-quoted pairs
_PIP_VALUE_PER_LOT_USD: dict[str, float] = {
    "EURUSD": 10.0,
    "GBPUSD": 10.0,
    "AUDUSD": 10.0,
    "NZDUSD": 10.0,
    # Cross-pairs below use dynamic calculation via calculate_pip_value
}


@dataclass
class PositionSizeResult:
    lots: float
    units: float
    risk_amount: float
    risk_pct: float
    pip_value: float
    max_loss_amount: float
    r_r_ratio: float


class PositionSizer:
    """
    Institutional position sizing using the Fixed Fractional method
    with optional ATR-based volatility adjustment.
    """

    def calculate_size(
        self,
        account_balance: float,
        risk_pct: float,
        entry_price: float,
        stop_loss_price: float,
        symbol: str,
        contract_size: float = 100_000.0,
        leverage: int = 100,
    ) -> PositionSizeResult:
        if account_balance <= 0:
            raise ValueError(f"account_balance must be positive; got {account_balance}")
        if risk_pct <= 0 or risk_pct > 100:
            raise ValueError(f"risk_pct must be in (0, 100]; got {risk_pct}")
        if entry_price <= 0:
            raise ValueError(f"entry_price must be positive; got {entry_price}")
        if stop_loss_price <= 0:
            raise ValueError(f"stop_loss_price must be positive; got {stop_loss_price}")
        if entry_price == stop_loss_price:
            raise ValueError("entry_price and stop_loss_price must differ")

        pip_size = self._get_pip_size(symbol)
        sl_distance_pips = abs(entry_price - stop_loss_price) / pip_size

        if sl_distance_pips <= 0:
            raise ValueError(
                f"Calculated SL distance is zero for {symbol} "
                f"(entry={entry_price}, sl={stop_loss_price})"
            )

        risk_amount = account_balance * (risk_pct / 100.0)
        pip_value = self.calculate_pip_value(symbol, lot_size=1.0)

        if pip_value <= 0:
            raise ValueError(f"Cannot calculate pip value for {symbol}")

        raw_lots = risk_amount / (sl_distance_pips * pip_value)
        lots = round(raw_lots, 2)

        if lots <= 0:
            lots = 0.01  # minimum tradeable lot

        units = lots * contract_size
        actual_risk = sl_distance_pips * pip_value * lots
        actual_risk_pct = (actual_risk / account_balance) * 100.0

        # Leverage ceiling: position notional must not exceed account_balance * leverage
        max_notional = account_balance * leverage
        position_notional = units * entry_price
        if position_notional > max_notional:
            lots = round(max_notional / (entry_price * contract_size), 2)
            lots = max(lots, 0.01)
            units = lots * contract_size
            actual_risk = sl_distance_pips * pip_value * lots
            actual_risk_pct = (actual_risk / account_balance) * 100.0
            logger.warning(
                "position_size_reduced_by_leverage",
                symbol=symbol,
                leverage=leverage,
                adjusted_lots=lots,
            )

        logger.debug(
            "position_size_calculated",
            symbol=symbol,
            lots=lots,
            sl_pips=sl_distance_pips,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
        )

        return PositionSizeResult(
            lots=lots,
            units=units,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            pip_value=pip_value,
            max_loss_amount=actual_risk,
            r_r_ratio=0.0,  # caller sets after determining take-profit
        )

    def calculate_pip_value(
        self,
        symbol: str,
        lot_size: float,
        account_currency: str = "USD",
    ) -> float:
        if lot_size <= 0:
            raise ValueError(f"lot_size must be positive; got {lot_size}")

        symbol_upper = symbol.upper()

        # USD-quoted pairs: pip_value = 0.0001 * contract_size = $10 per std lot
        if symbol_upper in _PIP_VALUE_PER_LOT_USD:
            return _PIP_VALUE_PER_LOT_USD[symbol_upper] * lot_size

        # JPY-quoted pairs: pip_value ≈ (pip_size * contract_size) / price
        # We cannot know current price here without a price feed; callers should
        # prefer passing pip_value explicitly.  We approximate using a reference
        # rate embedded in metadata or default to ~$9 for USDJPY at ~110.
        if symbol_upper.endswith("JPY"):
            # 0.01 pip * 100_000 units = 1000 yen / price in yen/USD
            # At a typical rate of 110, that's ~$9.09
            pip_size = 0.01
            contract_size = 100_000.0
            approximate_price = 110.0  # fallback — callers should supply price in metadata
            per_lot = (pip_size * contract_size) / approximate_price
            return per_lot * lot_size

        # Generic XXX/YYY: pip_value = (pip_size * contract_size) / approx_quote_to_account_rate
        # Default to standard-lot $10 equivalent for unlisted pairs as a safe approximation
        logger.warning(
            "pip_value_approximated",
            symbol=symbol,
            reason="symbol not in known pip value table",
        )
        return 10.0 * lot_size

    def risk_adjusted_size(
        self,
        base_size: float,
        volatility_ratio: float,
        max_reduction_pct: float = 50.0,
    ) -> float:
        """
        Reduce lot size proportionally when current volatility exceeds historical average.

        Args:
            base_size: Baseline lot size from calculate_size.
            volatility_ratio: current_ATR / historical_average_ATR.  >1 means elevated volatility.
            max_reduction_pct: Floor expressed as a percentage of base_size (0-100).

        Returns:
            Adjusted lot size, never below (1 - max_reduction_pct/100) * base_size.
        """
        if base_size <= 0:
            raise ValueError(f"base_size must be positive; got {base_size}")
        if volatility_ratio <= 0:
            raise ValueError(f"volatility_ratio must be positive; got {volatility_ratio}")
        if not (0.0 <= max_reduction_pct <= 100.0):
            raise ValueError(f"max_reduction_pct must be in [0, 100]; got {max_reduction_pct}")

        if volatility_ratio <= 1.0:
            return base_size  # normal or below-normal volatility — no reduction

        # Scale down inversely with volatility; a ratio of 2.0 → 50% reduction
        adjusted = base_size / volatility_ratio
        floor = base_size * (1.0 - max_reduction_pct / 100.0)
        result = max(adjusted, floor)
        result = round(result, 2)
        result = max(result, 0.01)

        logger.debug(
            "position_size_volatility_adjusted",
            base_size=base_size,
            volatility_ratio=volatility_ratio,
            adjusted_size=result,
        )
        return result

    def _get_pip_size(self, symbol: str) -> float:
        symbol_upper = symbol.upper()
        if symbol_upper in _PIP_SIZE:
            return _PIP_SIZE[symbol_upper]
        if symbol_upper.endswith("JPY"):
            return 0.01
        return 0.0001
