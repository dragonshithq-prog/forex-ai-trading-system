"""Tests for PositionSizer — fixed-fractional sizing and volatility adjustment."""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st
from hypothesis.strategies import floats

from forex_trading.execution.services.position_sizer import PositionSizer, PositionSizeResult


class TestPositionSizer:
    """Tests for the PositionSizer calculator."""

    def setup_method(self):
        self.sizer = PositionSizer()

    def test_calculate_size_basic(self):
        """Basic position size calculation should return correct values."""
        result = self.sizer.calculate_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            entry_price=1.1000,
            stop_loss_price=1.0950,
            symbol="EURUSD",
        )
        assert result.lots > 0
        assert result.units > 0
        assert result.risk_amount > 0
        assert result.risk_pct > 0
        assert result.pip_value > 0

    def test_calculate_size_risk_amount(self):
        """Risk amount should be approximately 1% of account balance."""
        result = self.sizer.calculate_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            entry_price=1.1000,
            stop_loss_price=1.0950,
            symbol="EURUSD",
        )
        # SL distance = 50 pips, pip value = $10
        # risk = 10000 * 0.01 = $100
        # lots = 100 / (50 * 10) = 0.2
        assert result.lots == pytest.approx(0.2, abs=0.01)
        assert result.risk_amount == pytest.approx(100.0, abs=5.0)
        assert result.risk_pct == pytest.approx(1.0, abs=0.1)

    def test_calculate_size_minimum_lots(self):
        """Very small risk should result in minimum lot size."""
        result = self.sizer.calculate_size(
            account_balance=100.0,
            risk_pct=1.0,
            entry_price=1.1000,
            stop_loss_price=1.0950,
            symbol="EURUSD",
        )
        assert result.lots >= 0.01

    def test_calculate_size_leverage_cap(self):
        """Position size should be capped by leverage."""
        result = self.sizer.calculate_size(
            account_balance=1_000.0,
            risk_pct=50.0,  # High risk
            entry_price=1.1000,
            stop_loss_price=1.0900,  # Wide SL
            symbol="EURUSD",
            leverage=10,
        )
        # Notional value should not exceed balance * leverage = $10,000
        max_notional = 1_000.0 * 10
        position_notional = result.units * 1.1000
        assert position_notional <= max_notional * 1.1  # Allow slight rounding

    def test_calculate_size_zero_balance_raises(self):
        """Zero account balance should raise ValueError."""
        with pytest.raises(ValueError, match="account_balance must be positive"):
            self.sizer.calculate_size(
                account_balance=0,
                risk_pct=1.0,
                entry_price=1.1000,
                stop_loss_price=1.0950,
                symbol="EURUSD",
            )

    def test_calculate_size_invalid_risk_pct_raises(self):
        """Invalid risk percentage should raise ValueError."""
        with pytest.raises(ValueError, match="risk_pct must be in"):
            self.sizer.calculate_size(
                account_balance=10_000.0,
                risk_pct=0,
                entry_price=1.1000,
                stop_loss_price=1.0950,
                symbol="EURUSD",
            )
        with pytest.raises(ValueError, match="risk_pct must be in"):
            self.sizer.calculate_size(
                account_balance=10_000.0,
                risk_pct=101,
                entry_price=1.1000,
                stop_loss_price=1.0950,
                symbol="EURUSD",
            )

    def test_calculate_size_entry_equals_sl_raises(self):
        """When entry equals stop loss, should raise ValueError."""
        with pytest.raises(ValueError, match="entry_price and stop_loss_price must differ"):
            self.sizer.calculate_size(
                account_balance=10_000.0,
                risk_pct=1.0,
                entry_price=1.1000,
                stop_loss_price=1.1000,
                symbol="EURUSD",
            )

    @given(
        balance=floats(min_value=1000, max_value=1_000_000, allow_nan=False, allow_infinity=False),
        risk_pct=floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
        entry=floats(min_value=0.5, max_value=200.0, allow_nan=False, allow_infinity=False),
        sl_distance=floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    def test_calculate_size_property_bounds(self, balance, risk_pct, entry, sl_distance):
        """Position size should always be positive and risk within expected range."""
        sl = entry - sl_distance if entry > sl_distance else entry + sl_distance
        # Ensure SL is positive
        sl = max(sl, 0.0001)
        try:
            result = self.sizer.calculate_size(
                account_balance=balance,
                risk_pct=risk_pct,
                entry_price=entry,
                stop_loss_price=sl,
                symbol="EURUSD",
            )
        except ValueError:
            return  # Expected for edge cases
        assert result.lots >= 0.01
        assert result.units > 0
        assert result.risk_amount > 0
        assert result.pip_value > 0

    def test_jpy_pair_sizing(self):
        """JPY pairs should calculate correctly."""
        result = self.sizer.calculate_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            entry_price=110.00,
            stop_loss_price=109.50,
            symbol="USDJPY",
        )
        assert result.lots > 0
        assert result.pip_value > 0

    def test_unknown_pair_sizing(self):
        """Unknown pairs should use sensible defaults."""
        result = self.sizer.calculate_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            entry_price=1.1000,
            stop_loss_price=1.0950,
            symbol="XAUUSD",
        )
        assert result.lots > 0


