"""Analytics API router - portfolio metrics, backtesting, and optimization endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

logger = structlog.get_logger()

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# In-memory job store (replace with Redis in production)
_backtest_jobs: dict[str, dict] = {}
_optimize_jobs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    strategy_type: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_balance: float = Field(default=10_000.0, gt=0)
    risk_per_trade_pct: float = Field(default=1.0, gt=0, le=10)
    commission_per_lot: float = Field(default=7.0, ge=0)
    slippage_pips: float = Field(default=0.5, ge=0)
    spread_pips: float = Field(default=1.5, ge=0)
    leverage: int = Field(default=100, gt=0)
    parameters: dict[str, Any] = Field(default_factory=dict)


class OptimizationRequest(BaseModel):
    strategy_type: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    param_space: dict[str, Any]  # {"sl_atr": [1.0, 3.0], ...}
    n_trials: int = Field(default=100, ge=1, le=1000)
    metric: str = Field(default="sharpe_ratio")
    walk_forward: bool = False
    n_splits: int = Field(default=5, ge=2, le=20)
    initial_balance: float = Field(default=10_000.0, gt=0)


class EquityCurveResponse(BaseModel):
    timestamps: list[str]
    equity: list[float]
    drawdown_pct: list[float]


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_analytics_engine():
    """Returns an AnalyticsEngine. In production this would use DI container."""
    from forex_trading.analytics.engine import AnalyticsEngine
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _null_factory():
        class _NullSession:
            async def get_closed_positions(self, *args, **kwargs) -> list:
                return []
        yield _NullSession()

    return AnalyticsEngine(db_session_factory=_null_factory)


def _get_backtest_engine():
    from forex_trading.analytics.backtesting.engine import BacktestEngine

    async def _null_provider(symbol, start, end, timeframe):
        return []

    return BacktestEngine(data_provider=_null_provider)


# ---------------------------------------------------------------------------
# Analytics endpoints
# ---------------------------------------------------------------------------

@router.get("/portfolio")
async def get_portfolio_metrics(
    broker_account_id: UUID = Query(...),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
) -> dict:
    """Compute comprehensive portfolio performance metrics."""
    engine = _get_analytics_engine()
    try:
        metrics = await engine.compute_portfolio_metrics(
            broker_account_id=broker_account_id,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        logger.error("portfolio_metrics_failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return {
        "broker_account_id": str(broker_account_id),
        "total_trades": metrics.total_trades,
        "winning_trades": metrics.winning_trades,
        "losing_trades": metrics.losing_trades,
        "win_rate": metrics.win_rate,
        "profit_factor": metrics.profit_factor,
        "sharpe_ratio": metrics.sharpe_ratio,
        "sortino_ratio": metrics.sortino_ratio,
        "calmar_ratio": metrics.calmar_ratio,
        "max_drawdown_pct": metrics.max_drawdown_pct,
        "max_drawdown_duration_days": metrics.max_drawdown_duration_days,
        "net_profit": metrics.net_profit,
        "gross_profit": metrics.gross_profit,
        "gross_loss": metrics.gross_loss,
        "avg_win_pips": metrics.avg_win_pips,
        "avg_loss_pips": metrics.avg_loss_pips,
        "expectancy": metrics.expectancy,
        "avg_r_multiple": metrics.avg_r_multiple,
        "best_trade_pnl": metrics.best_trade_pnl,
        "worst_trade_pnl": metrics.worst_trade_pnl,
        "avg_trade_duration_hours": metrics.avg_trade_duration_hours,
        "total_commission_paid": metrics.total_commission_paid,
        "consecutive_wins_max": metrics.consecutive_wins_max,
        "consecutive_losses_max": metrics.consecutive_losses_max,
    }


@router.get("/equity-curve")
async def get_equity_curve(
    broker_account_id: UUID = Query(...),
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    initial_balance: float = Query(default=10_000.0, gt=0),
) -> EquityCurveResponse:
    """Get equity curve data for charting."""
    engine = _get_analytics_engine()
    try:
        points = await engine.get_equity_curve(
            broker_account_id=broker_account_id,
            granularity=granularity,
            initial_balance=initial_balance,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return EquityCurveResponse(
        timestamps=[p.timestamp.isoformat() for p in points],
        equity=[p.equity for p in points],
        drawdown_pct=[p.drawdown_pct for p in points],
    )


@router.get("/monthly-returns")
async def get_monthly_returns(
    broker_account_id: UUID = Query(...),
    initial_balance: float = Query(default=10_000.0, gt=0),
) -> dict:
    """Get monthly returns as percentage - suitable for heatmap rendering."""
    engine = _get_analytics_engine()
    try:
        returns = await engine.get_monthly_returns(
            broker_account_id=broker_account_id,
            initial_balance=initial_balance,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return {"broker_account_id": str(broker_account_id), "monthly_returns": returns}


@router.get("/strategies")
async def get_strategy_metrics(
    broker_account_id: UUID = Query(...),
    strategy_type: str = Query(...),
) -> dict:
    """Get per-strategy performance metrics."""
    engine = _get_analytics_engine()
    try:
        metrics = await engine.compute_strategy_metrics(
            strategy_type=strategy_type,
            broker_account_id=broker_account_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return {
        "strategy_type": metrics.strategy_type,
        "total_trades": metrics.total_trades,
        "win_rate": metrics.win_rate,
        "profit_factor": metrics.profit_factor,
        "net_profit": metrics.net_profit,
        "avg_r_multiple": metrics.avg_r_multiple,
        "sharpe_ratio": metrics.sharpe_ratio,
        "avg_trade_duration_hours": metrics.avg_trade_duration_hours,
    }


@router.get("/pairs")
async def get_pair_metrics(
    broker_account_id: UUID = Query(...),
    symbol: str = Query(...),
) -> dict:
    """Get per-currency-pair performance metrics."""
    engine = _get_analytics_engine()
    try:
        metrics = await engine.compute_pair_metrics(
            symbol=symbol.upper(),
            broker_account_id=broker_account_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return {
        "symbol": metrics.symbol,
        "total_trades": metrics.total_trades,
        "win_rate": metrics.win_rate,
        "profit_factor": metrics.profit_factor,
        "net_profit": metrics.net_profit,
        "avg_win_pips": metrics.avg_win_pips,
        "avg_loss_pips": metrics.avg_loss_pips,
        "best_trade_pnl": metrics.best_trade_pnl,
        "worst_trade_pnl": metrics.worst_trade_pnl,
    }


@router.get("/sessions")
async def get_session_metrics(
    broker_account_id: UUID = Query(...),
) -> dict:
    """Get per-trading-session performance metrics."""
    engine = _get_analytics_engine()
    try:
        metrics = await engine.compute_session_metrics(broker_account_id=broker_account_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return {
        "broker_account_id": str(broker_account_id),
        "sessions": {
            name: {
                "session_name": m.session_name,
                "total_trades": m.total_trades,
                "win_rate": m.win_rate,
                "profit_factor": m.profit_factor,
                "net_profit": m.net_profit,
                "avg_pips": m.avg_pips,
            }
            for name, m in metrics.items()
        },
    }


# ---------------------------------------------------------------------------
# Backtest endpoints
# ---------------------------------------------------------------------------

@router.post("/backtest", status_code=status.HTTP_202_ACCEPTED)
async def run_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Enqueue an async backtest job. Returns run_id for polling."""
    from forex_trading.analytics.backtesting.engine import BacktestConfig

    run_id = str(uuid4())
    _backtest_jobs[run_id] = {"status": "pending", "result": None, "error": None}

    config = BacktestConfig(
        strategy_type=request.strategy_type,
        symbol=request.symbol,
        timeframe=request.timeframe,
        start_date=request.start_date,
        end_date=request.end_date,
        initial_balance=request.initial_balance,
        risk_per_trade_pct=request.risk_per_trade_pct,
        commission_per_lot=request.commission_per_lot,
        slippage_pips=request.slippage_pips,
        spread_pips=request.spread_pips,
        leverage=request.leverage,
        parameters=request.parameters,
    )

    background_tasks.add_task(_run_backtest_job, run_id, config)

    logger.info("backtest_job_enqueued", run_id=run_id, strategy=config.strategy_type)
    return {"run_id": run_id, "status": "pending"}


