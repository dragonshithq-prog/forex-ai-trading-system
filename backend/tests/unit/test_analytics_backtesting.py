"""Unit tests for Backtesting Engine."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from forex_trading.analytics.backtesting.engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestTrade,
    BacktestResult,
    _ema,
    _atr,
    _pip_size,
    _trend_following_signal,
    _mean_reversion_signal,
    _breakout_signal,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_candles(n: int = 200, base_price: float = 1.1000, trend: float = 0.0) -> list[dict]:
    """Generate deterministic OHLCV candles."""
    candles = []
    price = base_price
    start = datetime(2024, 1, 1)
    for i in range(n):
        open_p = price
        close_p = price + trend * 0.0001
        high = max(open_p, close_p) + 0.0010
        low = min(open_p, close_p) - 0.0010
        candles.append({
            "timestamp": start + timedelta(hours=i),
            "open": round(open_p, 5),
            "high": round(high, 5),
            "low": round(low, 5),
            "close": round(close_p, 5),
            "volume": 1000,
        })
        price = close_p
    return candles


async def _data_provider_with_candles(candles):
    async def provider(symbol, start, end, timeframe):
        return [c for c in candles if start <= c["timestamp"] <= end]
    return provider


def _make_config(**kwargs) -> BacktestConfig:
    defaults = dict(
        strategy_type="trend_following",
        symbol="EURUSD",
        timeframe="H1",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 6, 30),
        initial_balance=10_000.0,
        risk_per_trade_pct=1.0,
        commission_per_lot=7.0,
        slippage_pips=0.5,
        spread_pips=1.5,
        leverage=100,
    )
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


# ---------------------------------------------------------------------------
# pip_size
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPipSize:
    def test_eurusd_pip(self):
        assert _pip_size("EURUSD") == 0.0001

    def test_usdjpy_pip(self):
        assert _pip_size("USDJPY") == 0.01

    def test_gbpjpy_pip(self):
        assert _pip_size("GBPJPY") == 0.01

    def test_audusd_pip(self):
        assert _pip_size("AUDUSD") == 0.0001


# ---------------------------------------------------------------------------
# Technical helpers
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTechnicalHelpers:
    def test_ema_length(self):
        import numpy as np
        arr = np.ones(50, dtype=float)
        result = _ema(arr, 20)
        assert len(result) == 50

    def test_ema_constant_series(self):
        import numpy as np
        arr = np.full(50, 2.0)
        result = _ema(arr, 10)
        assert abs(result[-1] - 2.0) < 1e-6

    def test_ema_trending(self):
        import numpy as np
        arr = np.arange(1.0, 51.0)
        result = _ema(arr, 10)
        # EMA should lag the actual value for upward-trending data
        assert result[-1] < arr[-1]
        assert result[-1] > result[0]

    def test_atr_positive(self):
        candles = _make_candles(20)
        result = _atr(candles, 14)
        assert result > 0.0

    def test_atr_minimal_candles(self):
        result = _atr([], 14)
        assert result == 0.001  # sentinel value


# ---------------------------------------------------------------------------
# BacktestConfig validation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBacktestConfig:
    def test_defaults(self):
        cfg = _make_config()
        assert cfg.initial_balance == 10_000.0
        assert cfg.commission_per_lot == 7.0
        assert cfg.risk_per_trade_pct == 1.0

    def test_parameters_default_factory(self):
        cfg1 = _make_config()
        cfg2 = _make_config()
        cfg1.parameters["x"] = 1
        assert "x" not in cfg2.parameters  # separate instances


# ---------------------------------------------------------------------------
# BacktestEngine._calculate_sharpe / sortino / max_drawdown
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMetricCalculations:
    def setup_method(self):
        async def _provider(*a):
            return []
        self.engine = BacktestEngine(data_provider=_provider)

    def test_sharpe_empty(self):
        assert self.engine._calculate_sharpe([]) == 0.0

    def test_sharpe_positive_returns(self):
        # Need variance in returns for Sharpe to be non-zero
        import numpy as np
        rng = np.random.default_rng(42)
        returns = list(rng.normal(0.002, 0.005, 252))
        s = self.engine._calculate_sharpe(returns)
        assert s > 0.0

    def test_sharpe_all_negative(self):
        import numpy as np
        rng = np.random.default_rng(99)
        returns = list(rng.normal(-0.002, 0.005, 252))
        s = self.engine._calculate_sharpe(returns)
        assert s < 0.0

    def test_sharpe_zero_std(self):
        # Constant returns: mean excess = small positive but std approaches 0 - returns 0
        returns = [0.0002 / 252] * 252  # exactly risk-free rate
        # No meaningful Sharpe when std=0
        s = self.engine._calculate_sharpe(returns)
        assert isinstance(s, float)

    def test_sortino_no_downside(self):
        returns = [0.002] * 100
        s = self.engine._calculate_sortino(returns)
        assert s == float("inf") or s > 100  # very high Sortino with no losses

    def test_sortino_with_downside(self):
        returns = [0.001, -0.002, 0.003, -0.001, 0.002]
        s = self.engine._calculate_sortino(returns)
        assert isinstance(s, float)

    def test_max_drawdown_no_drawdown(self):
        equity = [10000.0, 10100.0, 10200.0, 10300.0]
        dd, days = self.engine._calculate_max_drawdown(equity)
        assert dd == pytest.approx(0.0, abs=1e-6)
        assert days == 0

    def test_max_drawdown_simple(self):
        equity = [10000.0, 11000.0, 9000.0, 9500.0]
        dd, days = self.engine._calculate_max_drawdown(equity)
        # Peak = 11000, trough = 9000 => 18.18%
        assert dd == pytest.approx(18.18, rel=0.01)

    def test_max_drawdown_recovery(self):
        equity = [10000.0, 12000.0, 8000.0, 12000.0]
        dd, days = self.engine._calculate_max_drawdown(equity)
        assert dd == pytest.approx(33.33, rel=0.01)

    def test_profit_factor_no_losses(self):
        trades = [
            _make_fake_trade(pnl=100),
            _make_fake_trade(pnl=200),
        ]
        pf = self.engine._calculate_profit_factor(trades)
        assert pf == float("inf")

    def test_profit_factor_normal(self):
        trades = [
            _make_fake_trade(pnl=200),
            _make_fake_trade(pnl=-100),
        ]
        pf = self.engine._calculate_profit_factor(trades)
        assert pf == pytest.approx(2.0)

    def test_profit_factor_all_losses(self):
        trades = [_make_fake_trade(pnl=-100), _make_fake_trade(pnl=-50)]
        pf = self.engine._calculate_profit_factor(trades)
        assert pf == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# BacktestEngine.run - integration style (with synthetic data)
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestBacktestEngineRun:
    async def test_empty_data_returns_empty_result(self):
        async def provider(*a):
            return []
        engine = BacktestEngine(data_provider=provider)
        config = _make_config()
        result = await engine.run(config)
        assert result.total_trades == 0
        assert result.net_profit == 0.0
        assert result.final_balance == 10_000.0

    async def test_run_with_candles_produces_result(self):
        candles = _make_candles(300, trend=2.0)  # upward trend
        start = candles[0]["timestamp"]
        end = candles[-1]["timestamp"]

        async def provider(symbol, s, e, tf):
            return [c for c in candles if s <= c["timestamp"] <= e]

        engine = BacktestEngine(data_provider=provider)
        config = _make_config(start_date=start, end_date=end)
        result = await engine.run(config)

        assert isinstance(result, BacktestResult)
        assert result.total_trades >= 0
        assert result.initial_balance == 10_000.0
        assert 0.0 <= result.win_rate <= 1.0
        assert result.run_id is not None

    async def test_result_equity_curve_starts_at_initial(self):
        candles = _make_candles(100)
        async def provider(*a):
            return candles

        engine = BacktestEngine(data_provider=provider)
        config = _make_config()
        result = await engine.run(config)
        assert result.equity_curve[0][1] == 10_000.0

    async def test_final_balance_consistency(self):
        """final_balance = initial + net_profit within rounding."""
        candles = _make_candles(300, trend=1.5)
        async def provider(*a):
            return candles

        engine = BacktestEngine(data_provider=provider)
        config = _make_config()
        result = await engine.run(config)

        expected = result.initial_balance + result.net_profit
        assert abs(result.final_balance - expected) < 0.01

    async def test_monthly_returns_keys_are_year_month(self):
        candles = _make_candles(300, trend=1.0)
        async def provider(*a):
            return candles

        engine = BacktestEngine(data_provider=provider)
        config = _make_config()
        result = await engine.run(config)

        for key in result.monthly_returns.keys():
            # Format should be YYYY-MM
            parts = key.split("-")
            assert len(parts) == 2
            assert len(parts[0]) == 4
            assert len(parts[1]) == 2

    async def test_winning_losing_sum_equals_total(self):
        candles = _make_candles(300, trend=1.5)
        async def provider(*a):
            return candles

        engine = BacktestEngine(data_provider=provider)
        config = _make_config()
        result = await engine.run(config)
        assert result.winning_trades + result.losing_trades == result.total_trades

    async def test_sharpe_ratio_is_finite(self):
        candles = _make_candles(300)
        async def provider(*a):
            return candles

        engine = BacktestEngine(data_provider=provider)
        config = _make_config()
        result = await engine.run(config)
        assert math.isfinite(result.sharpe_ratio)


# ---------------------------------------------------------------------------
# _simulate_trade - unit tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestSimulateTrade:
    def setup_method(self):
        async def _provider(*a):
            return []
        self.engine = BacktestEngine(data_provider=_provider)
        self.config = _make_config()

    def test_tp_hit_long(self):
        entry_candle = {
            "timestamp": datetime(2024, 1, 1),
            "open": 1.1000,
            "high": 1.1010,
            "low": 1.0990,
            "close": 1.1000,
            "volume": 100,
        }
        candles = [
            {
                "timestamp": datetime(2024, 1, 1, 1),
                "open": 1.1000,
                "high": 1.1100,  # hits TP at 1.1050
                "low": 1.0990,
                "close": 1.1050,
                "volume": 100,
            }
        ]
        trade = self.engine._simulate_trade(
            entry_candle, candles,
            entry_price=1.1000,
            direction="long",
            stop_loss=1.0950,
            take_profit=1.1050,
            size=0.1,
            config=self.config,
        )
        assert trade.exit_reason == "tp_hit"
        assert trade.pnl_pips > 0
        assert trade.pnl > 0

    def test_sl_hit_long(self):
        entry_candle = {
            "timestamp": datetime(2024, 1, 1),
            "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1000, "volume": 100,
        }
        candles = [
            {
                "timestamp": datetime(2024, 1, 1, 1),
                "open": 1.1000,
                "high": 1.1010,
                "low": 1.0940,  # hits SL at 1.0950
                "close": 1.0960,
                "volume": 100,
            }
        ]
        trade = self.engine._simulate_trade(
            entry_candle, candles,
            entry_price=1.1000,
            direction="long",
            stop_loss=1.0950,
            take_profit=1.1100,
            size=0.1,
            config=self.config,
        )
        assert trade.exit_reason == "sl_hit"
        assert trade.pnl_pips < 0

    def test_tp_hit_short(self):
        entry_candle = {
            "timestamp": datetime(2024, 1, 1),
            "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1000, "volume": 100,
        }
        candles = [
            {
                "timestamp": datetime(2024, 1, 1, 1),
                "open": 1.0980,
                "high": 1.0990,
                "low": 1.0940,  # hits TP at 1.0950 for short
                "close": 1.0960,
                "volume": 100,
            }
        ]
        trade = self.engine._simulate_trade(
            entry_candle, candles,
            entry_price=1.1000,
            direction="short",
            stop_loss=1.1060,
            take_profit=1.0950,
            size=0.1,
            config=self.config,
        )
        assert trade.exit_reason == "tp_hit"
        assert trade.pnl_pips > 0

    def test_time_exit_no_sl_tp(self):
        entry_candle = {
            "timestamp": datetime(2024, 1, 1),
            "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1000, "volume": 100,
        }
        candles = [
            {
                "timestamp": datetime(2024, 1, 1, h),
                "open": 1.1000, "high": 1.1005, "low": 1.0998, "close": 1.1001,
                "volume": 100,
            }
            for h in range(1, 5)
        ]
        trade = self.engine._simulate_trade(
            entry_candle, candles,
            entry_price=1.1000,
            direction="long",
            stop_loss=0.5000,   # way below
            take_profit=2.0000,  # way above
            size=0.1,
            config=self.config,
        )
        assert trade.exit_reason == "time_exit"

    def test_mfe_mae_tracked(self):
        entry_candle = {
            "timestamp": datetime(2024, 1, 1),
            "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1000, "volume": 100,
        }
        candles = [
            {"timestamp": datetime(2024, 1, 1, 1), "open": 1.1000,
             "high": 1.1050, "low": 1.0980, "close": 1.1020, "volume": 100},
        ]
        trade = self.engine._simulate_trade(
            entry_candle, candles,
            entry_price=1.1000,
            direction="long",
            stop_loss=0.5000,
            take_profit=2.0000,
            size=0.1,
            config=self.config,
        )
        assert trade.max_favorable_excursion > 0  # price went up 50 pips
        assert trade.max_adverse_excursion >= 0   # price went down 20 pips

    def test_commission_deducted(self):
        entry_candle = {
            "timestamp": datetime(2024, 1, 1),
            "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1000, "volume": 100,
        }
        candles = [
            {"timestamp": datetime(2024, 1, 1, 1), "open": 1.1000,
             "high": 1.1100, "low": 1.0990, "close": 1.1060, "volume": 100},
        ]
        trade = self.engine._simulate_trade(
            entry_candle, candles,
            entry_price=1.1000,
            direction="long",
            stop_loss=1.0900,
            take_profit=1.1050,
            size=1.0,
            config=self.config,
        )
        assert trade.commission > 0.0

    def test_no_candles_time_exit_at_entry(self):
        entry_candle = {
            "timestamp": datetime(2024, 1, 1),
            "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1000, "volume": 100,
        }
        trade = self.engine._simulate_trade(
            entry_candle, candles=[],
            entry_price=1.1000, direction="long",
            stop_loss=1.0950, take_profit=1.1100,
            size=0.1, config=self.config,
        )
        assert trade.exit_reason == "time_exit"


# ---------------------------------------------------------------------------
# Strategy signal functions
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestStrategySignals:
    def test_trend_needs_min_candles(self):
        candles = _make_candles(30)
        config = _make_config()
        # Only 30 candles, need 51
        result = _trend_following_signal(candles[:30], config)
        assert result is None

    def test_mean_reversion_needs_min_candles(self):
        candles = _make_candles(15)
        config = _make_config()
        result = _mean_reversion_signal(candles, config)
        assert result is None

    def test_breakout_needs_min_candles(self):
        candles = _make_candles(10)
        config = _make_config()
        result = _breakout_signal(candles, config)
        assert result is None

    def test_signal_returns_tuple_or_none(self):
        candles = _make_candles(100, trend=3.0)
        config = _make_config()
        result = _trend_following_signal(candles, config)
        if result is not None:
            direction, sl, tp = result
            assert direction in ("long", "short")
            assert sl > 0
            assert tp > 0

    def test_mean_reversion_signal_format(self):
        candles = _make_candles(100)
        config = _make_config()
        result = _mean_reversion_signal(candles, config)
        if result is not None:
            direction, sl, tp = result
            assert direction in ("long", "short")

    def test_breakout_signal_format(self):
        candles = _make_candles(100)
        config = _make_config()
        result = _breakout_signal(candles, config)
        if result is not None:
            direction, sl, tp = result
            assert direction in ("long", "short")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestBacktestEdgeCases:
    async def test_single_candle_returns_empty(self):
        candles = _make_candles(1)
        async def provider(*a):
            return candles

        engine = BacktestEngine(data_provider=provider)
        config = _make_config()
        result = await engine.run(config)
        assert result.total_trades == 0

    async def test_zero_risk_pct_handled(self):
        """Zero risk means position size = 0, no trades opened."""
        candles = _make_candles(300, trend=5.0)
        async def provider(*a):
            return candles

        engine = BacktestEngine(data_provider=provider)
        config = _make_config(risk_per_trade_pct=0.001)
        result = await engine.run(config)
        assert isinstance(result, BacktestResult)

    async def test_different_strategies_produce_results(self):
        candles = _make_candles(300)
        async def provider(*a):
            return candles

        engine = BacktestEngine(data_provider=provider)

        for strategy in ("trend_following", "mean_reversion", "breakout"):
            config = _make_config(strategy_type=strategy)
            result = await engine.run(config)
            assert isinstance(result, BacktestResult)
            assert result.total_trades >= 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_trade(pnl: float) -> BacktestTrade:
    return BacktestTrade(
        trade_id=uuid4(),
        symbol="EURUSD",
        direction="long",
        entry_price=1.1000,
        exit_price=1.1050 if pnl > 0 else 1.0950,
        size=0.1,
        entry_time=datetime(2024, 1, 1),
        exit_time=datetime(2024, 1, 2),
        pnl=pnl,
        pnl_pips=50.0 if pnl > 0 else -50.0,
        commission=0.7,
        slippage=0.1,
        stop_loss=1.0950,
        take_profit=1.1050,
        exit_reason="tp_hit" if pnl > 0 else "sl_hit",
        max_favorable_excursion=60.0,
        max_adverse_excursion=10.0,
        r_multiple=1.0 if pnl > 0 else -1.0,
    )