class TestPositionSizerVolatilityAdjustment:
    """Tests for volatility-adjusted position sizing."""

    def setup_method(self):
        self.sizer = PositionSizer()

    def test_no_adjustment_when_volatility_normal(self):
        """When volatility ratio is <= 1.0, size should not change."""
        adjusted = self.sizer.risk_adjusted_size(
            base_size=1.0,
            volatility_ratio=1.0,
        )
        assert adjusted == 1.0

        adjusted = self.sizer.risk_adjusted_size(
            base_size=1.0,
            volatility_ratio=0.5,
        )
        assert adjusted == 1.0

    def test_reduces_size_when_volatility_elevated(self):
        """Elevated volatility should reduce position size."""
        adjusted = self.sizer.risk_adjusted_size(
            base_size=1.0,
            volatility_ratio=2.0,  # 2x normal volatility
        )
        # Should be 0.5 (base / ratio)
        assert adjusted == 0.5

    def test_respects_max_reduction_floor(self):
        """Position size should not go below the max reduction floor."""
        adjusted = self.sizer.risk_adjusted_size(
            base_size=1.0,
            volatility_ratio=10.0,  # Extreme volatility
            max_reduction_pct=50.0,  # Floor at 50% of base = 0.5
        )
        # base / 10 = 0.1, but floor is 0.5
        assert adjusted == 0.5

    def test_volatility_adjustment_minimum_lot(self):
        """Volatility adjustment should never go below 0.01 lots."""
        adjusted = self.sizer.risk_adjusted_size(
            base_size=0.02,
            volatility_ratio=5.0,
            max_reduction_pct=90.0,
        )
        assert adjusted >= 0.01

    def test_invalid_base_size_raises(self):
        with pytest.raises(ValueError):
            self.sizer.risk_adjusted_size(base_size=0, volatility_ratio=1.0)

    def test_invalid_volatility_ratio_raises(self):
        with pytest.raises(ValueError):
            self.sizer.risk_adjusted_size(base_size=1.0, volatility_ratio=0)

    def test_invalid_max_reduction_raises(self):
        with pytest.raises(ValueError):
            self.sizer.risk_adjusted_size(base_size=1.0, volatility_ratio=1.0, max_reduction_pct=101)

    @given(
        base=floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
        vr=floats(min_value=0.1, max_value=20.0, allow_nan=False, allow_infinity=False),
    )
    def test_volatility_adjustment_property_bounds(self, base, vr):
        """Adjusted size should always be >= 0.01 and <= base."""
        try:
            adjusted = self.sizer.risk_adjusted_size(base_size=base, volatility_ratio=vr)
        except ValueError:
            return
        assert 0.01 <= adjusted <= base


class TestPositionSizerPipValue:
    """Tests for pip value calculation."""

    def setup_method(self):
        self.sizer = PositionSizer()

    def test_usd_quoted_pairs(self):
        """USD-quoted pairs should have $10 pip value per lot."""
        for symbol in ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]:
            pv = self.sizer.calculate_pip_value(symbol, lot_size=1.0)
            assert pv == 10.0

    def test_jpy_pairs(self):
        """JPY pairs should have a pip value around $9-10."""
        pv = self.sizer.calculate_pip_value("USDJPY", lot_size=1.0)
        assert pv == pytest.approx(9.09, rel=0.1)

    def test_custom_lot_size(self):
        """Pip value should scale with lot size."""
        pv_1 = self.sizer.calculate_pip_value("EURUSD", lot_size=1.0)
        pv_2 = self.sizer.calculate_pip_value("EURUSD", lot_size=2.0)
        assert pv_2 == pv_1 * 2

    def test_invalid_lot_size_raises(self):
        with pytest.raises(ValueError):
            self.sizer.calculate_pip_value("EURUSD", lot_size=0)
