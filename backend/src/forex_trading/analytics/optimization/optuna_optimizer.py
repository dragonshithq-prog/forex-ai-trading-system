"""Strategy parameter optimization using Optuna with walk-forward validation."""

from __future__ import annotations

import asyncio
import copy
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import optuna
import structlog

from forex_trading.analytics.backtesting.engine import BacktestConfig, BacktestEngine, BacktestResult

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger = structlog.get_logger()


@dataclass
class OptimizationResult:
    best_params: dict
    best_score: float
    metric: str
    trials: list[dict]  # [{"params": {...}, "score": float, "trial_number": int}]
    study: optuna.Study
    stability_score: float  # std deviation of top-quartile trial scores; lower = more stable
    n_trials: int
    config: BacktestConfig


@dataclass
class WalkForwardResult:
    in_sample_results: list[OptimizationResult]
    out_of_sample_results: list[BacktestResult]
    n_splits: int
    avg_out_of_sample_score: float
    stability_score: float  # consistency of out-of-sample performance
    best_params_per_split: list[dict]


class StrategyOptimizer:
    """
    Optimize strategy parameters using Optuna TPE sampler with optional pruning.

    Walk-forward optimization runs in-sample optimization then evaluates the
    best parameters on subsequent out-of-sample windows, giving an honest
    measure of parameter robustness.
    """

    def __init__(self, backtest_engine: BacktestEngine) -> None:
        self._engine = backtest_engine

    async def optimize(
        self,
        config: BacktestConfig,
        param_space: dict,
        n_trials: int = 100,
        metric: str = "sharpe_ratio",
        prune_poor_trials: bool = True,
    ) -> OptimizationResult:
        """
        Optimize strategy parameters over the full config date range.

        Args:
            config: Backtest configuration (date range, symbol, etc.)
            param_space: Mapping of param_name -> (low, high) float range or
                         list of categorical values.
            n_trials: Number of Optuna trials.
            metric: BacktestResult attribute to maximize.
            prune_poor_trials: Enable MedianPruner to discard clearly poor trials.

        Returns:
            OptimizationResult with best params, score, and all trial data.
        """
        logger.info(
            "optimization_started",
            strategy=config.strategy_type,
            n_trials=n_trials,
            metric=metric,
        )

        objective = self._create_objective(config, param_space, metric)
        sampler = optuna.samplers.TPESampler(seed=42)
        pruner = optuna.pruners.MedianPruner(n_startup_trials=5) if prune_poor_trials else optuna.pruners.NopPruner()

        study = optuna.create_study(
            direction="maximize",
            sampler=sampler,
            pruner=pruner,
        )

        # Run trials - use asyncio thread pool to keep async contract
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: study.optimize(objective, n_trials=n_trials, show_progress_bar=False),
        )

        trials = [
            {
                "trial_number": t.number,
                "params": t.params,
                "score": t.value if t.value is not None else float("-inf"),
            }
            for t in study.trials
            if t.value is not None
        ]
        trials.sort(key=lambda x: x["score"], reverse=True)

        stability = self._compute_stability(trials)

        best_params = study.best_params
        best_score = study.best_value if study.best_value is not None else 0.0

        logger.info(
            "optimization_completed",
            best_score=best_score,
            best_params=best_params,
            n_trials_completed=len(trials),
        )

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            metric=metric,
            trials=trials,
            study=study,
            stability_score=stability,
            n_trials=len(trials),
            config=config,
        )

    def _create_objective(
        self,
        config: BacktestConfig,
        param_space: dict,
        metric: str,
    ) -> Callable[[optuna.Trial], float]:
        """Create an Optuna objective function that runs a backtest per trial."""

        engine = self._engine

        def objective(trial: optuna.Trial) -> float:
            params = {}
            for name, space in param_space.items():
                if isinstance(space, (list, tuple)) and len(space) == 2 and all(
                    isinstance(v, (int, float)) for v in space
                ):
                    low, high = space
                    if isinstance(low, int) and isinstance(high, int):
                        params[name] = trial.suggest_int(name, low, high)
                    else:
                        params[name] = trial.suggest_float(name, float(low), float(high))
                elif isinstance(space, list):
                    params[name] = trial.suggest_categorical(name, space)
                else:
                    raise ValueError(f"Invalid param_space entry for '{name}': {space!r}")

            trial_config = copy.deepcopy(config)
            trial_config.parameters = {**config.parameters, **params}

            try:
                loop = asyncio.new_event_loop()
                result: BacktestResult = loop.run_until_complete(engine.run(trial_config))
                loop.close()
            except Exception as exc:
                logger.debug("trial_failed", error=str(exc))
                raise optuna.exceptions.TrialPruned()

            score = getattr(result, metric, None)
            if score is None:
                raise ValueError(f"BacktestResult has no attribute '{metric}'")

            # Guard against NaN/inf
            if not math.isfinite(score):
                score = 0.0

            return float(score)

        return objective

    async def walk_forward_optimize(
        self,
        config: BacktestConfig,
        param_space: dict,
        n_splits: int = 5,
        n_trials_per_split: int = 50,
        metric: str = "sharpe_ratio",
    ) -> WalkForwardResult:
        """
        Walk-forward optimization with time-series cross-validation.

        The total date range is divided into n_splits+1 windows. Each iteration
        uses windows 0..i as in-sample and window i+1 as out-of-sample.

        Args:
            config: Full backtest config spanning the entire date range.
            param_space: Parameter search space.
            n_splits: Number of in-sample/out-of-sample splits.
            n_trials_per_split: Optuna trials per in-sample window.
            metric: Metric to optimize and measure out-of-sample.

        Returns:
            WalkForwardResult with all split results and overall stability.
        """
        total_days = (config.end_date - config.start_date).days
        window_days = total_days // (n_splits + 1)

        in_sample_results: list[OptimizationResult] = []
        out_of_sample_results: list[BacktestResult] = []
        best_params_per_split: list[dict] = []

        logger.info(
            "walk_forward_started",
            n_splits=n_splits,
            window_days=window_days,
            total_days=total_days,
        )

        for i in range(n_splits):
            in_sample_start = config.start_date
            in_sample_end = config.start_date + timedelta(days=window_days * (i + 1))
            oos_start = in_sample_end
            oos_end = min(oos_start + timedelta(days=window_days), config.end_date)

            if oos_end <= oos_start:
                break

            in_sample_config = copy.deepcopy(config)
            in_sample_config.start_date = in_sample_start
            in_sample_config.end_date = in_sample_end

            opt_result = await self.optimize(
                in_sample_config,
                param_space,
                n_trials=n_trials_per_split,
                metric=metric,
            )
            in_sample_results.append(opt_result)
            best_params_per_split.append(opt_result.best_params)

            # Out-of-sample evaluation with best params
            oos_config = copy.deepcopy(config)
            oos_config.start_date = oos_start
            oos_config.end_date = oos_end
            oos_config.parameters = {**config.parameters, **opt_result.best_params}

            oos_result = await self._engine.run(oos_config)
            out_of_sample_results.append(oos_result)

            logger.info(
                "walk_forward_split_done",
                split=i + 1,
                in_sample_score=opt_result.best_score,
                oos_score=getattr(oos_result, metric, 0.0),
            )

        oos_scores = [getattr(r, metric, 0.0) for r in out_of_sample_results]
        avg_oos = sum(oos_scores) / len(oos_scores) if oos_scores else 0.0
        stability = _population_std(oos_scores)

        return WalkForwardResult(
            in_sample_results=in_sample_results,
            out_of_sample_results=out_of_sample_results,
            n_splits=len(in_sample_results),
            avg_out_of_sample_score=avg_oos,
            stability_score=stability,
            best_params_per_split=best_params_per_split,
        )

    @staticmethod
    def _compute_stability(trials: list[dict]) -> float:
        """Std deviation of top-quartile scores (lower = more stable/robust)."""
        if len(trials) < 4:
            return 0.0
        top_n = max(1, len(trials) // 4)
        top_scores = [t["score"] for t in trials[:top_n]]
        return _population_std(top_scores)


def _population_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)
