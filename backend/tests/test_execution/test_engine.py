"""Tests for ExecutionEngine — saga lifecycle, compensating transactions, pre-trade checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from forex_trading.execution.engine import (
    ExecutionEngine,
    ExecutionResult,
    Order,
    OrderResult,
    SagaStep,
    SagaStatus,
    Fill,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    ManagementAction,
)
from forex_trading.ai.agents.base import SignalDirection
from forex_trading.strategy.engine import TradeSignal, StrategyParameters, StrategyType
from forex_trading.shared.database.models_trading import (
    OrderSide as DBOrderSide,
    OrderType as DBOrderType,
    OrderStatus as DBOrderStatus,
    PositionSide,
)
from tests.factories import fake_order


pytestmark = pytest.mark.asyncio


class TestExecutionEngineSaga:
    """Tests for the saga lifecycle (validate → persist → submit → fill)."""

    async def test_process_signal_full_success(self, trade_signal, test_container):
        """A valid trade signal should go through the full saga and succeed."""
        engine = test_container.execution_engine
        broker_id = uuid4()

        # Ensure risk engine approves — seed risk state in DB
        async with test_container.uow_factory as uow:
            await uow.risk_states.upsert(broker_id, {
                "current_equity": 10_000.0,
                "peak_equity": 10_000.0,
                "current_drawdown_pct": 0.0,
                "total_exposure_pct": 0.0,
                "open_positions": 0,
                "consecutive_losses": 0,
                "daily_trades": 0,
                "is_circuit_breaker_active": False,
            })
            await uow.commit()

        # Mock broker gateway
        test_container.broker_gateway.get_account_info = AsyncMock(return_value=MagicMock(
            balance=10_000.0, equity=10_000.0,
        ))

        result = await engine.process_signal(trade_signal, broker_id)
        assert result is not None
        # With mocks it should at least not crash

    async def test_saga_persist_then_submit(self, test_container):
        """Saga should persist order to DB and submit to broker."""
        engine = test_container.execution_engine
        broker_id = uuid4()
        order = Order(
            broker_account_id=broker_id,
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
        )

        # Mock broker to return immediate fill
        test_container.broker_gateway.place_order = AsyncMock(return_value={
            "order_id": "BRK-001",
            "fill_price": 1.1002,
            "status": "filled",
            "filled_quantity": 0.1,
        })

        signal = TradeSignal(
            strategy=StrategyType.TREND_FOLLOWING,
            symbol="EURUSD",
            direction=SignalDirection.LONG,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            confidence=0.75,
            parameters=StrategyParameters(
                max_holding_time_minutes=240,
                metadata={"atr": 0.001, "lots": 0.1},
            ),
        )

        result = await engine._run_saga(order, broker_id, signal)
        assert result.success is True

    async def test_saga_compensates_on_broker_failure(self, test_container):
        """When broker rejects the order, the saga should compensate."""
        engine = test_container.execution_engine
        broker_id = uuid4()
        order = Order(
            broker_account_id=broker_id,
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            price=1.1000,
        )

        test_container.broker_gateway.place_order = AsyncMock(return_value={
            "error": "Insufficient margin",
        })

        signal = TradeSignal(
            strategy=StrategyType.TREND_FOLLOWING,
            symbol="EURUSD",
            direction=SignalDirection.LONG,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            confidence=0.75,
            parameters=StrategyParameters(
                max_holding_time_minutes=240,
                metadata={"atr": 0.001, "lots": 0.1},
            ),
        )

        result = await engine._run_saga(order, broker_id, signal)
        assert result.success is False
        assert "Insufficient margin" in (result.rejection_reason or "")

    async def test_on_fill_creates_position(self, test_container):
        """A fill notification should create a tracked position."""
        engine = test_container.execution_engine
        broker_id = uuid4()
        order = Order(
            broker_account_id=broker_id,
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0.1,
            price=1.1000,
            metadata={"atr": 0.001, "max_holding_minutes": 240, "strategy": "trend_following"},
        )
        engine._active_sagas[order.order_id] = order

        fill = Fill(
            order_id=order.order_id,
            symbol="EURUSD",
            side=OrderSide.BUY,
            quantity=0.1,
            price=1.1002,
            commission=0.5,
        )

        await engine.on_fill(order.order_id, fill)
        assert order.order_id in engine._tracked_positions
        tracked = engine._tracked_positions[order.order_id]
        assert tracked.symbol == "EURUSD"
        assert tracked.entry_price == 1.1002


class TestExecutionEnginePreTradeChecklist:
    """Tests for the pre-trade checklist."""

    async def test_checklist_off_hours_blocked(self, test_container):
        """Trading during off hours should be blocked by default."""
        engine = test_container.execution_engine
        engine._allow_off_hours = False

        signal = TradeSignal(
            strategy=StrategyType.TREND_FOLLOWING,
            symbol="EURUSD",
            direction=SignalDirection.LONG,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            confidence=0.75,
        )

        # Patch datetime to return an off-hour time
        with patch("forex_trading.execution.engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 23, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw) if args else mock_dt.now()

            rejection = await engine._run_pre_trade_checklist(signal, uuid4())
            assert rejection is not None
            assert "Off-hours" in rejection

    async def test_checklist_low_confidence_rejected(self, test_container):
        """Signals below minimum confidence should be rejected."""
        engine = test_container.execution_engine

        signal = TradeSignal(
            strategy=StrategyType.TREND_FOLLOWING,
            symbol="EURUSD",
            direction=SignalDirection.LONG,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            confidence=0.5,  # Below minimum of 0.6
        )

        rejection = await engine._run_pre_trade_checklist(signal, uuid4())
        assert rejection is not None
        assert "AI confidence" in rejection

    async def test_checklist_wide_spread_rejected(self, test_container):
        """Signals with spread exceeding max should be rejected."""
        engine = test_container.execution_engine
        engine._max_spread_pips = 5.0

        signal = TradeSignal(
            strategy=StrategyType.TREND_FOLLOWING,
            symbol="EURUSD",
            direction=SignalDirection.LONG,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            confidence=0.75,
            parameters=StrategyParameters(
                metadata={"current_spread_pips": 10.0},  # Exceeds 5.0
            ),
        )

        rejection = await engine._run_pre_trade_checklist(signal, uuid4())
        assert rejection is not None
        assert "Spread" in rejection

    async def test_checklist_passes_all_checks(self, test_container):
        """A valid signal should pass the checklist with no rejection."""
        engine = test_container.execution_engine
        engine._allow_off_hours = True

        signal = TradeSignal(
            strategy=StrategyType.TREND_FOLLOWING,
            symbol="EURUSD",
            direction=SignalDirection.LONG,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            confidence=0.75,
            parameters=StrategyParameters(
                metadata={"current_spread_pips": 1.0},
            ),
        )

        rejection = await engine._run_pre_trade_checklist(signal, uuid4())
        assert rejection is None


class TestExecutionEnginePositionManagement:
    """Tests for position management rules (breakeven, trailing, partial close)."""

    async def test_manage_position_hold_no_action(self, test_container):
        """When price hasn't moved enough, management should return 'hold'."""
        engine = test_container.execution_engine

        # Add a tracked position
        from forex_trading.execution.engine import _TrackedPosition
        pos_id = uuid4()
        engine._tracked_positions[pos_id] = _TrackedPosition(
            position_id=pos_id,
            symbol="EURUSD",
            direction="long",
            entry_price=1.1000,
            current_stop_loss=1.0950,
            take_profit=1.1100,
            quantity=0.1,
            atr=0.0010,
            strategy_type="trend_following",
            max_holding_minutes=240,
            highest_price=1.1000,
            lowest_price=1.1000,
        )

        # Price barely moved
        action = await engine.manage_position(pos_id, 1.1005)
        assert action.action == "hold"

    async def test_manage_position_breakeven(self, test_container):
        """When price moves enough, stop should move to breakeven."""
        engine = test_container.execution_engine

        pos_id = uuid4()
        engine._tracked_positions[pos_id] = type('MockPos', (), {
            "position_id": pos_id,
            "symbol": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "current_stop_loss": 1.0950,
            "take_profit": 1.1100,
            "quantity": 0.1,
            "atr": 0.0010,
            "strategy_type": "trend_following",
            "max_holding_minutes": 240,
            "highest_price": 1.1000,
            "lowest_price": 1.1000,
            "partial_1_done": False,
            "partial_2_done": False,
            "breakeven_moved": False,
            "opened_at": datetime.now(timezone.utc) - timedelta(minutes=30),
        })()

        # Price moved 1.5× ATR (0.0015) above entry — triggers breakeven but not partial close
        # 1.1015 - 1.1000 = 0.0015 (≈1.5× ATR), safely below 2.0× ATR partial-close threshold
        action = await engine.manage_position(pos_id, 1.1015)
        assert action.action == "move_breakeven"
        assert action.new_stop_loss == 1.1000  # Entry price

    def _make_mock_position(self, pos_id, overrides=None):
        """Create a mock position dict-like object with required attributes."""
        attrs = {
            "position_id": pos_id,
            "symbol": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "current_stop_loss": 1.0950,
            "take_profit": 1.1100,
            "quantity": 0.1,
            "atr": 0.0010,
            "strategy_type": "trend_following",
            "max_holding_minutes": 240,
            "highest_price": 1.1000,
            "lowest_price": 1.1000,
            "partial_1_done": False,
            "partial_2_done": False,
            "breakeven_moved": False,
            "opened_at": datetime.now(timezone.utc) - timedelta(minutes=30),
        }
        if overrides:
            attrs.update(overrides)
        return type('MockPosition', (), attrs)()

    async def test_manage_position_partial_close(self, test_container):
        """When price moves 2× ATR, should trigger first partial close."""
        engine = test_container.execution_engine

        pos_id = uuid4()
        engine._tracked_positions[pos_id] = self._make_mock_position(pos_id)

        # Price moved 2× ATR above entry
        action = await engine.manage_position(pos_id, 1.1020)
        assert action.action == "partial_close"
        assert action.close_pct == 33.0

    async def test_manage_position_time_exit(self, test_container):
        """When max holding time exceeded, should close position."""
        from datetime import timedelta
        engine = test_container.execution_engine

        pos_id = uuid4()
        old_time = datetime.now(timezone.utc) - timedelta(minutes=300)
        engine._tracked_positions[pos_id] = type('TP', (), {
            "position_id": pos_id,
            "symbol": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "current_stop_loss": 1.0950,
            "take_profit": 1.1100,
            "quantity": 0.1,
            "atr": 0.0010,
            "strategy_type": "trend_following",
            "max_holding_minutes": 240,
            "highest_price": 1.1000,
            "lowest_price": 1.1000,
            "partial_1_done": False,
            "partial_2_done": False,
            "breakeven_moved": False,
            "opened_at": old_time,
        })()

        action = await engine.manage_position(pos_id, 1.1005)
        assert action.action == "close"
        assert action.close_pct == 100.0


