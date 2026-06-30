"""Strategy Registry - singleton registry for all trading strategies."""

import structlog

from forex_trading.ai.agents.base import MarketRegime
from forex_trading.strategy.engine import BaseStrategy, StrategyType
from forex_trading.strategy.strategies.asian_range import AsianRangeStrategy
from forex_trading.strategy.strategies.breakout import BreakoutStrategy
from forex_trading.strategy.strategies.london_open import LondonOpenStrategy
from forex_trading.strategy.strategies.mean_reversion import MeanReversionStrategy
from forex_trading.strategy.strategies.pullback import PullbackStrategy
from forex_trading.strategy.strategies.scalping import ScalpingStrategy
from forex_trading.strategy.strategies.trend_following import TrendFollowingStrategy

logger = structlog.get_logger()


class StrategyRegistry:
    """
    Singleton registry for all strategies.

    Auto-registers all built-in strategies on construction.
    Supports regime-aware strategy selection with optional performance weighting.
    """

    def __init__(self) -> None:
        self._strategies: dict[StrategyType, BaseStrategy] = {}
        self._register_builtin_strategies()

    def _register_builtin_strategies(self) -> None:
        builtins: list[BaseStrategy] = [
            TrendFollowingStrategy(),
            PullbackStrategy(),
            BreakoutStrategy(),
            MeanReversionStrategy(),
            ScalpingStrategy(),
            LondonOpenStrategy(),
            AsianRangeStrategy(),
        ]
        for strategy in builtins:
            self.register(strategy)

    def register(self, strategy: BaseStrategy) -> None:
        if strategy.strategy_type in self._strategies:
            logger.warning(
                "strategy_overwritten",
                strategy_type=strategy.strategy_type.value,
                old_name=self._strategies[strategy.strategy_type].name,
                new_name=strategy.name,
            )
        self._strategies[strategy.strategy_type] = strategy
        logger.info("strategy_registered", name=strategy.name, type=strategy.strategy_type.value)

    def get(self, strategy_type: StrategyType) -> BaseStrategy | None:
        return self._strategies.get(strategy_type)

    def all(self) -> list[BaseStrategy]:
        return list(self._strategies.values())

    def for_regime(self, regime: MarketRegime) -> list[BaseStrategy]:
        return [s for s in self._strategies.values() if regime in s.get_optimal_regime()]

    def get_best_for_regime(
        self,
        regime: MarketRegime,
        performance_data: dict[str, dict[str, float]],
    ) -> BaseStrategy | None:
        """
        Return the highest-scoring strategy for the given regime.

        performance_data maps strategy name to a dict with keys
        'win_rate' (0-1) and 'profit_factor' (>0).  Missing entries
        default to win_rate=0.5, profit_factor=1.0.
        """
        candidates = self.for_regime(regime)
        if not candidates:
            return None

        best: BaseStrategy | None = None
        best_score = -1.0

        for strategy in candidates:
            perf = performance_data.get(strategy.name, {})
            win_rate = float(perf.get("win_rate", 0.5))
            profit_factor = float(perf.get("profit_factor", 1.0))
            score = win_rate * profit_factor
            if score > best_score:
                best_score = score
                best = strategy

        logger.info(
            "best_strategy_selected",
            regime=regime.value,
            strategy=best.name if best else None,
            score=best_score,
        )
        return best
