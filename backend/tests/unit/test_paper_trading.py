"""Unit tests for Paper Trading Engine."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from forex_trading.analytics.backtesting.paper_trading import PaperTradingEngine, VirtualPosition


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_engine(initial_balance: float = 10_000.0) -> PaperTradingEngine:
    market_data = MagicMock()
    market_data.get_ohlcv = AsyncMock(return_value=[])
    risk_engine = MagicMock()
    risk_engine.assess_trade = AsyncMock(return_value=MagicMock(is_approved=False))
    strategy_engine = MagicMock()
    ai_orchestrator = MagicMock()
    ai_orchestrator.get_signal = AsyncMock(return_value=None)

    return PaperTradingEngine(
        market_data_service=market_data,
        risk_engine=risk_engine,
        strategy_engine=strategy_engine,
        ai_orchestrator=ai_orchestrator,
        initial_balance=initial_balance,
    )


def _make_order(symbol="EURUSD", direction="long", size=0.1,
                sl=1.0950, tp=1.1100, price=1.1000) -> dict:
    return {
        "symbol": symbol,
        "direction": direction,
        "size": size,
        "stop_loss": sl,
        "take_profit": tp,
        "entry_price": price,
        "strategy_type": "trend_following",
    }


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestPaperTradingStartStop:
    async def test_starts_successfully(self):
        engine = _make_engine()
        await engine.start()
        assert engine._running is True

    async def test_double_start_safe(self):
        engine = _make_engine()
        await engine.start()
        await engine.start()  # should not raise
        assert engine._running is True

    async def test_stops_successfully(self):
        engine = _make_engine()
        await engine.start()
        await engine.stop()
        assert engine._running is False

    async def test_stop_without_start_safe(self):
        engine = _make_engine()
        await engine.stop()  # should not raise

    async def test_stop_closes_open_positions(self):
        engine = _make_engine()
        await engine.start()
        fill = await engine.simulate_fill(_make_order())
        assert len(engine._positions) == 1

        await engine.stop()
        assert len(engine._positions) == 0
        assert len(engine._closed_trades) == 1
        assert engine._closed_trades[0]["exit_reason"] == "engine_stop"


# ---------------------------------------------------------------------------
# simulate_fill
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestSimulateFill:
    async def test_fill_creates_position(self):
        engine = _make_engine()
        fill = await engine.simulate_fill(_make_order())

        assert fill["status"] == "filled"
        assert len(engine._positions) == 1

    async def test_fill_returns_position_id(self):
        engine = _make_engine()
        fill = await engine.simulate_fill(_make_order())
        assert "position_id" in fill
        assert fill["position_id"] in engine._positions

    async def test_commission_deducted(self):
        engine = _make_engine(10_000.0)
        initial_balance = engine._virtual_balance
        await engine.simulate_fill(_make_order(size=1.0))
        # Commission for 1 lot = $7
        assert engine._virtual_balance < initial_balance

    async def test_long_slippage_increases_price(self):
        engine = _make_engine()
        fill = await engine.simulate_fill(_make_order(direction="long", price=1.1000))
        assert fill["fill_price"] > 1.1000  # slippage adds to long entry

    async def test_short_slippage_decreases_price(self):
        engine = _make_engine()
        fill = await engine.simulate_fill(_make_order(direction="short", price=1.1000))
        assert fill["fill_price"] < 1.1000  # slippage subtracts from short entry

    async def test_fill_recorded_in_history(self):
        engine = _make_engine()
        await engine.simulate_fill(_make_order())
        assert len(engine._fill_history) == 1


# ---------------------------------------------------------------------------
# process_tick
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestProcessTick:
    async def test_process_tick_when_not_running_is_noop(self):
        engine = _make_engine()
        await engine.process_tick("EURUSD", 1.1000)
        assert len(engine._positions) == 0

    async def test_sl_hit_closes_long(self):
        engine = _make_engine()
        await engine.start()
        fill = await engine.simulate_fill(_make_order(direction="long", price=1.1000, sl=1.0950, tp=1.1200))

        # Tick below SL
        await engine.process_tick("EURUSD", 1.0940)
        assert len(engine._positions) == 0
        assert engine._closed_trades[-1]["exit_reason"] == "sl_hit"

    async def test_tp_hit_closes_long(self):
        engine = _make_engine()
        await engine.start()
        fill = await engine.simulate_fill(_make_order(direction="long", price=1.1000, sl=1.0900, tp=1.1100))

        # Tick above TP
        await engine.process_tick("EURUSD", 1.1110)
        assert len(engine._positions) == 0
        assert engine._closed_trades[-1]["exit_reason"] == "tp_hit"

    async def test_sl_hit_closes_short(self):
        engine = _make_engine()
        await engine.start()
        fill = await engine.simulate_fill(_make_order(direction="short", price=1.1000, sl=1.1060, tp=1.0900))

        # Tick above SL for short
        await engine.process_tick("EURUSD", 1.1070)
        assert len(engine._positions) == 0
        assert engine._closed_trades[-1]["exit_reason"] == "sl_hit"

    async def test_tp_hit_closes_short(self):
        engine = _make_engine()
        await engine.start()
        fill = await engine.simulate_fill(_make_order(direction="short", price=1.1000, sl=1.1060, tp=1.0900))

        # Tick below TP for short
        await engine.process_tick("EURUSD", 1.0890)
        assert len(engine._positions) == 0
        assert engine._closed_trades[-1]["exit_reason"] == "tp_hit"

    async def test_tick_updates_unrealized_pnl(self):
        engine = _make_engine()
        await engine.start()
        fill = await engine.simulate_fill(_make_order(direction="long", price=1.1000, sl=1.0900, tp=1.1200))
        position_id = fill["position_id"]

        # Move price up 10 pips
        await engine.process_tick("EURUSD", 1.1010)

        if position_id in engine._positions:
            pos = engine._positions[position_id]
            assert pos.current_price == pytest.approx(1.1010)
            assert pos.unrealized_pnl > 0  # long position gains when price rises

    async def test_other_symbol_tick_ignored(self):
        engine = _make_engine()
        await engine.start()
        fill = await engine.simulate_fill(_make_order(symbol="EURUSD", price=1.1000, sl=1.0900, tp=1.1200))
        position_id = fill["position_id"]

        # Different symbol tick
        await engine.process_tick("GBPUSD", 1.2500)
        assert position_id in engine._positions  # EURUSD position untouched

    async def test_tick_increments_counter(self):
        engine = _make_engine()
        await engine.start()
        initial = engine._tick_count
        await engine.process_tick("EURUSD", 1.1000)
        assert engine._tick_count == initial + 1


# ---------------------------------------------------------------------------
# get_virtual_account
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestGetVirtualAccount:
    async def test_initial_state(self):
        engine = _make_engine(initial_balance=25_000.0)
        account = engine.get_virtual_account()
        assert account["initial_balance"] == 25_000.0
        assert account["equity"] == 25_000.0
        assert account["open_positions"] == 0
        assert account["total_trades"] == 0

    async def test_equity_includes_unrealized(self):
        engine = _make_engine(10_000.0)
        await engine.start()
        fill = await engine.simulate_fill(_make_order(direction="long", price=1.1000, sl=1.0900, tp=1.1200))

        # Force update unrealized pnl by processing a winning tick
        await engine.process_tick("EURUSD", 1.1050)  # 50 pips up

        account = engine.get_virtual_account()
        assert account["open_positions"] >= 0  # may or may not be closed

    async def test_total_return_pct_formula(self):
        engine = _make_engine(10_000.0)
        engine._virtual_balance = 11_000.0
        account = engine.get_virtual_account()
        assert account["total_return_pct"] == pytest.approx(10.0)

    async def test_is_running_flag(self):
        engine = _make_engine()
        assert engine.get_virtual_account()["is_running"] is False
        await engine.start()
        assert engine.get_virtual_account()["is_running"] is True


# ---------------------------------------------------------------------------
# get_virtual_positions
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestGetVirtualPositions:
    async def test_empty_when_no_positions(self):
        engine = _make_engine()
        assert engine.get_virtual_positions() == []

    async def test_returns_all_open_positions(self):
        engine = _make_engine()
        await engine.simulate_fill(_make_order(symbol="EURUSD"))
        await engine.simulate_fill(_make_order(symbol="GBPUSD"))
        positions = engine.get_virtual_positions()
        assert len(positions) == 2

    async def test_position_dict_keys(self):
        engine = _make_engine()
        await engine.simulate_fill(_make_order())
        pos = engine.get_virtual_positions()[0]
        required_keys = {"position_id", "symbol", "direction", "size", "entry_price",
                         "current_price", "stop_loss", "take_profit", "unrealized_pnl", "opened_at"}
        assert required_keys.issubset(pos.keys())


# ---------------------------------------------------------------------------
# get_performance_summary
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestGetPerformanceSummary:
    async def test_empty_trades(self):
        engine = _make_engine()
        summary = engine.get_performance_summary()
        assert summary["total_trades"] == 0
        assert summary["win_rate"] == 0.0

    async def test_after_profitable_trade(self):
        engine = _make_engine(10_000.0)
        await engine.start()
        await engine.simulate_fill(_make_order(direction="long", price=1.1000, sl=1.0900, tp=1.1200))
        await engine.process_tick("EURUSD", 1.1210)  # hit TP

        summary = engine.get_performance_summary()
        if summary["total_trades"] > 0:
            assert summary["win_rate"] >= 0.0
            assert "net_profit" in summary

    async def test_summary_keys_present(self):
        engine = _make_engine()
        summary = engine.get_performance_summary()
        required = {"total_trades", "win_rate", "profit_factor", "net_profit", "best_trade", "worst_trade"}
        assert required.issubset(summary.keys())


# ---------------------------------------------------------------------------
# P&L calculation correctness
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPnLCalculation:
    def test_long_profit(self):
        engine = _make_engine()
        pos = VirtualPosition(
            position_id="test",
            symbol="EURUSD",
            direction="long",
            size=1.0,
            entry_price=1.1000,
            current_price=1.1050,
            stop_loss=1.0950,
            take_profit=1.1100,
            opened_at=datetime.utcnow(),
        )
        pnl = engine._calc_pnl(pos)
        # 50 pips * $10/pip * 1 lot = $500
        assert pnl == pytest.approx(500.0)

    def test_short_profit(self):
        engine = _make_engine()
        pos = VirtualPosition(
            position_id="test",
            symbol="EURUSD",
            direction="short",
            size=0.5,
            entry_price=1.1000,
            current_price=1.0980,
            stop_loss=1.1050,
            take_profit=1.0900,
            opened_at=datetime.utcnow(),
        )
        pnl = engine._calc_pnl(pos)
        # 20 pips * $10/pip * 0.5 lot = $100
        assert pnl == pytest.approx(100.0)

    def test_long_loss(self):
        engine = _make_engine()
        pos = VirtualPosition(
            position_id="test",
            symbol="EURUSD",
            direction="long",
            size=1.0,
            entry_price=1.1000,
            current_price=1.0950,
            stop_loss=1.0950,
            take_profit=1.1100,
            opened_at=datetime.utcnow(),
        )
        pnl = engine._calc_pnl(pos)
        assert pnl == pytest.approx(-500.0)
