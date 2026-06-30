"""Strategy Engine - strategy selection, validation, and lifecycle management."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import structlog

from forex_trading.ai.agents.base import MarketContext, MarketRegime, SignalDirection

logger = structlog.get_logger()


class StrategyType(str, Enum):
    """Available strategy types."""
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    SCALPING = "scalping"
    BREAKOUT = "breakout"
    GRID_TRADING = "grid_trading"
    SENTIMENT_FADE = "sentiment_fade"
    PULLBACK = "pullback"
    MOMENTUM = "momentum"
    SWING_TRADING = "swing_trading"
    LONDON_OPEN = "london_open"
    NEW_YORK_OPEN = "new_york_open"
    ASIAN_RANGE = "asian_range"


@dataclass
class StrategyParameters:
    """Parameters for a strategy."""
    stop_loss_pips: float = 50.0
    take_profit_pips: float = 100.0
    trailing_stop_pips: float = 30.0
    max_holding_time_minutes: int = 480
    entry_threshold: float = 0.7
    exit_threshold: float = 0.3
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeSignal:
    """Trade signal ready for execution."""
    signal_id: UUID = field(default_factory=uuid4)
    strategy: StrategyType = StrategyType.TREND_FOLLOWING
    symbol: str = ""
    direction: SignalDirection = SignalDirection.NEUTRAL
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    confidence: float = 0.0
    parameters: StrategyParameters = field(default_factory=StrategyParameters)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ValidationResult:
    """Result of trade validation."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TradeOutcome:
    """Outcome of a completed trade."""
    trade_id: UUID
    pnl: float
    pnl_pips: float
    duration_minutes: float
    hit_stop_loss: bool
    hit_take_profit: bool
    exit_reason: str


class BaseStrategy(ABC):
    """Base class for all trading strategies."""

    def __init__(self, strategy_type: StrategyType, name: str) -> None:
        self.strategy_type = strategy_type
        self.name = name
        self._parameters: dict[str, StrategyParameters] = {}

    @abstractmethod
    def get_optimal_regime(self) -> list[MarketRegime]:
        """Get market regimes where this strategy performs best."""
        pass

    @abstractmethod
    def validate_signal(self, context: MarketContext, signal: TradeSignal) -> ValidationResult:
        """Validate a trade signal against strategy rules."""
        pass

    def get_parameters(self, symbol: str) -> StrategyParameters:
        """Get parameters for a symbol."""
        return self._parameters.get(symbol, StrategyParameters())

    def set_parameters(self, symbol: str, params: StrategyParameters) -> None:
        """Set parameters for a symbol."""
        self._parameters[symbol] = params


class StrategyEngine:
    """
    Strategy Engine - selects and validates trading strategies.

    Responsibilities:
    - Match market regimes to optimal strategies
    - Manage strategy lifecycle and parameters
    - Validate trade signals against strategy rules
    - Track strategy performance
    """

    def __init__(self) -> None:
        self._strategies: dict[StrategyType, BaseStrategy] = {}
        self._performance: dict[StrategyType, dict[str, float]] = {}

    def register_strategy(self, strategy: BaseStrategy) -> None:
        """Register a trading strategy."""
        self._strategies[strategy.strategy_type] = strategy
        logger.info("strategy_registered", strategy=strategy.name, type=strategy.strategy_type.value)

    def get_strategy(self, strategy_type: StrategyType) -> BaseStrategy | None:
        """Get strategy by type."""
        return self._strategies.get(strategy_type)

    async def select_strategy(
        self,
        regime: MarketRegime,
        context: MarketContext,
    ) -> BaseStrategy | None:
        """
        Select optimal strategy for current market conditions.

        Args:
            regime: Current market regime
            context: Market context

        Returns:
            Best matching strategy or None
        """
        candidates = []

        for strategy in self._strategies.values():
            optimal_regimes = strategy.get_optimal_regime()
            if regime in optimal_regimes:
                candidates.append(strategy)

        if not candidates:
            # Fallback to first available strategy
            return next(iter(self._strategies.values()), None)

        # Select based on historical performance
        best_strategy = None
        best_score = -1.0

        for strategy in candidates:
            score = self._get_strategy_score(strategy)
            if score > best_score:
                best_score = score
                best_strategy = strategy

        logger.info(
            "strategy_selected",
            strategy=best_strategy.name if best_strategy else None,
            regime=regime.value,
            symbol=context.symbol,
        )

        return best_strategy

    async def validate_trade(
        self,
        signal: TradeSignal,
        strategy: BaseStrategy,
    ) -> ValidationResult:
        """
        Validate a trade signal against strategy rules.

        Args:
            signal: Trade signal to validate
            strategy: Strategy to validate against

        Returns:
            ValidationResult with errors and warnings
        """
        # Basic validation
        errors = []
        warnings = []

        if signal.entry_price <= 0:
            errors.append("Invalid entry price")

        if signal.stop_loss <= 0:
            errors.append("Invalid stop loss")

        if signal.direction == SignalDirection.NEUTRAL:
            errors.append("Cannot execute neutral signal")

        # Strategy-specific validation
        strategy_validation = strategy.validate_signal(None, signal)
        errors.extend(strategy_validation.errors)
        warnings.extend(strategy_validation.warnings)

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    async def record_outcome(self, trade_id: UUID, outcome: TradeOutcome) -> None:
        """Record trade outcome for performance tracking."""
        logger.info(
            "trade_outcome_recorded",
            trade_id=str(trade_id),
            pnl=outcome.pnl,
            duration=outcome.duration_minutes,
        )

    def _get_strategy_score(self, strategy: BaseStrategy) -> float:
        """Calculate strategy score based on performance."""
        perf = self._performance.get(strategy.strategy_type, {})
        win_rate = perf.get("win_rate", 0.5)
        profit_factor = perf.get("profit_factor", 1.0)
        return win_rate * profit_factor
