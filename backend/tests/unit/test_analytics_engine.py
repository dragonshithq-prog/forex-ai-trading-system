"""Unit tests for Analytics Engine."""

from __future__ import annotations

import math
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from forex_trading.analytics.engine import (
    AnalyticsEngine,
    PortfolioMetrics,
    StrategyMetrics,
    PairMetrics,
    SessionMetrics,
    EquityPoint,
    _compute_portfolio,
    _sharpe_from_daily,
    _sortino_from_daily,
    _max_drawdown,
    _consecutive_streaks,
    _daily_pnls,
    _truncate_datetime,
    _detect_session,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_trade(
    pnl: float = 100.0,
    symbol: str = "EURUSD",
    strategy_type: str = "trend_following",
    exit_time: datetime | None = None,
    duration_hours: float = 4.0,
    pnl_pips: float = 25.0,
    commission: float = 7.0,
    r_multiple: float = 1.0,
) -> dict:
    if exit_time is None:
        exit_time = datetime(2024, 1, 15)
    return {
        "id": str(uuid4()),
        "symbol": symbol,
        "pnl": pnl,
        "pnl_pips": pnl_pips if pnl > 0 else -abs(pnl_pips),
        "commission": commission,
        "exit_time": exit_time,
        "entry_time": exit_time - timedelta(hours=duration_hours),
        "duration_hours": duration_hours,
        "strategy_type": strategy_type,
        "r_multiple": r_multiple,
    }


def _make_trades(n_wins: int, n_losses: int) -> list[dict]:
    trades = []
    for i in range(n_wins):
        trades.append(_make_trade(pnl=100.0, pnl_pips=25.0, r_multiple=1.0,
                                  exit_time=datetime(2024, 1, i + 1)))
    for i in range(n_losses):
        trades.append(_make_trade(pnl=-50.0, pnl_pips=-12.5, r_multiple=-0.5,
                                  exit_time=datetime(2024, 2, i + 1)))
    return trades


def _make_engine(trades: list[dict] | None = None) -> AnalyticsEngine:
    """Create an AnalyticsEngine with an in-memory trade store."""
    if trades is None:
        trades = []
    stored = list(trades)

    @asynccontextmanager
    async def factory():
        class _Session:
            async def get_closed_positions(self, *a, **kw):
                return stored
        yield _Session()

    return AnalyticsEngine(db_session_factory=factory)


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSharpeFromDaily:
    def test_empty_returns_zero(self):
        assert _sharpe_from_daily([]) == 0.0

    def test_single_return_zero(self):
        assert _sharpe_from_daily([0.01]) == 0.0

    def test_all_positive(self):
        returns = [0.002] * 252
        s = _sharpe_from_daily(returns)
        assert s > 0.0

    def test_negative_returns(self):
        import numpy as np
        rng = np.random.default_rng(7)
        returns = list(rng.normal(-0.003, 0.005, 252))
        s = _sharpe_from_daily(returns)
        assert s < 0.0

    def test_mixed_returns(self):
        returns = [0.003, -0.001, 0.002, -0.002, 0.001] * 50
        s = _sharpe_from_daily(returns)
        assert math.isfinite(s)

    def test_zero_std_returns_zero(self):
        # All returns exactly at risk-free rate
        rf = 0.02 / 252
        returns = [rf] * 100
        s = _sharpe_from_daily(returns, rf_daily=rf)
        assert s == 0.0


@pytest.mark.unit
class TestSortinoFromDaily:
    def test_empty_returns_zero(self):
        assert _sortino_from_daily([]) == 0.0

    def test_no_downside_positive_mean(self):
        returns = [0.002] * 100
        s = _sortino_from_daily(returns)
        assert s == float("inf") or s > 100

    def test_all_negative(self):
        returns = [-0.001] * 100
        s = _sortino_from_daily(returns)
        assert s < 0.0

    def test_finite_with_mixed(self):
        returns = [0.003, -0.002, 0.001, -0.003, 0.004]
        s = _sortino_from_daily(returns)
        assert math.isfinite(s)


@pytest.mark.unit
class TestMaxDrawdown:
    def test_no_drawdown(self):
        dd, days = _max_drawdown([10000, 11000, 12000, 13000])
        assert dd == pytest.approx(0.0, abs=1e-6)
        assert days == 0

    def test_full_recovery(self):
        dd, days = _max_drawdown([10000, 5000, 10000])
        assert dd == pytest.approx(50.0)
        assert days > 0

    def test_single_value(self):
        dd, days = _max_drawdown([10000])
        assert dd == 0.0

    def test_empty(self):
        dd, days = _max_drawdown([])
        assert dd == 0.0
        assert days == 0

    def test_consecutive_down(self):
        equity = [10000, 9000, 8000, 7000, 6000]
        dd, days = _max_drawdown(equity)
        assert dd == pytest.approx(40.0)
        assert days == 4


@pytest.mark.unit
class TestConsecutiveStreaks:
    def test_all_wins(self):
        trades = [_make_trade(pnl=100) for _ in range(5)]
        wins, losses = _consecutive_streaks(trades)
        assert wins == 5
        assert losses == 0

    def test_all_losses(self):
        trades = [_make_trade(pnl=-50) for _ in range(3)]
        wins, losses = _consecutive_streaks(trades)
        assert wins == 0
        assert losses == 3

    def test_alternating(self):
        trades = [_make_trade(pnl=100 if i % 2 == 0 else -50,
                              exit_time=datetime(2024, 1, i + 1))
                  for i in range(6)]
        wins, losses = _consecutive_streaks(trades)
        assert wins == 1
        assert losses == 1

    def test_streak_of_3_wins(self):
        trades = [
            _make_trade(pnl=-50, exit_time=datetime(2024, 1, 1)),
            _make_trade(pnl=100, exit_time=datetime(2024, 1, 2)),
            _make_trade(pnl=100, exit_time=datetime(2024, 1, 3)),
            _make_trade(pnl=100, exit_time=datetime(2024, 1, 4)),
            _make_trade(pnl=-50, exit_time=datetime(2024, 1, 5)),
        ]
        wins, losses = _consecutive_streaks(trades)
        assert wins == 3


@pytest.mark.unit
class TestDailyPnls:
    def test_groups_by_day(self):
        trades = [
            _make_trade(pnl=100, exit_time=datetime(2024, 1, 1, 10)),
            _make_trade(pnl=50, exit_time=datetime(2024, 1, 1, 14)),
            _make_trade(pnl=-30, exit_time=datetime(2024, 1, 2, 9)),
        ]
        result = _daily_pnls(trades)
        assert result["2024-01-01"] == pytest.approx(150.0)
        assert result["2024-01-02"] == pytest.approx(-30.0)

    def test_empty_trades(self):
        result = _daily_pnls([])
        assert result == {}


@pytest.mark.unit
class TestTruncateDateTime:
    def test_day(self):
        dt = datetime(2024, 3, 15, 14, 30, 45)
        result = _truncate_datetime(dt, "day")
        assert result == datetime(2024, 3, 15, 0, 0, 0)

    def test_week(self):
        dt = datetime(2024, 3, 13, 14, 30)  # Wednesday
        result = _truncate_datetime(dt, "week")
        assert result.weekday() == 0  # Monday
        assert result.hour == 0

    def test_month(self):
        dt = datetime(2024, 3, 15, 14, 30)
        result = _truncate_datetime(dt, "month")
        assert result == datetime(2024, 3, 1, 0, 0, 0)


@pytest.mark.unit
class TestDetectSession:
    def test_london(self):
        assert _detect_session(datetime(2024, 1, 1, 10)) == "london"

    def test_new_york(self):
        # 14:00 UTC is NY but also London - London takes priority (7-16)
        assert _detect_session(datetime(2024, 1, 1, 14)) == "london"

    def test_new_york_only(self):
        # 18:00 UTC is only NY
        assert _detect_session(datetime(2024, 1, 1, 18)) == "new_york"

    def test_tokyo(self):
        assert _detect_session(datetime(2024, 1, 1, 4)) == "tokyo"

    def test_sydney(self):
        assert _detect_session(datetime(2024, 1, 1, 22)) == "sydney"


# ---------------------------------------------------------------------------
# _compute_portfolio tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestComputePortfolio:
    def test_all_wins(self):
        trades = [_make_trade(pnl=100) for _ in range(10)]
        m = _compute_portfolio(trades)
        assert m.win_rate == 1.0
        assert m.losing_trades == 0
        assert m.profit_factor == float("inf")

    def test_all_losses(self):
        trades = [_make_trade(pnl=-50) for _ in range(5)]
        m = _compute_portfolio(trades)
        assert m.win_rate == 0.0
        assert m.winning_trades == 0
        assert m.net_profit < 0

    def test_mixed_50_50(self):
        trades = _make_trades(5, 5)
        m = _compute_portfolio(trades)
        assert m.win_rate == pytest.approx(0.5)
        assert m.total_trades == 10
        assert m.profit_factor == pytest.approx(2.0)  # 500/250

    def test_expectancy_sign(self):
        trades = _make_trades(7, 3)  # 70% win rate, avg win 100, avg loss 50
        m = _compute_portfolio(trades)
        assert m.expectancy > 0

    def test_best_worst_trade(self):
        trades = [
            _make_trade(pnl=500),
            _make_trade(pnl=100),
            _make_trade(pnl=-200),
        ]
        m = _compute_portfolio(trades)
        assert m.best_trade_pnl == pytest.approx(500.0)
        assert m.worst_trade_pnl == pytest.approx(-200.0)

    def test_consecutive_win_loss_streaks(self):
        trades = [
            _make_trade(pnl=100, exit_time=datetime(2024, 1, i + 1))
            for i in range(4)
        ] + [
            _make_trade(pnl=-50, exit_time=datetime(2024, 1, i + 5))
            for i in range(2)
        ]
        m = _compute_portfolio(trades)
        assert m.consecutive_wins_max == 4
        assert m.consecutive_losses_max == 2

    def test_commission_totaled(self):
        trades = [_make_trade(pnl=100, commission=7.0) for _ in range(5)]
        m = _compute_portfolio(trades)
        assert m.total_commission_paid == pytest.approx(35.0)

    def test_sharpe_is_finite(self):
        trades = _make_trades(10, 5)
        m = _compute_portfolio(trades)
        assert math.isfinite(m.sharpe_ratio)

    def test_calmar_positive_when_profitable(self):
        trades = [_make_trade(pnl=200, exit_time=datetime(2024, 1, i + 1)) for i in range(20)]
        m = _compute_portfolio(trades)
        # If no drawdown and profit > 0, calmar = 0 (no drawdown means 0/0 guard)
        assert m.calmar_ratio >= 0.0


# ---------------------------------------------------------------------------
# AnalyticsEngine async methods
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestAnalyticsEngine:
    async def test_empty_db_returns_default_metrics(self):
        engine = _make_engine(trades=[])
        metrics = await engine.compute_portfolio_metrics(broker_account_id=uuid4())
        assert metrics.total_trades == 0
        assert metrics.net_profit == 0.0

    async def test_portfolio_metrics_win_rate(self):
        trades = _make_trades(6, 4)
        engine = _make_engine(trades)
        metrics = await engine.compute_portfolio_metrics(broker_account_id=uuid4())
        assert metrics.total_trades == 10
        assert metrics.win_rate == pytest.approx(0.6)

    async def test_strategy_metrics(self):
        trades = [
            _make_trade(pnl=100, strategy_type="trend_following"),
            _make_trade(pnl=100, strategy_type="trend_following"),
            _make_trade(pnl=-50, strategy_type="trend_following"),
            _make_trade(pnl=200, strategy_type="breakout"),
        ]
        engine = _make_engine(trades)
        m = await engine.compute_strategy_metrics("trend_following", uuid4())
        assert m.total_trades == 3
        assert m.strategy_type == "trend_following"

    async def test_strategy_metrics_unknown_returns_default(self):
        engine = _make_engine(_make_trades(5, 5))
        m = await engine.compute_strategy_metrics("nonexistent_strategy", uuid4())
        assert m.total_trades == 0

    async def test_pair_metrics(self):
        trades = [
            _make_trade(pnl=100, symbol="EURUSD"),
            _make_trade(pnl=-50, symbol="EURUSD"),
            _make_trade(pnl=200, symbol="GBPUSD"),
        ]
        engine = _make_engine(trades)
        m = await engine.compute_pair_metrics("EURUSD", uuid4())
        assert m.symbol == "EURUSD"
        assert m.total_trades == 2

    async def test_pair_metrics_unknown_symbol(self):
        engine = _make_engine(_make_trades(3, 3))
        m = await engine.compute_pair_metrics("XAUUSD", uuid4())
        assert m.total_trades == 0

    async def test_session_metrics_returns_all_sessions(self):
        trades = [
            _make_trade(pnl=100, exit_time=datetime(2024, 1, 1, 10)),  # London
            _make_trade(pnl=-50, exit_time=datetime(2024, 1, 1, 18)),  # NY
            _make_trade(pnl=80, exit_time=datetime(2024, 1, 1, 4)),   # Tokyo
        ]
        engine = _make_engine(trades)
        sessions = await engine.compute_session_metrics(uuid4())
        assert "london" in sessions
        assert "new_york" in sessions
        assert "tokyo" in sessions
        assert "sydney" in sessions

    async def test_session_metrics_win_rates(self):
        trades = [
            _make_trade(pnl=100, exit_time=datetime(2024, 1, 1, 10)),
            _make_trade(pnl=100, exit_time=datetime(2024, 1, 2, 10)),
        ]
        engine = _make_engine(trades)
        sessions = await engine.compute_session_metrics(uuid4())
        assert sessions["london"].win_rate == 1.0

    async def test_equity_curve_day_granularity(self):
        trades = [
            _make_trade(pnl=100, exit_time=datetime(2024, 1, 1, 12)),
            _make_trade(pnl=-50, exit_time=datetime(2024, 1, 2, 12)),
            _make_trade(pnl=200, exit_time=datetime(2024, 1, 3, 12)),
        ]
        engine = _make_engine(trades)
        curve = await engine.get_equity_curve(uuid4(), granularity="day")
        assert len(curve) == 3
        assert all(isinstance(p, EquityPoint) for p in curve)
        assert curve[0].equity > 10_000.0  # first profitable day

    async def test_equity_curve_monotone_on_all_wins(self):
        trades = [
            _make_trade(pnl=100, exit_time=datetime(2024, 1, i + 1, 12))
            for i in range(5)
        ]
        engine = _make_engine(trades)
        curve = await engine.get_equity_curve(uuid4(), granularity="day")
        equities = [p.equity for p in curve]
        assert equities == sorted(equities)

    async def test_drawdown_zero_on_all_wins(self):
        trades = [
            _make_trade(pnl=100, exit_time=datetime(2024, 1, i + 1, 12))
            for i in range(5)
        ]
        engine = _make_engine(trades)
        curve = await engine.get_equity_curve(uuid4(), granularity="day")
        assert all(p.drawdown_pct == pytest.approx(0.0, abs=1e-6) for p in curve)

    async def test_monthly_returns_format(self):
        trades = [
            _make_trade(pnl=100, exit_time=datetime(2024, 1, 15)),
            _make_trade(pnl=-50, exit_time=datetime(2024, 2, 15)),
        ]
        engine = _make_engine(trades)
        returns = await engine.get_monthly_returns(uuid4())
        assert "2024-01" in returns
        assert "2024-02" in returns
        assert returns["2024-01"] == pytest.approx(1.0)   # 100/10000*100
        assert returns["2024-02"] == pytest.approx(-0.5)   # -50/10000*100

    async def test_db_error_returns_empty(self):
        @asynccontextmanager
        async def failing_factory():
            raise RuntimeError("DB unavailable")
            yield  # noqa: unreachable

        engine = AnalyticsEngine(db_session_factory=failing_factory)
        metrics = await engine.compute_portfolio_metrics(uuid4())
        assert metrics.total_trades == 0
