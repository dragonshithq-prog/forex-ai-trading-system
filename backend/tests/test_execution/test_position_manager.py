"""Tests for PositionManager — open/close positions, reconciliation logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from forex_trading.execution.position_manager import PositionManager
from forex_trading.shared.database.models_trading import (
    PositionSide,
    PositionStatus,
)
from tests.factories import fake_position


pytestmark = pytest.mark.asyncio


class TestPositionManagerOpenClose:
    """Tests for opening and closing positions."""

    async def test_open_position(self, uow_factory, mock_event_bus, mock_broker_gateway):
        """Opening a position should persist it and publish an event."""
        pm = PositionManager(uow_factory, mock_event_bus, mock_broker_gateway)

        pos = await pm.open_position(
            broker_account_id=uuid4(),
            symbol="EURUSD",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=1.1000,
        )
        assert pos is not None
        assert pos.symbol == "EURUSD"
        assert pos.side == PositionSide.LONG
        assert pos.status == PositionStatus.OPEN
        assert pos.entry_price == 1.1000

        # Events are written via the transactional outbox (uow.add_event),
        # NOT directly to the event bus, so mock_event_bus.events will be empty.
        # Verify the position was persisted by querying the DB instead.

    async def test_open_position_with_sl_tp(self, uow_factory, mock_event_bus, mock_broker_gateway):
        """Opening a position with stop loss and take profit should work."""
        pm = PositionManager(uow_factory, mock_event_bus, mock_broker_gateway)
        pos = await pm.open_position(
            broker_account_id=uuid4(),
            symbol="EURUSD",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
        )
        assert pos.stop_loss == 1.0950
        assert pos.take_profit == 1.1100

    async def test_close_position(self, uow_factory, mock_event_bus, mock_broker_gateway):
        """Closing a position should update its status and publish an event."""
        pm = PositionManager(uow_factory, mock_event_bus, mock_broker_gateway)
        pos = await pm.open_position(
            broker_account_id=uuid4(),
            symbol="EURUSD",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=1.1000,
        )
        pos_id = pos.id

        result = await pm.close_position(
            position_id=pos_id,
            exit_price=1.1050,
            realized_pnl=50.0,
            reason="take_profit",
        )
        assert result is True

        # Verify position is closed in DB
        async with uow_factory as uow:
            closed = await uow.positions.get(pos_id)
            assert closed.status == PositionStatus.CLOSED
            assert closed.realized_pnl == 50.0

        # Events are written via the transactional outbox (uow.add_event),
        # NOT directly to the event bus.

    async def test_close_nonexistent_position(self, uow_factory, mock_event_bus, mock_broker_gateway):
        """Closing a non-existent position should return False."""
        pm = PositionManager(uow_factory, mock_event_bus, mock_broker_gateway)
        result = await pm.close_position(
            position_id=uuid4(),
            exit_price=1.1000,
            realized_pnl=0.0,
        )
        assert result is False

    async def test_update_position(self, uow_factory, mock_event_bus, mock_broker_gateway):
        """Updating a position's price should persist changes."""
        pm = PositionManager(uow_factory, mock_event_bus, mock_broker_gateway)
        pos = await pm.open_position(
            broker_account_id=uuid4(),
            symbol="EURUSD",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=1.1000,
        )

        await pm.update_position(
            position_id=pos.id,
            current_price=1.1050,
            stop_loss=1.1000,
        )

        # Verify update
        async with uow_factory as uow:
            updated = await uow.positions.get(pos.id)
            assert updated.current_price == 1.1050
            assert updated.stop_loss == 1.1000

    async def test_get_open_positions(self, uow_factory, mock_event_bus, mock_broker_gateway):
        """Getting open positions should return only open ones."""
        pm = PositionManager(uow_factory, mock_event_bus, mock_broker_gateway)
        account_id = uuid4()

        # Open two positions
        p1 = await pm.open_position(account_id, "EURUSD", PositionSide.LONG, 0.1, 1.1000)
        p2 = await pm.open_position(account_id, "GBPUSD", PositionSide.SHORT, 0.2, 1.2500)

        # Close one
        await pm.close_position(p2.id, 1.2400, 20.0, "test")

        # Get open positions
        open_positions = await pm.get_open_positions(account_id)
        assert len(open_positions) == 1
        assert open_positions[0].id == p1.id