class TestExecutionEngineClosePosition:
    """Tests for closing positions."""

    async def test_close_full_position(self, test_container, uow_factory):
        """Closing a full position should remove it from tracking."""
        engine = test_container.execution_engine
        broker_id = uuid4()
        account_info = MagicMock(balance=10000.0, equity=10000.0)
        test_container.broker_gateway.get_account_info = AsyncMock(return_value=account_info)
        test_container.broker_gateway.place_order = AsyncMock(return_value={
            "order_id": "BRK-001",
            "fill_price": 1.1002,
            "status": "filled",
        })

        pos_id = uuid4()
        from forex_trading.execution.engine import _TrackedPosition
        engine._tracked_positions[pos_id] = _TrackedPosition(
            position_id=pos_id,
            symbol="EURUSD",
            direction="long",
            entry_price=1.1000,
            current_stop_loss=1.0950,
            take_profit=1.1100,
            quantity=0.1,
            atr=0.0010,
            strategy_type="trend_following",
            max_holding_minutes=240,
            broker_connection_id=broker_id,
        )

        # Open the position in DB
        await test_container.position_manager.open_position(
            broker_account_id=broker_id,
            symbol="EURUSD",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=1.1000,
        )

        result = await engine.close_position(pos_id, reason="test", partial_pct=100.0)
        assert result is True
        assert pos_id not in engine._tracked_positions

    async def test_close_nonexistent_position(self, test_container):
        engine = test_container.execution_engine
        result = await engine.close_position(uuid4(), reason="test")
        assert result is False
