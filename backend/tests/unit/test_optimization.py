"""Unit tests for Optuna Strategy Optimizer."""

from __future__ import annotations

import asyncio
import copy
import math
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from forex_trading.analytics.backtesting.engine import BacktestConfig, BacktestResult, BacktestEngine
from forex_trading.analytics.optimization.optuna_optimizer import (
    StrategyOptimizer,
    OptimizationResult,
    WalkForwardResult,
    _population_std,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**kwargs) -> BacktestConfig:
    defaults = dict(
        strategy_type="trend_following",
        symbol="EURUSD",
        timeframe="H1",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 6, 30),
        initial_balance=10_000.0,
    )
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


def _make_dummy_result(sharpe: float = 1.0) -> BacktestResult:
    config = _make_config()
    return BacktestResult(
        config=config,
        trades=[],
        total_trades=10,
        winning_trades=6,
        losing_trades=4,
        win_rate=0.6,
        profit_factor=1.8,
        gross_profit=600.0,
        gross_loss=400.0,
        net_profit=200.0,
        sharpe_ratio=sharpe,
        sortino_ratio=sharpe * 1.2,
        calmar_ratio=sharpe * 0.5,
        max_drawdown_pct=5.0,
        max_drawdown_duration_days=10,
        avg_win_pips=25.0,
        avg_loss_pips=-15.0,
        avg_r_multiple=1.2,
        expectancy=50.0,
        initial_balance=10_000.0,
        final_balance=10_200.0,
        total_return_pct=2.0,
        monthly_returns={"2024-01": 1.0, "2024-02": 1.0},
        equity_curve=[(datetime(2024, 1, 1), 10000.0)],
        start_date=config.start_date,
        end_date=config.end_date,
        duration_days=180,
    )


def _make_engine_returning(result: BacktestResult) -> BacktestEngine:
    """Create a BacktestEngine whose run() always returns the given result."""
    async def provider(*a):
        return []

    engine = BacktestEngine(data_provider=provider)
    engine.run = AsyncMock(return_value=result)
    return engine


# ---------------------------------------------------------------------------
# _population_std
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPopulationStd:
    def test_empty(self):
        assert _population_std([]) == 0.0

    def test_single_value(self):
        assert _population_std([5.0]) == 0.0

    def test_constant_values(self):
        assert _population_std([3.0, 3.0, 3.0]) == pytest.approx(0.0, abs=1e-10)

    def test_known_std(self):
        values = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        result = _population_std(values)
        # Population std = 2.0
        assert result == pytest.approx(2.0)

    def test_two_values(self):
        result = _population_std([0.0, 10.0])
        assert result == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# StrategyOptimizer._compute_stability
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestComputeStability:
    def test_empty_trials(self):
        assert StrategyOptimizer._compute_stability([]) == 0.0

    def test_few_trials(self):
        trials = [{"score": 1.0}]
        assert StrategyOptimizer._compute_stability(trials) == 0.0

    def test_stable_top_quartile(self):
        # All top-quartile scores equal
        trials = [{"score": 2.0} for _ in range(4)] + [{"score": 0.5} for _ in range(12)]
        stability = StrategyOptimizer._compute_stability(trials)
        assert stability == pytest.approx(0.0, abs=1e-10)

    def test_unstable_top_quartile(self):
        # Need at least 8 trials so top quartile (2+) has variance
        trials = [
            {"score": 5.0}, {"score": 1.0},
            {"score": 3.0}, {"score": 0.5},
            {"score": 4.5}, {"score": 0.2},
            {"score": 4.8}, {"score": 0.1},
        ]
        trials.sort(key=lambda t: t["score"], reverse=True)
        stability = StrategyOptimizer._compute_stability(trials)
        assert stability > 0.0