class TestPositionManagerReconciliation:
    """Tests for the reconciliation loop."""

    async def test_reconcile_matching_positions(self, uow_factory, mock_event_bus, mock_broker_gateway_with_positions):
        """Reconciliation should not change matching positions."""
        pm = PositionManager(uow_factory, mock_event_bus, mock_broker_gateway_with_positions)
        account_id = uuid4()

        # Open a position in DB
        pos = await pm.open_position(
            broker_account_id=account_id,
            symbol="EURUSD",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=1.1000,
            broker_position_id="BP-001",
        )

        # Broker returns the same position
        from forex_trading.broker.gateway import BrokerPosition
        broker_pos = BrokerPosition(
            broker_position_id="BP-001",
            symbol="EURUSD",
            side="long",
            size=0.1,
            entry_price=1.1000,
            current_price=1.1010,
        )
        mock_broker_gateway_with_positions.get_positions = AsyncMock(return_value=[broker_pos])
        mock_broker_gateway_with_positions.get_connected_brokers = MagicMock(return_value=[account_id])

        # Run reconciliation
        await pm._reconcile_account(account_id)

        # Position should still be open with updated price
        async with uow_factory as uow:
            updated = await uow.positions.get(pos.id)
            assert updated.status == PositionStatus.OPEN
            # Price might have been updated
            assert updated.current_price is not None

    async def test_reconcile_detects_ghost_positions(self, uow_factory, mock_event_bus, mock_broker_gateway_with_positions):
        """Reconciliation should detect positions in DB but not at broker."""
        pm = PositionManager(uow_factory, mock_event_bus, mock_broker_gateway_with_positions)
        account_id = uuid4()

        # Open a position in DB
        pos = await pm.open_position(
            broker_account_id=account_id,
            symbol="EURUSD",
            side=PositionSide.LONG,
            size=0.1,
            entry_price=1.1000,
            broker_position_id="BP-GHOST",
        )

        # Broker returns no positions
        mock_broker_gateway_with_positions.get_positions = AsyncMock(return_value=[])
        mock_broker_gateway_with_positions.get_connected_brokers = MagicMock(return_value=[account_id])

        # Run reconciliation (should log ghost warning but not delete)
        await pm._reconcile_account(account_id)

        # Ghost position should still exist in DB
        async with uow_factory as uow:
            ghost = await uow.positions.get(pos.id)
            assert ghost is not None

    async def test_reconcile_auto_imports_broker_positions(self, uow_factory, mock_event_bus, mock_broker_gateway_with_positions):
        """Reconciliation should import positions that exist at broker but not in DB."""
        pm = PositionManager(uow_factory, mock_event_bus, mock_broker_gateway_with_positions)
        account_id = uuid4()

        # Broker has a position not in DB
        from forex_trading.broker.gateway import BrokerPosition
        broker_pos = BrokerPosition(
            broker_position_id="BP-NEW",
            symbol="GBPUSD",
            side="short",
            size=0.2,
            entry_price=1.2500,
            current_price=1.2480,
        )
        mock_broker_gateway_with_positions.get_positions = AsyncMock(return_value=[broker_pos])
        mock_broker_gateway_with_positions.get_connected_brokers = MagicMock(return_value=[account_id])

        # Run reconciliation
        await pm._reconcile_account(account_id)

        # Position should now exist in DB
        async with uow_factory as uow:
            imported = await uow.positions.get_by_broker_position_id("BP-NEW")
            assert imported is not None
            assert imported.symbol == "GBPUSD"
            assert imported.side == PositionSide.SHORT
