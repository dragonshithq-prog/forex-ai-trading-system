"""Analytics Engine - compute performance metrics from historical trades."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID

import numpy as np
import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

@dataclass
class PortfolioMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    win_rate: float = 0.0
    profit_factor: float = 0.0

    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: int = 0

    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0

    avg_win_pips: float = 0.0
    avg_loss_pips: float = 0.0

    expectancy: float = 0.0
    avg_r_multiple: float = 0.0

    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0

    avg_trade_duration_hours: float = 0.0
    total_commission_paid: float = 0.0

    consecutive_wins_max: int = 0
    consecutive_losses_max: int = 0


@dataclass
class StrategyMetrics:
    strategy_type: str = ""
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_profit: float = 0.0
    avg_r_multiple: float = 0.0
    sharpe_ratio: float = 0.0
    avg_trade_duration_hours: float = 0.0


@dataclass
class PairMetrics:
    symbol: str = ""
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_profit: float = 0.0
    avg_win_pips: float = 0.0
    avg_loss_pips: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0


@dataclass
class SessionMetrics:
    session_name: str = ""
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_profit: float = 0.0
    avg_pips: float = 0.0


@dataclass
class EquityPoint:
    timestamp: datetime
    equity: float
    drawdown_pct: float


# ---------------------------------------------------------------------------
# Session detection helpers
# ---------------------------------------------------------------------------

_SESSION_HOURS_UTC: dict[str, tuple[int, int]] = {
    "sydney": (21, 6),    # 21:00 - 06:00 UTC
    "tokyo": (0, 9),      # 00:00 - 09:00 UTC
    "london": (7, 16),    # 07:00 - 16:00 UTC
    "new_york": (12, 21), # 12:00 - 21:00 UTC
}


def _detect_session(dt: datetime) -> str:
    hour = dt.hour
    # Simple priority: London > New York > Tokyo > Sydney
    if 7 <= hour < 16:
        return "london"
    if 12 <= hour < 21:
        return "new_york"
    if 0 <= hour < 9:
        return "tokyo"
    return "sydney"


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class AnalyticsEngine:
    """
    Compute trading performance analytics from historical trade records.

    Accepts a db_session_factory that returns an async context manager
    yielding a session with a method: get_closed_positions(broker_account_id,
    start_date, end_date) -> list[dict].
    """

    def __init__(self, db_session_factory: Callable) -> None:
        self._db_factory = db_session_factory

    async def compute_portfolio_metrics(
        self,
        broker_account_id: UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> PortfolioMetrics:
        """Compute comprehensive portfolio metrics for a broker account."""
        trades = await self._fetch_trades(broker_account_id, start_date, end_date)
        if not trades:
            return PortfolioMetrics()
        return _compute_portfolio(trades)

    async def compute_strategy_metrics(
        self,
        strategy_type: str,
        broker_account_id: UUID,
    ) -> StrategyMetrics:
        """Compute per-strategy performance metrics."""
        trades = await self._fetch_trades(broker_account_id)
        strategy_trades = [t for t in trades if t.get("strategy_type") == strategy_type]
        if not strategy_trades:
            return StrategyMetrics(strategy_type=strategy_type)

        wins = [t for t in strategy_trades if t.get("pnl", 0.0) > 0]
        losses = [t for t in strategy_trades if t.get("pnl", 0.0) <= 0]
        win_rate = len(wins) / len(strategy_trades)
        gross_profit = sum(t.get("pnl", 0.0) for t in wins)
        gross_loss = abs(sum(t.get("pnl", 0.0) for t in losses))
        net_profit = gross_profit - gross_loss
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        r_multiples = [t.get("r_multiple", 0.0) for t in strategy_trades]
        avg_r = sum(r_multiples) / len(r_multiples)
        daily_pnls = _daily_pnls(strategy_trades)
        sharpe = _sharpe_from_daily(list(daily_pnls.values()))
        durations = [t.get("duration_hours", 0.0) for t in strategy_trades]
        avg_dur = sum(durations) / len(durations) if durations else 0.0

        return StrategyMetrics(
            strategy_type=strategy_type,
            total_trades=len(strategy_trades),
            win_rate=win_rate,
            profit_factor=pf,
            net_profit=net_profit,
            avg_r_multiple=avg_r,
            sharpe_ratio=sharpe,
            avg_trade_duration_hours=avg_dur,
        )

    async def compute_pair_metrics(
        self,
        symbol: str,
        broker_account_id: UUID,
    ) -> PairMetrics:
        """Compute per-currency-pair performance metrics."""
        trades = await self._fetch_trades(broker_account_id)
        pair_trades = [t for t in trades if t.get("symbol") == symbol]
        if not pair_trades:
            return PairMetrics(symbol=symbol)

        wins = [t for t in pair_trades if t.get("pnl", 0.0) > 0]
        losses = [t for t in pair_trades if t.get("pnl", 0.0) <= 0]
        win_rate = len(wins) / len(pair_trades)
        gross_profit = sum(t.get("pnl", 0.0) for t in wins)
        gross_loss = abs(sum(t.get("pnl", 0.0) for t in losses))
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        avg_win_pips = sum(t.get("pnl_pips", 0.0) for t in wins) / len(wins) if wins else 0.0
        avg_loss_pips = sum(t.get("pnl_pips", 0.0) for t in losses) / len(losses) if losses else 0.0
        pnls = [t.get("pnl", 0.0) for t in pair_trades]

        return PairMetrics(
            symbol=symbol,
            total_trades=len(pair_trades),
            win_rate=win_rate,
            profit_factor=pf,
            net_profit=gross_profit - gross_loss,
            avg_win_pips=avg_win_pips,
            avg_loss_pips=avg_loss_pips,
            best_trade_pnl=max(pnls),
            worst_trade_pnl=min(pnls),
        )

    async def compute_session_metrics(
        self,
        broker_account_id: UUID,
    ) -> dict[str, SessionMetrics]:
        """Compute per-trading-session performance (London, NY, Tokyo, Sydney)."""
        trades = await self._fetch_trades(broker_account_id)
        buckets: dict[str, list[dict]] = {s: [] for s in _SESSION_HOURS_UTC}

        for t in trades:
            exit_time = t.get("exit_time") or t.get("closed_at") or datetime.utcnow()
            if isinstance(exit_time, str):
                exit_time = datetime.fromisoformat(exit_time)
            session = _detect_session(exit_time)
            buckets.setdefault(session, []).append(t)

        result: dict[str, SessionMetrics] = {}
        for session_name, session_trades in buckets.items():
            if not session_trades:
                result[session_name] = SessionMetrics(session_name=session_name)
                continue
            wins = [t for t in session_trades if t.get("pnl", 0.0) > 0]
            losses = [t for t in session_trades if t.get("pnl", 0.0) <= 0]
            gross_profit = sum(t.get("pnl", 0.0) for t in wins)
            gross_loss = abs(sum(t.get("pnl", 0.0) for t in losses))
            pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
            avg_pips = sum(t.get("pnl_pips", 0.0) for t in session_trades) / len(session_trades)
            result[session_name] = SessionMetrics(
                session_name=session_name,
                total_trades=len(session_trades),
                win_rate=len(wins) / len(session_trades),
                profit_factor=pf,
                net_profit=gross_profit - gross_loss,
                avg_pips=avg_pips,
            )
        return result

    async def get_equity_curve(
        self,
        broker_account_id: UUID,
        granularity: str = "day",
        initial_balance: float = 10_000.0,
    ) -> list[EquityPoint]:
        """
        Build equity curve from closed trades.

        Args:
            granularity: "day" | "week" | "month"
            initial_balance: Starting account balance assumption
        """
        trades = await self._fetch_trades(broker_account_id)
        if not trades:
            return [EquityPoint(timestamp=datetime.utcnow(), equity=initial_balance, drawdown_pct=0.0)]

        trades_sorted = sorted(
            trades,
            key=lambda t: t.get("exit_time") or t.get("closed_at") or datetime.utcnow(),
        )

        # Aggregate PnL per granularity bucket
        bucket_pnl: dict[datetime, float] = {}
        for t in trades_sorted:
            exit_time = t.get("exit_time") or t.get("closed_at") or datetime.utcnow()
            if isinstance(exit_time, str):
                exit_time = datetime.fromisoformat(exit_time)
            bucket = _truncate_datetime(exit_time, granularity)
            bucket_pnl[bucket] = bucket_pnl.get(bucket, 0.0) + t.get("pnl", 0.0)

        equity = initial_balance
        peak = initial_balance
        points: list[EquityPoint] = []

        for ts in sorted(bucket_pnl):
            equity += bucket_pnl[ts]
            peak = max(peak, equity)
            dd_pct = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
            points.append(EquityPoint(timestamp=ts, equity=equity, drawdown_pct=dd_pct))

        return points

    async def get_monthly_returns(
        self,
        broker_account_id: UUID,
        initial_balance: float = 10_000.0,
    ) -> dict[str, float]:
        """Get monthly returns as percentage of initial balance."""
        trades = await self._fetch_trades(broker_account_id)
        monthly: dict[str, float] = {}
        for t in trades:
            exit_time = t.get("exit_time") or t.get("closed_at") or datetime.utcnow()
            if isinstance(exit_time, str):
                exit_time = datetime.fromisoformat(exit_time)
            key = exit_time.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0.0) + t.get("pnl", 0.0)

        return {k: v / initial_balance * 100.0 for k, v in sorted(monthly.items())}

    async def _fetch_trades(
        self,
        broker_account_id: UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """Fetch closed trades from DB via the session factory."""
        try:
            async with self._db_factory() as session:
                if hasattr(session, "get_closed_positions"):
                    return await session.get_closed_positions(
                        broker_account_id, start_date, end_date
                    )
                # Fallback: session is a raw SQLAlchemy session
                return await _query_positions(session, broker_account_id, start_date, end_date)
        except Exception as exc:
            logger.error("analytics_fetch_failed", error=str(exc), account_id=str(broker_account_id))
            return []


# ---------------------------------------------------------------------------
# SQLAlchemy query helper
# ---------------------------------------------------------------------------

async def _query_positions(
    session,
    broker_account_id: UUID,
    start_date: datetime | None,
    end_date: datetime | None,
) -> list[dict]:
    from sqlalchemy import select, and_
    try:
        from forex_trading.shared.database.models_trading import Position, PositionStatus
    except ImportError:
        return []

    filters = [
        Position.broker_account_id == broker_account_id,
        Position.status == PositionStatus.CLOSED,
    ]
    if start_date:
        filters.append(Position.closed_at >= start_date)
    if end_date:
        filters.append(Position.closed_at <= end_date)

    stmt = select(Position).where(and_(*filters)).order_by(Position.closed_at)
    result = await session.execute(stmt)
    positions = result.scalars().all()

    trades = []
    for p in positions:
        duration_hours = 0.0
        if p.closed_at and p.opened_at:
            duration_hours = (p.closed_at - p.opened_at).total_seconds() / 3600.0

        # pnl_pips approximation
        from forex_trading.analytics.backtesting.engine import _pip_size
        pip = _pip_size(p.symbol)
        if p.side.value == "long":
            pnl_pips = (p.current_price - p.entry_price) / pip
        else:
            pnl_pips = (p.entry_price - p.current_price) / pip

        trades.append({
            "id": str(p.id),
            "symbol": p.symbol,
            "side": p.side.value,
            "pnl": p.realized_pnl or 0.0,
            "pnl_pips": pnl_pips,
            "commission": p.commission or 0.0,
            "exit_time": p.closed_at,
            "entry_time": p.opened_at,
            "duration_hours": duration_hours,
            "strategy_type": str(p.strategy_id) if p.strategy_id else "unknown",
            "r_multiple": 0.0,  # not stored in DB
        })

    return trades


# ---------------------------------------------------------------------------
# Metric computation helpers (pure functions)
# ---------------------------------------------------------------------------

def _compute_portfolio(trades: list[dict]) -> PortfolioMetrics:
    wins = [t for t in trades if t.get("pnl", 0.0) > 0]
    losses = [t for t in trades if t.get("pnl", 0.0) <= 0]

    gross_profit = sum(t.get("pnl", 0.0) for t in wins)
    gross_loss = abs(sum(t.get("pnl", 0.0) for t in losses))
    net_profit = gross_profit - gross_loss
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    win_rate = len(wins) / len(trades)

    avg_win_pips = sum(t.get("pnl_pips", 0.0) for t in wins) / len(wins) if wins else 0.0
    avg_loss_pips = sum(t.get("pnl_pips", 0.0) for t in losses) / len(losses) if losses else 0.0

    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss_abs = gross_loss / len(losses) if losses else 0.0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss_abs)

    r_multiples = [t.get("r_multiple", 0.0) for t in trades]
    avg_r = sum(r_multiples) / len(r_multiples)

    pnls = [t.get("pnl", 0.0) for t in trades]
    best_trade = max(pnls)
    worst_trade = min(pnls)

    durations = [t.get("duration_hours", 0.0) for t in trades]
    avg_dur = sum(durations) / len(durations)

    total_commission = sum(t.get("commission", 0.0) for t in trades)

    cons_wins, cons_losses = _consecutive_streaks(trades)

    # Build equity series for drawdown
    initial = 10_000.0  # approximation; actual balance fed separately
    equity_vals = [initial]
    for t in sorted(trades, key=lambda x: x.get("exit_time") or datetime.utcnow()):
        equity_vals.append(equity_vals[-1] + t.get("pnl", 0.0))

    max_dd_pct, max_dd_days = _max_drawdown(equity_vals)

    # Annualized metrics
    daily_pnl_map = _daily_pnls(trades)
    daily_ret = list(daily_pnl_map.values())
    initial_equity = equity_vals[0]
    daily_returns_pct = [p / initial_equity for p in daily_ret]

    sharpe = _sharpe_from_daily(daily_returns_pct)
    sortino = _sortino_from_daily(daily_returns_pct)

    total_return = (equity_vals[-1] - initial) / initial
    n_days = max(len(daily_ret), 1)
    ann_return = (1 + total_return) ** (252 / n_days) - 1
    calmar = ann_return / (max_dd_pct / 100.0) if max_dd_pct > 0 else 0.0

    return PortfolioMetrics(
        total_trades=len(trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=win_rate,
        profit_factor=pf,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        max_drawdown_pct=max_dd_pct,
        max_drawdown_duration_days=max_dd_days,
        net_profit=net_profit,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        avg_win_pips=avg_win_pips,
        avg_loss_pips=avg_loss_pips,
        expectancy=expectancy,
        avg_r_multiple=avg_r,
        best_trade_pnl=best_trade,
        worst_trade_pnl=worst_trade,
        avg_trade_duration_hours=avg_dur,
        total_commission_paid=total_commission,
        consecutive_wins_max=cons_wins,
        consecutive_losses_max=cons_losses,
    )


def _sharpe_from_daily(daily_returns: list[float], rf_daily: float = 0.02 / 252) -> float:
    if len(daily_returns) < 2:
        return 0.0
    arr = np.array(daily_returns, dtype=float)
    excess = arr - rf_daily
    std = float(np.std(excess, ddof=1))
    if std == 0.0:
        return 0.0
    return float(np.mean(excess) / std * math.sqrt(252))


def _sortino_from_daily(daily_returns: list[float], rf_daily: float = 0.02 / 252) -> float:
    if len(daily_returns) < 2:
        return 0.0
    arr = np.array(daily_returns, dtype=float)
    mean_excess = float(np.mean(arr)) - rf_daily
    downside = arr[arr < 0]
    if len(downside) == 0:
        return float("inf") if mean_excess > 0 else 0.0
    downside_std = float(np.std(downside, ddof=1))
    if downside_std == 0.0:
        return 0.0
    return float(mean_excess / downside_std * math.sqrt(252))


def _max_drawdown(equity_curve: list[float]) -> tuple[float, int]:
    if not equity_curve:
        return 0.0, 0
    arr = np.array(equity_curve, dtype=float)
    peak = np.maximum.accumulate(arr)
    drawdown = (peak - arr) / np.where(peak > 0, peak, 1.0)
    max_dd = float(np.max(drawdown)) * 100.0
    in_dd = drawdown > 0
    max_streak = streak = 0
    for v in in_dd:
        streak = streak + 1 if v else 0
        max_streak = max(max_streak, streak)
    return max_dd, max_streak


def _consecutive_streaks(trades: list[dict]) -> tuple[int, int]:
    sorted_t = sorted(trades, key=lambda t: t.get("exit_time") or datetime.utcnow())
    max_wins = max_losses = wins = losses = 0
    for t in sorted_t:
        if t.get("pnl", 0.0) > 0:
            wins += 1
            losses = 0
        else:
            losses += 1
            wins = 0
        max_wins = max(max_wins, wins)
        max_losses = max(max_losses, losses)
    return max_wins, max_losses


def _daily_pnls(trades: list[dict]) -> dict[str, float]:
    result: dict[str, float] = {}
    for t in trades:
        exit_time = t.get("exit_time") or t.get("closed_at") or datetime.utcnow()
        if isinstance(exit_time, str):
            exit_time = datetime.fromisoformat(exit_time)
        key = exit_time.strftime("%Y-%m-%d")
        result[key] = result.get(key, 0.0) + t.get("pnl", 0.0)
    return result


def _truncate_datetime(dt: datetime, granularity: str) -> datetime:
    if granularity == "month":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if granularity == "week":
        return (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    # default: day
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)
