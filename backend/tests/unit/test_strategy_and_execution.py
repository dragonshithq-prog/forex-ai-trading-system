"""Unit tests for Strategy implementations, StrategyRegistry, ExecutionEngine, and PositionSizer."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from forex_trading.ai.agents.base import MarketContext, MarketRegime, SignalDirection
from forex_trading.strategy.engine import (
    StrategyParameters,
    StrategyType,
    TradeSignal,
    StrategyEngine,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_signal(
    direction: SignalDirection = SignalDirection.LONG,
    entry: float = 1.1000,
    sl: float = 1.0950,
    tp: float = 1.1100,
    metadata: dict | None = None,
    confidence: float = 0.8,
) -> TradeSignal:
    params = StrategyParameters(
        stop_loss_pips=50.0,
        take_profit_pips=100.0,
        metadata=metadata or {},
    )
    return TradeSignal(
        strategy=StrategyType.TREND_FOLLOWING,
        symbol="EURUSD",
        direction=direction,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        confidence=confidence,
        parameters=params,
    )


def _make_context(regime: MarketRegime = MarketRegime.TRENDING_UP) -> MarketContext:
    return MarketContext(symbol="EURUSD", timeframe="H1", regime=regime)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 2 – StrategyType enum
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestStrategyTypeEnum:
    def test_new_values_present(self):
        values = {e.value for e in StrategyType}
        assert "pullback" in values
        assert "momentum" in values
        assert "swing_trading" in values
        assert "london_open" in values
        assert "new_york_open" in values
        assert "asian_range" in values

    def test_original_values_preserved(self):
        assert StrategyType.TREND_FOLLOWING.value == "trend_following"
        assert StrategyType.MEAN_REVERSION.value == "mean_reversion"
        assert StrategyType.SCALPING.value == "scalping"
        assert StrategyType.BREAKOUT.value == "breakout"


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1a – TrendFollowingStrategy
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestTrendFollowingStrategy:
    @pytest.fixture
    def strategy(self):
        from forex_trading.strategy.strategies.trend_following import TrendFollowingStrategy
        return TrendFollowingStrategy()

    def test_optimal_regime(self, strategy):
        regimes = strategy.get_optimal_regime()
        assert MarketRegime.TRENDING_UP in regimes
        assert MarketRegime.TRENDING_DOWN in regimes

    def test_valid_long_signal(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1000, sl=1.0925, tp=1.1150,
            metadata={
                "ema20": 1.1010, "ema50": 1.0990, "ema200": 1.0900,
                "adx": 28.0,
            },
        )
        ctx = _make_context(MarketRegime.TRENDING_UP)
        result = strategy.validate_signal(ctx, signal)
        assert result.is_valid, result.errors

    def test_rejects_bad_ema_alignment(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            metadata={"ema20": 1.0900, "ema50": 1.0990, "ema200": 1.1050, "adx": 30.0},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("EMA alignment" in e for e in result.errors)

    def test_rejects_low_adx(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1000, sl=1.0925, tp=1.1150,
            metadata={"ema20": 1.1010, "ema50": 1.0990, "ema200": 1.0900, "adx": 15.0},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("ADX" in e for e in result.errors)

    def test_rejects_poor_rr(self, strategy):
        # sl=5 pips, tp=5 pips → RR=1 < 2
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1000, sl=1.0995, tp=1.1005,
            metadata={"ema20": 1.1010, "ema50": 1.0990, "ema200": 1.0900, "adx": 30.0},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("R:R" in e for e in result.errors)

    def test_rejects_direction_regime_mismatch(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.SHORT,
            entry=1.1000, sl=1.1050, tp=1.0900,
            metadata={"ema20": 1.1010, "ema50": 1.0990, "ema200": 1.0900, "adx": 30.0},
        )
        ctx = _make_context(MarketRegime.TRENDING_UP)
        result = strategy.validate_signal(ctx, signal)
        assert not result.is_valid
        assert any("TRENDING_UP" in e for e in result.errors)

    def test_rejects_resistance_proximity(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1000, sl=1.0850, tp=1.1300,
            metadata={
                "ema20": 1.1010, "ema50": 1.0990, "ema200": 1.0900,
                "adx": 30.0,
                "major_resistance": 1.1003,  # only 3 pips away
            },
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("resistance" in e.lower() for e in result.errors)

    def test_warns_missing_ema(self, strategy):
        signal = _make_signal(entry=1.1000, sl=1.0850, tp=1.1300, metadata={"adx": 30.0})
        result = strategy.validate_signal(None, signal)
        assert result.is_valid
        assert any("EMA" in w for w in result.warnings)

    def test_zero_entry_price(self, strategy):
        signal = _make_signal(entry=0.0, sl=1.0950, tp=1.1100)
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1b – PullbackStrategy
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestPullbackStrategy:
    @pytest.fixture
    def strategy(self):
        from forex_trading.strategy.strategies.pullback import PullbackStrategy
        return PullbackStrategy()

    def test_strategy_type(self, strategy):
        assert strategy.strategy_type == StrategyType.PULLBACK

    def test_optimal_regimes(self, strategy):
        assert MarketRegime.TRENDING_UP in strategy.get_optimal_regime()

    def test_valid_pullback(self, strategy):
        # Entry near EMA20 (1.1000 vs 1.1005 – within 10 pips)
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1000, sl=1.0940, tp=1.1090,
            metadata={
                "ema20": 1.1005, "ema50": 1.0970, "ema200": 1.0850,
                "rsi": 45.0,
            },
        )
        result = strategy.validate_signal(None, signal)
        assert result.is_valid, result.errors

    def test_rejects_not_near_ema(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1100, sl=1.1040, tp=1.1190,
            metadata={"ema20": 1.1000, "ema50": 1.0970, "ema200": 1.0850, "rsi": 50.0},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("pullback" in e.lower() for e in result.errors)

    def test_rejects_overbought_rsi_long(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1000, sl=1.0940, tp=1.1090,
            metadata={"ema20": 1.1005, "ema50": 1.0970, "ema200": 1.0850, "rsi": 75.0},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("RSI" in e for e in result.errors)

    def test_rejects_poor_rr(self, strategy):
        # RR = 3/5 = 0.6 < 1.5
        signal = _make_signal(
            entry=1.1000, sl=1.0995, tp=1.1003,
            metadata={"ema20": 1.1005, "ema50": 1.0970, "ema200": 1.0850, "rsi": 50.0},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("R:R" in e for e in result.errors)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1c – BreakoutStrategy
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestBreakoutStrategy:
    @pytest.fixture
    def strategy(self):
        from forex_trading.strategy.strategies.breakout import BreakoutStrategy
        return BreakoutStrategy()

    def test_optimal_regimes(self, strategy):
        regimes = strategy.get_optimal_regime()
        assert MarketRegime.TRENDING_UP in regimes
        assert MarketRegime.VOLATILE in regimes

    def test_valid_long_breakout(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1010,
            metadata={
                "resistance_level": 1.1000,
                "current_volume": 1500, "avg_volume_20": 1000,
                "current_spread_pips": 1.0, "avg_spread_pips": 1.2,
                "confirmation_type": "direct",
            },
        )
        result = strategy.validate_signal(None, signal)
        assert result.is_valid, result.errors

    def test_rejects_entry_below_resistance(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.0990,
            metadata={"resistance_level": 1.1000, "current_volume": 1500, "avg_volume_20": 1000},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("resistance" in e.lower() for e in result.errors)

    def test_rejects_low_volume(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1010,
            metadata={
                "resistance_level": 1.1000,
                "current_volume": 800, "avg_volume_20": 1000,
                "confirmation_type": "direct",
            },
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("volume" in e.lower() for e in result.errors)

    def test_rejects_excess_spread(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1010,
            metadata={
                "resistance_level": 1.1000,
                "current_volume": 1500, "avg_volume_20": 1000,
                "current_spread_pips": 5.0, "avg_spread_pips": 1.5,
                "confirmation_type": "direct",
            },
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("spread" in e.lower() for e in result.errors)

    def test_rejects_retest_too_far(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1020,  # 20 pips above broken resistance → too far for retest
            metadata={
                "resistance_level": 1.1000,
                "current_volume": 1500, "avg_volume_20": 1000,
                "confirmation_type": "retest",
            },
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("retest" in e.lower() for e in result.errors)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1d – MeanReversionStrategy
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestMeanReversionStrategy:
    @pytest.fixture
    def strategy(self):
        from forex_trading.strategy.strategies.mean_reversion import MeanReversionStrategy
        return MeanReversionStrategy()

    def test_optimal_regime(self, strategy):
        assert strategy.get_optimal_regime() == [MarketRegime.RANGING]

    def test_valid_long_at_lower_band(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.0990, sl=1.0970, tp=1.1020,
            metadata={
                "bb_upper": 1.1030, "bb_lower": 1.1000, "bb_middle": 1.1015,
                "rsi": 27.0,
            },
        )
        ctx = _make_context(MarketRegime.RANGING)
        result = strategy.validate_signal(ctx, signal)
        assert result.is_valid, result.errors

    def test_rejects_non_ranging_regime(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.0990,
            metadata={"bb_upper": 1.1030, "bb_lower": 1.1000, "bb_middle": 1.1015, "rsi": 27.0},
        )
        ctx = _make_context(MarketRegime.TRENDING_UP)
        result = strategy.validate_signal(ctx, signal)
        assert not result.is_valid
        assert any("RANGING" in e for e in result.errors)

    def test_rejects_entry_above_lower_band(self, strategy):
        # Entry at 1.1010 is ABOVE bb_lower 1.1000 — not a band extreme for LONG
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1010, sl=1.0970, tp=1.1020,
            metadata={"bb_upper": 1.1030, "bb_lower": 1.1000, "bb_middle": 1.1015, "rsi": 27.0},
        )
        ctx = _make_context(MarketRegime.RANGING)
        result = strategy.validate_signal(ctx, signal)
        assert not result.is_valid
        assert any("band" in e.lower() for e in result.errors)

    def test_rejects_rsi_not_oversold(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.0990, sl=1.0970, tp=1.1020,
            metadata={"bb_upper": 1.1030, "bb_lower": 1.1000, "bb_middle": 1.1015, "rsi": 45.0},
        )
        ctx = _make_context(MarketRegime.RANGING)
        result = strategy.validate_signal(ctx, signal)
        assert not result.is_valid
        assert any("RSI" in e for e in result.errors)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1e – ScalpingStrategy
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestScalpingStrategy:
    @pytest.fixture
    def strategy(self):
        from forex_trading.strategy.strategies.scalping import ScalpingStrategy
        return ScalpingStrategy()

    def test_valid_scalp(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            metadata={
                "utc_hour": 13,
                "current_spread_pips": 1.0,
                "bid_volume": 800, "ask_volume": 400,
            },
        )
        result = strategy.validate_signal(None, signal)
        assert result.is_valid, result.errors

    def test_rejects_off_session(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            metadata={"utc_hour": 4, "current_spread_pips": 1.0, "bid_volume": 800, "ask_volume": 400},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("overlap" in e.lower() for e in result.errors)

    def test_rejects_wide_spread(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            metadata={"utc_hour": 13, "current_spread_pips": 2.0, "bid_volume": 800, "ask_volume": 400},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("spread" in e.lower() for e in result.errors)

    def test_rejects_wrong_order_flow_long(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            metadata={
                "utc_hour": 13, "current_spread_pips": 1.0,
                "bid_volume": 200, "ask_volume": 800,  # sell pressure
            },
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("imbalance" in e.lower() for e in result.errors)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1f – LondonOpenStrategy
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestLondonOpenStrategy:
    @pytest.fixture
    def strategy(self):
        from forex_trading.strategy.strategies.london_open import LondonOpenStrategy
        return LondonOpenStrategy()

    def test_strategy_type(self, strategy):
        assert strategy.strategy_type == StrategyType.LONDON_OPEN

    def test_valid_long_breakout_asian_high(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1010,
            metadata={
                "utc_hour": 7,
                "asian_high": 1.1005,
                "asian_low": 1.0980,
            },
        )
        result = strategy.validate_signal(None, signal)
        assert result.is_valid, result.errors

    def test_rejects_wrong_time(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1010,
            metadata={"utc_hour": 12, "asian_high": 1.1005, "asian_low": 1.0980},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("07:00" in e for e in result.errors)

    def test_rejects_entry_not_above_asian_high(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.0990,
            metadata={"utc_hour": 8, "asian_high": 1.1005, "asian_low": 1.0980},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("Asian high" in e for e in result.errors)

    def test_rejects_invalid_asian_range(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1010,
            metadata={"utc_hour": 7, "asian_high": 1.0980, "asian_low": 1.1005},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("Invalid Asian range" in e for e in result.errors)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1g – AsianRangeStrategy
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestAsianRangeStrategy:
    @pytest.fixture
    def strategy(self):
        from forex_trading.strategy.strategies.asian_range import AsianRangeStrategy
        return AsianRangeStrategy()

    def test_strategy_type(self, strategy):
        assert strategy.strategy_type == StrategyType.ASIAN_RANGE

    def test_optimal_regimes(self, strategy):
        regimes = strategy.get_optimal_regime()
        assert MarketRegime.RANGING in regimes
        assert MarketRegime.LOW_VOLATILITY in regimes

    def test_valid_long_at_range_low(self, strategy):
        # Entry 1.0985 is within 5 pips of range_low 1.0985
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.0985, sl=1.0965, tp=1.1010,
            metadata={"utc_hour": 3, "range_high": 1.1015, "range_low": 1.0985},
        )
        result = strategy.validate_signal(None, signal)
        assert result.is_valid, result.errors

    def test_rejects_outside_tokyo_hours(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.0985,
            metadata={"utc_hour": 10, "range_high": 1.1015, "range_low": 1.0985},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("Tokyo" in e for e in result.errors)

    def test_rejects_entry_far_from_range_low(self, strategy):
        # Entry 20 pips above range_low → too far
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.1005,
            metadata={"utc_hour": 3, "range_high": 1.1015, "range_low": 1.0985},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("range low" in e.lower() for e in result.errors)

    def test_rejects_invalid_range(self, strategy):
        signal = _make_signal(
            direction=SignalDirection.LONG,
            entry=1.0985,
            metadata={"utc_hour": 3, "range_high": 1.0980, "range_low": 1.1015},
        )
        result = strategy.validate_signal(None, signal)
        assert not result.is_valid
        assert any("Invalid range" in e for e in result.errors)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 3 – StrategyRegistry
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestStrategyRegistry:
    @pytest.fixture
    def registry(self):
        from forex_trading.strategy.registry.strategy_registry import StrategyRegistry
        return StrategyRegistry()

    def test_registers_all_builtin_strategies(self, registry):
        all_strategies = registry.all()
        names = {s.name for s in all_strategies}
        assert "Trend Following" in names
        assert "Pullback" in names
        assert "Breakout" in names
        assert "Mean Reversion" in names
        assert "Scalping" in names
        assert "London Open" in names
        assert "Asian Range" in names

    def test_get_by_type(self, registry):
        strategy = registry.get(StrategyType.TREND_FOLLOWING)
        assert strategy is not None
        assert strategy.name == "Trend Following"

    def test_get_unknown_type_returns_none(self, registry):
        assert registry.get(StrategyType.GRID_TRADING) is None

    def test_for_regime_trending(self, registry):
        strategies = registry.for_regime(MarketRegime.TRENDING_UP)
        names = {s.name for s in strategies}
        assert "Trend Following" in names
        assert "Pullback" in names
        assert "Breakout" in names
        # Mean reversion should NOT be in trending regime
        assert "Mean Reversion" not in names

    def test_for_regime_ranging(self, registry):
        strategies = registry.for_regime(MarketRegime.RANGING)
        names = {s.name for s in strategies}
        assert "Mean Reversion" in names
        assert "Asian Range" in names

    def test_get_best_for_regime_uses_performance(self, registry):
        performance = {
            "Trend Following": {"win_rate": 0.7, "profit_factor": 1.8},
            "Pullback": {"win_rate": 0.6, "profit_factor": 1.5},
            "Breakout": {"win_rate": 0.5, "profit_factor": 1.2},
        }
        best = registry.get_best_for_regime(MarketRegime.TRENDING_UP, performance)
        assert best is not None
        assert best.name == "Trend Following"

    def test_get_best_for_regime_defaults_when_no_perf(self, registry):
        best = registry.get_best_for_regime(MarketRegime.RANGING, {})
        assert best is not None

    def test_get_best_for_regime_no_candidates(self, registry):
        # LOW_VOLATILITY only matches Asian Range
        best = registry.get_best_for_regime(MarketRegime.LOW_VOLATILITY, {})
        assert best is not None
        assert best.name == "Asian Range"

    def test_register_custom_strategy(self, registry):
        from forex_trading.strategy.strategies.trend_following import TrendFollowingStrategy
        custom = TrendFollowingStrategy()
        custom.name = "Custom Trend"
        registry.register(custom)
        assert registry.get(StrategyType.TREND_FOLLOWING).name == "Custom Trend"


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 5 – PositionSizer
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestPositionSizer:
    @pytest.fixture
    def sizer(self):
        from forex_trading.execution.services.position_sizer import PositionSizer
        return PositionSizer()

    def test_basic_eurusd_size(self, sizer):
        result = sizer.calculate_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            entry_price=1.1000,
            stop_loss_price=1.0950,
            symbol="EURUSD",
        )
        # $10k * 1% = $100 risk; SL = 50 pips at $10/pip → 0.20 lots
        assert result.lots == pytest.approx(0.20, abs=0.01)
        assert result.risk_amount == pytest.approx(100.0, abs=5.0)
        assert result.risk_pct == pytest.approx(1.0, abs=0.1)
        assert result.pip_value == pytest.approx(10.0)

    def test_usdjpy_size(self, sizer):
        result = sizer.calculate_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            entry_price=145.00,
            stop_loss_price=144.50,
            symbol="USDJPY",
        )
        assert result.lots > 0

    def test_minimum_lot_size(self, sizer):
        result = sizer.calculate_size(
            account_balance=100.0,
            risk_pct=0.01,  # tiny risk amount
            entry_price=1.1000,
            stop_loss_price=1.0000,  # 1000 pip SL
            symbol="EURUSD",
        )
        assert result.lots == 0.01

    def test_leverage_ceiling(self, sizer):
        # 100:1 leverage with $10k balance → max notional = $1,000,000 → not a binding ceiling
        # Use extreme risk_pct to verify the leverage ceiling is computed without crashing
        result = sizer.calculate_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            entry_price=1.1000,
            stop_loss_price=1.0950,
            symbol="EURUSD",
            leverage=100,
        )
        # position_notional = lots * 100_000 * 1.1000; must not exceed 10_000 * 100 = 1_000_000
        assert result.units * 1.1000 <= 10_000.0 * 100 + 1.0
        assert result.lots > 0

    def test_raises_zero_balance(self, sizer):
        with pytest.raises(ValueError, match="account_balance"):
            sizer.calculate_size(0, 1.0, 1.1000, 1.0950, "EURUSD")

    def test_raises_same_entry_sl(self, sizer):
        with pytest.raises(ValueError, match="differ"):
            sizer.calculate_size(10_000, 1.0, 1.1000, 1.1000, "EURUSD")

    def test_raises_bad_risk_pct(self, sizer):
        with pytest.raises(ValueError, match="risk_pct"):
            sizer.calculate_size(10_000, 0.0, 1.1000, 1.0950, "EURUSD")

    def test_calculate_pip_value_eurusd(self, sizer):
        pv = sizer.calculate_pip_value("EURUSD", lot_size=1.0)
        assert pv == pytest.approx(10.0)

    def test_calculate_pip_value_gbpusd(self, sizer):
        pv = sizer.calculate_pip_value("GBPUSD", lot_size=2.0)
        assert pv == pytest.approx(20.0)

    def test_calculate_pip_value_jpy_pair(self, sizer):
        pv = sizer.calculate_pip_value("USDJPY", lot_size=1.0)
        assert pv > 0

    def test_risk_adjusted_size_no_change_below_1(self, sizer):
        result = sizer.risk_adjusted_size(1.0, volatility_ratio=0.8)
        assert result == pytest.approx(1.0)

    def test_risk_adjusted_size_reduces_on_high_vol(self, sizer):
        result = sizer.risk_adjusted_size(1.0, volatility_ratio=2.0, max_reduction_pct=50.0)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_risk_adjusted_size_floor(self, sizer):
        result = sizer.risk_adjusted_size(1.0, volatility_ratio=10.0, max_reduction_pct=50.0)
        # floor is 50% of base_size
        assert result >= 0.5 - 0.01

    def test_risk_adjusted_size_minimum_lot(self, sizer):
        result = sizer.risk_adjusted_size(0.01, volatility_ratio=10.0, max_reduction_pct=99.0)
        assert result >= 0.01

    def test_risk_adjusted_size_raises_bad_inputs(self, sizer):
        with pytest.raises(ValueError):
            sizer.risk_adjusted_size(-1.0, volatility_ratio=1.5)
        with pytest.raises(ValueError):
            sizer.risk_adjusted_size(1.0, volatility_ratio=0.0)
        with pytest.raises(ValueError):
            sizer.risk_adjusted_size(1.0, volatility_ratio=1.5, max_reduction_pct=150.0)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 4 – ExecutionEngine
# ═══════════════════════════════════════════════════════════════════════════════


def _make_mock_broker_gateway(fill_price: float = 1.1002) -> MagicMock:
    gw = MagicMock()
    gw.get_account_info = AsyncMock(return_value=MagicMock(
        balance=10_000.0, equity=10_000.0, leverage=100
    ))
    gw.place_order = AsyncMock(return_value={"order_id": "BROKER-001", "fill_price": fill_price})
    return gw


def _make_mock_risk_engine(approved: bool = True) -> MagicMock:
    from forex_trading.risk.engine import RiskAssessment
    re = MagicMock()
    re.assess_trade = AsyncMock(return_value=RiskAssessment(
        is_approved=approved,
        violations=[] if approved else ["test violation"],
        risk_score=0.1,
    ))
    return re


def _make_mock_strategy_engine() -> MagicMock:
    from forex_trading.strategy.engine import ValidationResult
    se = MagicMock()
    validation = ValidationResult(is_valid=True)
    strategy_mock = MagicMock()
    strategy_mock.validate_signal.return_value = validation
    se.get_strategy.return_value = strategy_mock
    return se


def _make_mock_position_manager() -> MagicMock:
    pm = MagicMock()
    pm.create_position = AsyncMock(return_value=uuid4())
    pm.get_positions_for_symbol = AsyncMock(return_value=[])
    pm.get_all_positions = AsyncMock(return_value=[])
    pm.close_position = AsyncMock()
    pm.update_position = AsyncMock()
    return pm


def _make_mock_uow_factory() -> MagicMock:
    uow = MagicMock()
    uow.orders = MagicMock()
    uow.orders.add = AsyncMock()
    uow.orders.update = AsyncMock()
    uow.orders.get = AsyncMock()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock()
    factory.create = MagicMock(return_value=uow)
    return factory


def _make_mock_event_bus() -> MagicMock:
    eb = MagicMock()
    eb.publish = AsyncMock()
    return eb


@pytest.mark.unit
class TestExecutionEngine:
    @pytest.fixture
    def engine(self):
        from forex_trading.execution.engine import ExecutionEngine
        return ExecutionEngine(
            risk_engine=_make_mock_risk_engine(),
            broker_gateway=_make_mock_broker_gateway(),
            strategy_engine=_make_mock_strategy_engine(),
            position_manager=_make_mock_position_manager(),
            uow_factory=_make_mock_uow_factory(),
            event_bus=_make_mock_event_bus(),
            allow_off_hours=True,  # bypass time check in unit tests
        )

    @pytest.mark.asyncio
    async def test_process_signal_success(self, engine):
        signal = _make_signal(
            entry=1.1000, sl=1.0950, tp=1.1100,
            metadata={"lots": 0.1, "atr": 0.0005},
            confidence=0.85,
        )
        result = await engine.process_signal(signal, uuid4())
        assert result.success is True
        assert result.order_id is not None
        assert result.filled_price == pytest.approx(1.1002, abs=0.0001)
        assert result.slippage_pips == pytest.approx(2.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_process_signal_rejected_by_risk(self):
        from forex_trading.execution.engine import ExecutionEngine
        engine = ExecutionEngine(
            risk_engine=_make_mock_risk_engine(approved=False),
            broker_gateway=_make_mock_broker_gateway(),
            strategy_engine=_make_mock_strategy_engine(),
            position_manager=_make_mock_position_manager(),
            uow_factory=_make_mock_uow_factory(),
            event_bus=_make_mock_event_bus(),
            allow_off_hours=True,
        )
        signal = _make_signal(confidence=0.85)
        result = await engine.process_signal(signal, uuid4())
        assert result.success is False
        assert "Risk engine" in (result.rejection_reason or "")

    @pytest.mark.asyncio
    async def test_process_signal_rejected_low_confidence(self):
        from forex_trading.execution.engine import ExecutionEngine
        engine = ExecutionEngine(
            risk_engine=_make_mock_risk_engine(),
            broker_gateway=_make_mock_broker_gateway(),
            strategy_engine=_make_mock_strategy_engine(),
            position_manager=_make_mock_position_manager(),
            uow_factory=_make_mock_uow_factory(),
            event_bus=_make_mock_event_bus(),
            allow_off_hours=True,
        )
        signal = _make_signal(confidence=0.3)  # below 0.6 threshold
        result = await engine.process_signal(signal, uuid4())
        assert result.success is False
        assert "confidence" in (result.rejection_reason or "").lower()

    @pytest.mark.asyncio
    async def test_process_signal_rejected_wide_spread(self, engine):
        signal = _make_signal(
            metadata={"lots": 0.1, "atr": 0.0005, "current_spread_pips": 8.0},
            confidence=0.85,
        )
        result = await engine.process_signal(signal, uuid4())
        assert result.success is False
        assert "spread" in (result.rejection_reason or "").lower()

    @pytest.mark.asyncio
    async def test_process_signal_news_blackout(self, engine):
        engine.add_news_event(datetime.now(timezone.utc))
        signal = _make_signal(
            metadata={"lots": 0.1, "atr": 0.0005},
            confidence=0.85,
        )
        result = await engine.process_signal(signal, uuid4())
        assert result.success is False
        assert "news" in (result.rejection_reason or "").lower()
        engine.clear_news_events()

    @pytest.mark.asyncio
    async def test_process_signal_correlated_positions_blocked(self, engine):
        from forex_trading.execution.engine import _TrackedPosition
        conn = uuid4()
        # Pre-fill 3 EUR-correlated positions
        for _ in range(3):
            pid = uuid4()
            engine._tracked_positions[pid] = _TrackedPosition(
                position_id=pid, symbol="EURUSD", direction="long",
                entry_price=1.1000, current_stop_loss=1.0950,
                take_profit=1.1100, quantity=0.1, atr=0.0005,
                strategy_type="trend_following", max_holding_minutes=480,
                broker_connection_id=conn,
            )
        signal = _make_signal(confidence=0.85, metadata={"lots": 0.1, "atr": 0.0005})
        result = await engine.process_signal(signal, conn)
        assert result.success is False
        assert "correlated" in (result.rejection_reason or "").lower()
        engine._tracked_positions.clear()

    @pytest.mark.asyncio
    async def test_manage_position_move_breakeven(self, engine):
        from forex_trading.execution.engine import _TrackedPosition
        pid = uuid4()
        engine._tracked_positions[pid] = _TrackedPosition(
            position_id=pid, symbol="EURUSD", direction="long",
            entry_price=1.1000, current_stop_loss=1.0950,
            take_profit=1.1100, quantity=0.1, atr=0.0010,
            strategy_type="trend_following", max_holding_minutes=480,
            highest_price=1.1000, lowest_price=1.1000,
        )
        # Price moved 1.1×ATR = 0.0011 in favour (avoids fp precision edge)
        action = await engine.manage_position(pid, current_price=1.1011)
        assert action.action == "move_breakeven"
        assert action.new_stop_loss == pytest.approx(1.1000)

    @pytest.mark.asyncio
    async def test_manage_position_partial_close_at_2x_atr(self, engine):
        from forex_trading.execution.engine import _TrackedPosition
        pid = uuid4()
        engine._tracked_positions[pid] = _TrackedPosition(
            position_id=pid, symbol="EURUSD", direction="long",
            entry_price=1.1000, current_stop_loss=1.1000,
            take_profit=1.1300, quantity=0.1, atr=0.0010,
            strategy_type="trend_following", max_holding_minutes=480,
            highest_price=1.1000, lowest_price=1.1000,
            breakeven_moved=True,  # already past breakeven
        )
        action = await engine.manage_position(pid, current_price=1.1020)
        assert action.action == "partial_close"
        assert action.close_pct == pytest.approx(33.0)

    @pytest.mark.asyncio
    async def test_manage_position_max_holding_time(self, engine):
        from forex_trading.execution.engine import _TrackedPosition
        pid = uuid4()
        pos = _TrackedPosition(
            position_id=pid, symbol="EURUSD", direction="long",
            entry_price=1.1000, current_stop_loss=1.0950,
            take_profit=1.1100, quantity=0.1, atr=0.0010,
            strategy_type="trend_following", max_holding_minutes=1,
        )
        pos.opened_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        engine._tracked_positions[pid] = pos
        action = await engine.manage_position(pid, current_price=1.1005)
        assert action.action == "close"
        assert "max holding" in action.reason.lower()

    @pytest.mark.asyncio
    async def test_manage_position_unknown_returns_hold(self, engine):
        action = await engine.manage_position(uuid4(), current_price=1.1000)
        assert action.action == "hold"

    @pytest.mark.asyncio
    async def test_close_position_full(self, engine):
        from forex_trading.execution.engine import _TrackedPosition
        conn = uuid4()
        pid = uuid4()
        engine._tracked_positions[pid] = _TrackedPosition(
            position_id=pid, symbol="EURUSD", direction="long",
            entry_price=1.1000, current_stop_loss=1.0950,
            take_profit=1.1100, quantity=0.1, atr=0.0010,
            strategy_type="trend_following", max_holding_minutes=480,
            broker_connection_id=conn,
        )
        success = await engine.close_position(pid, reason="test", partial_pct=100.0)
        assert success is True
        assert pid not in engine._tracked_positions

    @pytest.mark.asyncio
    async def test_close_position_partial(self, engine):
        from forex_trading.execution.engine import _TrackedPosition
        conn = uuid4()
        pid = uuid4()
        engine._tracked_positions[pid] = _TrackedPosition(
            position_id=pid, symbol="EURUSD", direction="long",
            entry_price=1.1000, current_stop_loss=1.0950,
            take_profit=1.1100, quantity=0.3, atr=0.0010,
            strategy_type="trend_following", max_holding_minutes=480,
            broker_connection_id=conn,
        )
        success = await engine.close_position(pid, reason="partial", partial_pct=33.0)
        assert success is True
        assert pid in engine._tracked_positions
        assert engine._tracked_positions[pid].quantity == pytest.approx(0.2, abs=0.01)

    @pytest.mark.asyncio
    async def test_emergency_close_all(self, engine):
        from forex_trading.execution.engine import _TrackedPosition
        conn = uuid4()
        for i in range(3):
            pid = uuid4()
            engine._tracked_positions[pid] = _TrackedPosition(
                position_id=pid, symbol="EURUSD", direction="long",
                entry_price=1.1000, current_stop_loss=1.0950,
                take_profit=1.1100, quantity=0.1, atr=0.0010,
                strategy_type="trend_following", max_holding_minutes=480,
                broker_connection_id=conn,
            )
        result = await engine.emergency_close_all("emergency test")
        assert len(result["closed"]) == 3
        assert len(result["failed"]) == 0
        assert len(engine._tracked_positions) == 0

    @pytest.mark.asyncio
    async def test_close_position_invalid_pct(self, engine):
        pid = uuid4()
        success = await engine.close_position(pid, reason="test", partial_pct=0.0)
        assert success is False

    @pytest.mark.asyncio
    async def test_create_and_cancel_order(self, engine):
        from forex_trading.execution.engine import OrderSide, OrderType
        order = await engine.create_order(
            broker_account_id=uuid4(),
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
        )
        assert order.order_id in engine._active_sagas
        result = await engine.cancel_order(order.order_id)
        assert result.success is True
        assert order.order_id not in engine._active_sagas
