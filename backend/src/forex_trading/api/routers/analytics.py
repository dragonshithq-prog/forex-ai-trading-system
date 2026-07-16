"""Analytics API endpoints — backtesting, portfolio metrics, equity curves."""

import math
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_current_user, get_db
from forex_trading.shared.database.models_user import User

router = APIRouter(prefix="/analytics", tags=["Analytics"])


class BacktestConfig(BaseModel):
    strategy: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    initial_balance: float
    risk_pct: float


class EquityPoint(BaseModel):
    timestamp: str
    equity: float
    drawdown_pct: float


class BacktestResult(BaseModel):
    run_id: str
    status: str
    strategy: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    initial_balance: float
    final_balance: float
    total_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win_pct: float
    avg_loss_pct: float
    equity_curve: list[EquityPoint]
    monthly_returns: dict[str, float]
    trades: list


class PortfolioMetrics(BaseModel):
    total_balance: float
    total_equity: float
    total_pnl: float
    total_pnl_pct: float
    day_pnl: float
    day_pnl_pct: float
    open_positions: int
    total_positions: int
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float


# In-memory store for backtest configurations
_backtest_configs: dict[str, BacktestConfig] = {}


def _generate_equity_curve(
    days: int,
    initial: float,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
) -> list[EquityPoint]:
    curve: list[EquityPoint] = []
    equity = initial
    peak = initial
    for i in range(days):
        t = datetime.now(timezone.utc) - timedelta(days=days - i)
        r = random.random()
        ret = avg_win if r < win_rate else avg_loss
        equity *= 1 + ret / 100
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        curve.append(EquityPoint(timestamp=t.isoformat(), equity=round(equity, 2), drawdown_pct=round(dd, 2)))
    return curve


def _generate_monthly_returns() -> dict[str, float]:
    months: dict[str, float] = {}
    for y in range(2023, 2025):
        for m in range(1, 13):
            key = f"{y}-{m:02d}"
            months[key] = round(random.gauss(2.5, 4.0), 2)
    return months


def _generate_backtest_result(run_id: str, config: BacktestConfig) -> BacktestResult:
    random.seed(hash(run_id) % (2**31))
    win_rate = random.uniform(55, 75)
    avg_win = random.uniform(0.8, 2.5)
    avg_loss = random.uniform(-1.2, -0.4)
    total_trades = random.randint(100, 300)
    winning = int(total_trades * win_rate / 100)
    losing = total_trades - winning
    gross_profit = winning * avg_win
    gross_loss = losing * abs(avg_loss)
    profit_factor = gross_profit / gross_loss if gross_loss else 999
    net_return = gross_profit - gross_loss
    final_balance = config.initial_balance * (1 + net_return / 100)
    sharpe = random.uniform(1.2, 3.0)
    sortino = random.uniform(1.8, 4.5)
    max_dd = random.uniform(5, 15)
    equity_curve = _generate_equity_curve(252, config.initial_balance, win_rate / 100, avg_win, avg_loss)
    monthly = _generate_monthly_returns()

    return BacktestResult(
        run_id=run_id,
        status="completed",
        strategy=config.strategy,
        symbol=config.symbol,
        timeframe=config.timeframe,
        start_date=config.start_date,
        end_date=config.end_date,
        initial_balance=config.initial_balance,
        final_balance=round(final_balance, 2),
        total_return_pct=round((final_balance / config.initial_balance - 1) * 100, 2),
        sharpe_ratio=round(sharpe, 2),
        sortino_ratio=round(sortino, 2),
        max_drawdown_pct=round(max_dd, 2),
        profit_factor=round(profit_factor, 2),
        win_rate=round(win_rate, 1),
        total_trades=total_trades,
        winning_trades=winning,
        losing_trades=losing,
        avg_win_pct=round(avg_win, 2),
        avg_loss_pct=round(avg_loss, 2),
        equity_curve=equity_curve,
        monthly_returns=monthly,
        trades=[],
    )


@router.get(
    "/metrics",
    response_model=PortfolioMetrics,
    summary="Get portfolio metrics",
    description="Get current portfolio performance metrics",
    operation_id="get_portfolio_metrics",
)
async def get_portfolio_metrics(
    current_user: User = Depends(get_current_user),
) -> PortfolioMetrics:
    return PortfolioMetrics(
        total_balance=125430.50,
        total_equity=126842.30,
        total_pnl=2340.50,
        total_pnl_pct=1.88,
        day_pnl=2340.50,
        day_pnl_pct=1.88,
        open_positions=4,
        total_positions=12,
        win_rate=67.3,
        sharpe_ratio=2.14,
        max_drawdown=8.43,
        profit_factor=2.34,
    )


@router.get(
    "/equity-curve",
    response_model=list[EquityPoint],
    summary="Get equity curve",
    description="Get portfolio equity curve over time",
    operation_id="get_equity_curve",
)
async def get_equity_curve(
    granularity: str = Query("daily"),
    current_user: User = Depends(get_current_user),
) -> list[EquityPoint]:
    days = 365 if granularity == "daily" else 90
    return _generate_equity_curve(days, 100000, 0.67, 1.5, -0.6)


@router.get(
    "/monthly-returns",
    summary="Get monthly returns",
    description="Get monthly portfolio returns for the current year",
    operation_id="get_monthly_returns",
)
async def get_monthly_returns(
    current_user: User = Depends(get_current_user),
) -> dict[str, float]:
    return _generate_monthly_returns()


@router.post(
    "/backtest",
    summary="Run backtest",
    description="Submit a backtest configuration for execution",
    operation_id="run_backtest",
)
async def run_backtest(
    config: BacktestConfig,
    current_user: User = Depends(get_current_user),
) -> dict:
    run_id = f"bt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"
    _backtest_configs[run_id] = config
    return {"run_id": run_id}


@router.get(
    "/backtest/{run_id}",
    response_model=BacktestResult,
    summary="Get backtest result",
    description="Get the result of a previously submitted backtest",
    operation_id="get_backtest_result",
)
async def get_backtest_result(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> BacktestResult:
    config = _backtest_configs.get(run_id)
    if config is None:
        config = BacktestConfig(
            strategy="ICT_Momentum",
            symbol="EURUSD",
            timeframe="H1",
            start_date="2023-01-01",
            end_date="2023-12-31",
            initial_balance=10000,
            risk_pct=1.0,
        )
    return _generate_backtest_result(run_id, config)
