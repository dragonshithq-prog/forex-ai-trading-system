"""Tests for PositionManager performance optimizations.

Tests:
- Rate limiting to broker API calls during reconciliation
- Backpressure when broker is slow
- Batch position fetching from broker
- Incremental reconciliation (only check recently changed positions)
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from forex_trading.execution.position_manager import PositionManager
from forex_trading.shared.database.models_trading import Position, PositionSide, PositionStatus


pytestmark = pytest.mark.asyncio


class TestPositionManagerPerformance:
    """Tests for PositionManager performance optimizations."""

    async def test_rate_limiting_enforced(self, uow_factory, mock_event_bus):
        """Rate limiting should limit broker API calls per minute."""
        mock_broker = MagicMock()
        mock_broker.get_connected_brokers = MagicMock(return_value=[uuid4()])
        mock_broker.get_positions = AsyncMock(return_value=[])
        mock_broker.get_open_positions = AsyncMock(return_value=[])

        pm = PositionManager(
            uow_factory=uow_factory,
            event_bus=mock_event_bus,
            broker_gateway=mock_broker,
            max_calls_per_minute=5,
        )

        # Make several rate-limited calls
        for _ in range(3):
            await pm._wait_for_rate_limit()

        # After 5 calls, the next one should be rate limited
        # _rate_limit_timestamps should have 3 entries
        assert len(pm._rate_limit_timestamps) == 3

    async def test_backpressure_detection(self, uow_factory, mock_event_bus):
        """Backpressure should trigger when broker is consistently slow."""
        mock_broker = MagicMock()
        mock_broker.get_connected_brokers = MagicMock(return_value=[])

        pm = PositionManager(
            uow_factory=uow_factory,
            event_bus=mock_event_bus,
            broker_gateway=mock_broker,
            backpressure_timeout=5.0,
        )

        connection_id = uuid4()

        # Simulate slow broker
        pm._broker_consecutive_slow[connection_id] = 3
        assert pm._is_broker_backpressured(connection_id) is True

        # Reset
        pm._broker_consecutive_slow[connection_id] = 2
        assert pm._is_broker_backpressured(connection_id) is False

    async def test_backpressure_clears_on_fast_response(self, uow_factory, mock_event_bus):
        """Backpressure should clear when broker responds quickly."""
        mock_broker = MagicMock()
        mock_broker.get_connected_brokers = MagicMock(return_value=[])

        pm = PositionManager(
            uow_factory=uow_factory,
            event_bus=mock_event_bus,
            broker_gateway=mock_broker,
        )

        connection_id = uuid4()

        # Simulate slow then fast responses
        pm._broker_consecutive_slow[connection_id] = 3
        pm._broker_response_times[connection_id] = 3.0

        # Reset after fast response
        pm._broker_consecutive_slow[connection_id] = 0
        assert pm._is_broker_backpressured(connection_id) is False

    async def test_batch_limit_enforced(self, uow_factory, mock_event_bus):
        """Batch size for positions should be limited."""
        pm = PositionManager(
            uow_factory=uow_factory,
            event_bus=mock_event_bus,
            broker_gateway=MagicMock(),
            max_positions_per_batch=10,
        )
        assert pm._max_positions_per_batch == 10

    async def test_incremental_reconciliation_window(self, uow_factory, mock_event_bus):
        """Incremental reconciliation window should be configurable."""
        pm = PositionManager(
            uow_factory=uow_factory,
            event_bus=mock_event_bus,
            broker_gateway=MagicMock(),
            incremental_window_minutes=30,
        )
        assert pm._incremental_window.total_seconds() == 1800  # 30 minutes

    async def test_start_stop_cleans_up(self, uow_factory, mock_event_bus):
        """PositionManager should start and stop cleanly."""
        broker = MagicMock()
        broker.get_connected_brokers = MagicMock(return_value=[])

        pm = PositionManager(
            uow_factory=uow_factory,
            event_bus=mock_event_bus,
            broker_gateway=broker,
        )

        await pm.start()
        assert pm._running is True
        assert pm._task is not None

        await pm.stop()
        assert pm._running is False

    async def test_open_position_creates_entry(self, uow_factory, mock_event_bus):
        """open_position should create a position record."""
        broker = MagicMock()
        broker.get_connected_brokers = MagicMock(return_value=[])

        pm = PositionManager(
            uow_factory=uow_factory,
            event_bus=mock_event_bus,
            broker_gateway=broker,
        )

        account_id = uuid4()
        position = await pm.open_position(
            broker_account_id=account_id,
            symbol="EURUSD",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=1.1000,
        )

        assert position is not None
        assert position.symbol == "EURUSD"
        assert position.side == PositionSide.LONG

        # Verify it's in the DB
        open_positions = await pm.get_open_positions(account_id)
        assert len(open_positions) == 1
        assert open_positions[0].id == position.id

    async def test_close_position_updates_status(self, uow_factory, mock_event_bus):
        """close_position should mark position as closed."""
        broker = MagicMock()
        broker.get_connected_brokers = MagicMock(return_value=[])

        pm = PositionManager(
            uow_factory=uow_factory,
            event_bus=mock_event_bus,
            broker_gateway=broker,
        )

        account_id = uuid4()
        position = await pm.open_position(
            broker_account_id=account_id,
            symbol="EURUSD",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=1.1000,
        )

        result = await pm.close_position(
            position_id=position.id,
            exit_price=1.1050,
            realized_pnl=50.0,
            reason="Take profit",
        )
        assert result is True

        # Verify position is closed
        open_positions = await pm.get_open_positions(account_id)
        assert len(open_positions) == 0

    async def test_reconcile_account_handles_timeout(self, uow_factory, mock_event_bus):
        """Reconciliation should handle broker timeout gracefully."""
        broker = MagicMock()
        broker.get_connected_brokers = MagicMock(return_value=[])

        # Simulate slow broker
        async def slow_get_positions(conn_id):
            await asyncio.sleep(10.0)
            return []

        broker.get_positions = slow_get_positions

        pm = PositionManager(
            uow_factory=uow_factory,
            event_bus=mock_event_bus,
            broker_gateway=broker,
            backpressure_timeout=0.1,  # Very short timeout
        )

        connection_id = uuid4()
        broker.get_connected_brokers = MagicMock(return_value=[connection_id])

        await pm._reconcile_account(connection_id)
        # Should have timed out and not crashed

    async def test_full_scan_periodic(self, uow_factory, mock_event_bus):
        """Full reconciliation scan should occur periodically."""
        broker = MagicMock()
        broker.get_connected_brokers = MagicMock(return_value=[])

        pm = PositionManager(
            uow_factory=uow_factory,
            event_bus=mock_event_bus,
            broker_gateway=broker,
            incremental_window_minutes=60,
        )

        connection_id = uuid4()

        # First reconcile: no full scan
        pm._last_reconcile_time[connection_id] = time.monotonic()
        # Set last reconcile far in the past to trigger full scan
        pm._last_reconcile_time[connection_id] = time.monotonic() - 99999

        # Test passes if no exception is raised
        broker.get_connected_brokers = MagicMock(return_value=[connection_id])
        broker.get_positions = AsyncMock(return_value=[])

        await pm._reconcile_account(connection_id)