# ---------------------------------------------------------------------------
# StrategyOptimizer.optimize
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestStrategyOptimizerOptimize:
    async def test_returns_optimization_result(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.5))
        optimizer = StrategyOptimizer(engine)
        config = _make_config()
        param_space = {"stop_loss_atr_multiplier": (1.0, 3.0)}

        result = await optimizer.optimize(config, param_space, n_trials=3)

        assert isinstance(result, OptimizationResult)
        assert result.metric == "sharpe_ratio"

    async def test_best_params_from_space(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=2.0))
        optimizer = StrategyOptimizer(engine)
        config = _make_config()
        param_space = {"sl_mult": (1.0, 3.0), "tp_mult": (2.0, 5.0)}

        result = await optimizer.optimize(config, param_space, n_trials=3)

        assert "sl_mult" in result.best_params
        assert "tp_mult" in result.best_params
        assert 1.0 <= result.best_params["sl_mult"] <= 3.0
        assert 2.0 <= result.best_params["tp_mult"] <= 5.0

    async def test_trials_list_populated(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.0))
        optimizer = StrategyOptimizer(engine)
        config = _make_config()

        result = await optimizer.optimize(config, {"sl": (1.0, 2.0)}, n_trials=5)

        assert len(result.trials) > 0
        for trial in result.trials:
            assert "params" in trial
            assert "score" in trial
            assert "trial_number" in trial

    async def test_trials_sorted_descending(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.0))
        optimizer = StrategyOptimizer(engine)
        config = _make_config()

        result = await optimizer.optimize(config, {"sl": (1.0, 2.0)}, n_trials=5)

        if len(result.trials) >= 2:
            scores = [t["score"] for t in result.trials]
            assert scores == sorted(scores, reverse=True)

    async def test_integer_param_space(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.0))
        optimizer = StrategyOptimizer(engine)
        config = _make_config()
        param_space = {"period": (10, 50)}  # both ints

        result = await optimizer.optimize(config, param_space, n_trials=3)
        assert isinstance(result.best_params["period"], int)

    async def test_categorical_param_space(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.0))
        optimizer = StrategyOptimizer(engine)
        config = _make_config()
        param_space = {"strategy_variant": ["conservative", "aggressive"]}

        result = await optimizer.optimize(config, param_space, n_trials=3)
        assert result.best_params["strategy_variant"] in ["conservative", "aggressive"]

    async def test_stability_score_is_float(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.0))
        optimizer = StrategyOptimizer(engine)
        result = await optimizer.optimize(_make_config(), {"sl": (1.0, 2.0)}, n_trials=5)
        assert isinstance(result.stability_score, float)

    async def test_study_attribute_present(self):
        import optuna
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.0))
        optimizer = StrategyOptimizer(engine)
        result = await optimizer.optimize(_make_config(), {"sl": (1.0, 2.0)}, n_trials=3)
        assert isinstance(result.study, optuna.Study)

    async def test_custom_metric(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.5))
        optimizer = StrategyOptimizer(engine)
        result = await optimizer.optimize(
            _make_config(), {"sl": (1.0, 2.0)}, n_trials=3, metric="profit_factor"
        )
        assert result.metric == "profit_factor"
        assert result.best_score == pytest.approx(1.8)

    async def test_invalid_metric_raises(self):
        engine = _make_engine_returning(_make_dummy_result())
        optimizer = StrategyOptimizer(engine)
        with pytest.raises(ValueError):
            await optimizer.optimize(
                _make_config(), {"sl": (1.0, 2.0)}, n_trials=2, metric="nonexistent_metric"
            )

    async def test_invalid_param_space_raises(self):
        engine = _make_engine_returning(_make_dummy_result())
        optimizer = StrategyOptimizer(engine)
        with pytest.raises(ValueError):
            await optimizer.optimize(
                _make_config(), {"sl": "invalid_space"}, n_trials=1
            )


# ---------------------------------------------------------------------------
# StrategyOptimizer.walk_forward_optimize
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestWalkForwardOptimize:
    async def test_returns_walk_forward_result(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.5))
        optimizer = StrategyOptimizer(engine)
        config = _make_config(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        )

        result = await optimizer.walk_forward_optimize(
            config, {"sl": (1.0, 2.0)}, n_splits=2, n_trials_per_split=3
        )

        assert isinstance(result, WalkForwardResult)
        assert result.n_splits >= 1

    async def test_splits_equal_n_splits(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.0))
        optimizer = StrategyOptimizer(engine)
        config = _make_config(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        )

        result = await optimizer.walk_forward_optimize(
            config, {"sl": (1.0, 2.0)}, n_splits=3, n_trials_per_split=3
        )

        assert result.n_splits == len(result.in_sample_results)
        assert result.n_splits == len(result.out_of_sample_results)

    async def test_best_params_per_split_length(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.0))
        optimizer = StrategyOptimizer(engine)
        config = _make_config(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        )

        result = await optimizer.walk_forward_optimize(
            config, {"sl": (1.0, 2.0)}, n_splits=2, n_trials_per_split=3
        )

        assert len(result.best_params_per_split) == result.n_splits

    async def test_avg_oos_score_computed(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=2.0))
        optimizer = StrategyOptimizer(engine)
        config = _make_config(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        )

        result = await optimizer.walk_forward_optimize(
            config, {"sl": (1.0, 2.0)}, n_splits=2, n_trials_per_split=3
        )

        assert math.isfinite(result.avg_out_of_sample_score)

    async def test_stability_score_is_float(self):
        engine = _make_engine_returning(_make_dummy_result(sharpe=1.0))
        optimizer = StrategyOptimizer(engine)
        config = _make_config(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        )

        result = await optimizer.walk_forward_optimize(
            config, {"sl": (1.0, 2.0)}, n_splits=2, n_trials_per_split=3
        )

        assert isinstance(result.stability_score, float)
        assert result.stability_score >= 0.0
