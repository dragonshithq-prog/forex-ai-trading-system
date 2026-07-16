"""Tests for AutoTrader signal generation pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from forex_trading.execution.services.auto_trader import AutoTrader


pytestmark = pytest.mark.asyncio


class TestAutoTrader:
    """Tests for the AutoTrader execution loop."""

    async def test_start_stop(self, test_container):
        """AutoTrader should start and stop cleanly."""
        at = test_container.auto_trader
        assert at._running is False

        await at.start(uuid4())
        assert at._running is True
        assert at._task is not None

        await at.stop()
        assert at._running is False

    async def test_start_does_not_duplicate(self, test_container):
        """Starting an already-running AutoTrader should log a warning."""
        at = test_container.auto_trader
        await at.start(uuid4())
        await at.start(uuid4())  # Should log warning but not crash
        await at.stop()

    async def test_execute_on_symbol_no_trend(self, test_container):
        """When no actionable trend is detected, execution should return 'none' action."""
        at = test_container.auto_trader
        broker_id = uuid4()
        at._broker_connection_id = broker_id

        # Mock trend monitor to return non-actionable snapshot
        snapshot = MagicMock()
        snapshot.actionable = False
        snapshot.dominant_trend = MagicMock()
        snapshot.dominant_trend.value = "neutral"
        snapshot.confidence = 0.0
        snapshot.summary = "No clear trend"
        snapshot.is_bullish = False
        snapshot.is_bearish = False
        snapshot.regime_to_strategy_type = MagicMock(return_value="trend_following")

        at._trend_monitor.analyze = AsyncMock(return_value=snapshot)
        at._trend_monitor.get_last_snapshot = MagicMock(return_value=None)

        result = await at.execute_on_symbol("EURUSD")
        assert result["action"] == "none"
        assert result["symbol"] == "EURUSD"

    async def test_execute_on_symbol_full_pipeline(self, test_container):
        """Full pipeline should execute when trend is actionable."""
        at = test_container.auto_trader
        broker_id = uuid4()
        at._broker_connection_id = broker_id

        # Mock trend monitor for an actionable long signal
        snapshot = MagicMock()
        snapshot.actionable = True
        snapshot.dominant_trend = MagicMock()
        snapshot.dominant_trend.value = "long"
        snapshot.confidence = 0.75
        snapshot.summary = "Strong uptrend"
        snapshot.is_bullish = True
        snapshot.is_bearish = False
        snapshot.regime_to_strategy_type = MagicMock(return_value="trend_following")

        at._trend_monitor.analyze = AsyncMock(return_value=snapshot)
        at._trend_monitor.get_last_snapshot = MagicMock(return_value=None)

        # Mock market data
        at._market_data.get_latest_tick = AsyncMock(return_value={
            "bid": 1.1000, "ask": 1.1002, "spread": 0.0002,
        })
        at._market_data.calculate_atr = AsyncMock(return_value=0.001)

        # Mock broker gateway account info
        account_info = MagicMock()
        account_info.balance = 10_000.0
        account_info.get = MagicMock(return_value=10_000.0)
        at._broker_gateway.get_account_info = AsyncMock(return_value=account_info)

        # Mock position sizer
        sizing_result = MagicMock()
        sizing_result.lots = 0.1
        sizing_result.risk_amount = 100.0
        sizing_result.risk_pct = 1.0
        at._position_sizer.calculate_size = MagicMock(return_value=sizing_result)
        at._position_sizer.risk_adjusted_size = MagicMock(return_value=0.1)

        # Mock execution engine
        exec_result = MagicMock()
        exec_result.success = True
        exec_result.order_id = uuid4()
        exec_result.rejection_reason = None
        at._execution_engine.process_signal = AsyncMock(return_value=exec_result)

        result = await at.execute_on_symbol("EURUSD")
        assert result["action"] == "executed"
        assert result["symbol"] == "EURUSD"
        assert result["trend"]["direction"] == "long"
        assert result["execution"]["success"] is True

    async def test_execute_on_symbol_broker_error(self, test_container):
        """When execution fails, result should reflect the failure."""
        at = test_container.auto_trader
        broker_id = uuid4()
        at._broker_connection_id = broker_id

        snapshot = MagicMock()
        snapshot.actionable = True
        snapshot.dominant_trend = MagicMock()
        snapshot.dominant_trend.value = "long"
        snapshot.confidence = 0.75
        snapshot.summary = "Strong uptrend"
        snapshot.is_bullish = True
        snapshot.is_bearish = False
        snapshot.regime_to_strategy_type = MagicMock(return_value="trend_following")

        at._trend_monitor.analyze = AsyncMock(return_value=snapshot)
        at._trend_monitor.get_last_snapshot = MagicMock(return_value=None)

        at._market_data.get_latest_tick = AsyncMock(return_value={
            "bid": 1.1000, "ask": 1.1002, "spread": 0.0002,
        })
        at._market_data.calculate_atr = AsyncMock(return_value=0.001)

        account_info = MagicMock()
        account_info.balance = 10_000.0
        account_info.get = MagicMock(return_value=10_000.0)
        at._broker_gateway.get_account_info = AsyncMock(return_value=account_info)

        sizing_result = MagicMock()
        sizing_result.lots = 0.1
        sizing_result.risk_amount = 100.0
        sizing_result.risk_pct = 1.0
        at._position_sizer.calculate_size = MagicMock(return_value=sizing_result)
        at._position_sizer.risk_adjusted_size = MagicMock(return_value=0.1)

        exec_result = MagicMock()
        exec_result.success = False
        exec_result.order_id = None
        exec_result.rejection_reason = "Risk engine rejected"
        at._execution_engine.process_signal = AsyncMock(return_value=exec_result)

        result = await at.execute_on_symbol("EURUSD")
        assert result["action"] == "none"
        assert result["execution"]["success"] is False
        assert result["execution"]["rejection"] == "Risk engine rejected"

    async def test_execute_on_symbol_no_broker_connection(self, test_container):
        """Without a broker connection, execution should return an error."""
        at = test_container.auto_trader
        at._broker_connection_id = None

        snapshot = MagicMock()
        snapshot.actionable = True
        snapshot.dominant_trend = MagicMock()
        snapshot.dominant_trend.value = "long"
        snapshot.is_bullish = True
        snapshot.is_bearish = False
        snapshot.regime_to_strategy_type = MagicMock(return_value="trend_following")

        at._trend_monitor.analyze = AsyncMock(return_value=snapshot)
        at._trend_monitor.get_last_snapshot = MagicMock(return_value=None)

        result = await at.execute_on_symbol("EURUSD")
        assert result.get("error") is not None

    async def test_close_positions_on_reversal(self, test_container):
        """Trend reversal should close opposing positions."""
        at = test_container.auto_trader
        broker_id = uuid4()
        at._broker_connection_id = broker_id

        # Previous snapshot was bullish, current is bearish
        prev = MagicMock()
        prev.is_bullish = True
        prev.is_bearish = False

        snapshot = MagicMock()
        snapshot.actionable = False
        snapshot.dominant_trend = MagicMock()
        snapshot.dominant_trend.value = "short"
        snapshot.confidence = 0.0
        snapshot.is_bullish = False
        snapshot.is_bearish = True
        snapshot.regime_to_strategy_type = MagicMock(return_value="trend_following")

        at._trend_monitor.analyze = AsyncMock(return_value=snapshot)
        at._trend_monitor.get_last_snapshot = MagicMock(return_value=prev)

        result = await at.execute_on_symbol("EURUSD")
        assert result.get("reversal") == "bullish_to_bearish"