@router.get("/backtest/{run_id}")
async def get_backtest_result(run_id: str) -> dict:
    """Poll backtest job status and result."""
    job = _backtest_jobs.get(run_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest run not found")

    if job["status"] == "pending":
        return {"run_id": run_id, "status": "pending"}
    if job["status"] == "error":
        return {"run_id": run_id, "status": "error", "error": job["error"]}

    result = job["result"]
    return {
        "run_id": run_id,
        "status": "complete",
        "total_trades": result.total_trades,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "net_profit": result.net_profit,
        "sharpe_ratio": result.sharpe_ratio,
        "sortino_ratio": result.sortino_ratio,
        "calmar_ratio": result.calmar_ratio,
        "max_drawdown_pct": result.max_drawdown_pct,
        "total_return_pct": result.total_return_pct,
        "final_balance": result.final_balance,
        "monthly_returns": result.monthly_returns,
    }


async def _run_backtest_job(run_id: str, config) -> None:
    _backtest_jobs[run_id]["status"] = "running"
    try:
        engine = _get_backtest_engine()
        result = await engine.run(config)
        _backtest_jobs[run_id] = {"status": "complete", "result": result, "error": None}
    except Exception as exc:
        logger.error("backtest_job_failed", run_id=run_id, error=str(exc))
        _backtest_jobs[run_id] = {"status": "error", "result": None, "error": str(exc)}


# ---------------------------------------------------------------------------
# Optimization endpoints
# ---------------------------------------------------------------------------

@router.post("/optimize", status_code=status.HTTP_202_ACCEPTED)
async def run_optimization(
    request: OptimizationRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Enqueue an async optimization job."""
    from forex_trading.analytics.backtesting.engine import BacktestConfig

    job_id = str(uuid4())
    _optimize_jobs[job_id] = {"status": "pending", "result": None, "error": None}

    config = BacktestConfig(
        strategy_type=request.strategy_type,
        symbol=request.symbol,
        timeframe=request.timeframe,
        start_date=request.start_date,
        end_date=request.end_date,
        initial_balance=request.initial_balance,
    )

    background_tasks.add_task(
        _run_optimize_job,
        job_id,
        config,
        request.param_space,
        request.n_trials,
        request.metric,
        request.walk_forward,
        request.n_splits,
    )

    logger.info("optimize_job_enqueued", job_id=job_id, strategy=config.strategy_type)
    return {"job_id": job_id, "status": "pending"}


@router.get("/optimize/{job_id}")
async def get_optimization_result(job_id: str) -> dict:
    """Poll optimization job status and result."""
    job = _optimize_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optimization job not found")

    if job["status"] == "pending":
        return {"job_id": job_id, "status": "pending"}
    if job["status"] == "error":
        return {"job_id": job_id, "status": "error", "error": job["error"]}

    result = job["result"]
    return {
        "job_id": job_id,
        "status": "complete",
        "best_params": result.best_params,
        "best_score": result.best_score,
        "metric": result.metric,
        "n_trials": result.n_trials,
        "stability_score": result.stability_score,
        "top_trials": result.trials[:10],
    }


async def _run_optimize_job(
    job_id: str,
    config,
    param_space: dict,
    n_trials: int,
    metric: str,
    walk_forward: bool,
    n_splits: int,
) -> None:
    _optimize_jobs[job_id]["status"] = "running"
    try:
        from forex_trading.analytics.optimization.optuna_optimizer import StrategyOptimizer
        engine = _get_backtest_engine()
        optimizer = StrategyOptimizer(engine)

        if walk_forward:
            wf_result = await optimizer.walk_forward_optimize(
                config, param_space, n_splits=n_splits, metric=metric
            )
            # Return the last split's optimization result as the primary result
            result = wf_result.in_sample_results[-1] if wf_result.in_sample_results else None
            if result is None:
                raise ValueError("Walk-forward returned no results")
        else:
            result = await optimizer.optimize(config, param_space, n_trials=n_trials, metric=metric)

        _optimize_jobs[job_id] = {"status": "complete", "result": result, "error": None}
    except Exception as exc:
        logger.error("optimize_job_failed", job_id=job_id, error=str(exc))
        _optimize_jobs[job_id] = {"status": "error", "result": None, "error": str(exc)}
