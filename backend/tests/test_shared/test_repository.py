"""Tests for BaseRepository CRUD operations."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from uuid import UUID, uuid4

from forex_trading.shared.database.repository import (
    BaseRepository,
    OrderRepository,
    PositionRepository,
    RiskStateRepository,
)
from forex_trading.shared.database.models_trading import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    PositionStatus,
    TimeInForce,
)
from forex_trading.shared.database.models_risk import (
    RiskState,
    RiskLevel,
)
from tests.factories import fake_order, fake_position, fake_risk_state


pytestmark = pytest.mark.asyncio


class TestBaseRepository:
    """Tests for the generic BaseRepository CRUD operations."""

    async def test_add_and_get(self, db_session):
        """Adding an entity and retrieving it by ID should work."""
        repo = OrderRepository(db_session)
        order = fake_order()
        await repo.add(order)
        await db_session.flush()

        fetched = await repo.get(order.id)
        assert fetched is not None
        assert fetched.id == order.id
        assert fetched.symbol == "EURUSD"
        assert fetched.side == OrderSide.BUY

    async def test_add_all(self, db_session):
        """Adding multiple entities at once should work."""
        repo = OrderRepository(db_session)
        orders = [fake_order(symbol="EURUSD"), fake_order(symbol="GBPUSD")]
        await repo.add_all(orders)
        await db_session.flush()

        for o in orders:
            fetched = await repo.get(o.id)
            assert fetched is not None

    async def test_get_nonexistent_returns_none(self, db_session):
        """Getting a non-existent ID should return None."""
        repo = OrderRepository(db_session)
        result = await repo.get(uuid4())
        assert result is None

    async def test_get_multi_with_defaults(self, db_session):
        """get_multi with no filters should return all entities."""
        repo = OrderRepository(db_session)
        orders = [fake_order() for _ in range(5)]
        await repo.add_all(orders)
        await db_session.flush()

        result = await repo.get_multi()
        assert len(result) >= 5

    async def test_get_multi_with_filters(self, db_session):
        """get_multi should respect filters."""
        repo = OrderRepository(db_session)
        orders = [
            fake_order(symbol="EURUSD", status=OrderStatus.PENDING),
            fake_order(symbol="GBPUSD", status=OrderStatus.FILLED),
            fake_order(symbol="EURUSD", status=OrderStatus.FILLED),
        ]
        await repo.add_all(orders)
        await db_session.flush()

        # Filter by symbol
        result = await repo.get_multi(
            filters=[Order.symbol == "EURUSD"]
        )
        assert len(result) == 2
        assert all(o.symbol == "EURUSD" for o in result)

    async def test_get_multi_with_ordering(self, db_session):
        """get_multi should respect ordering."""
        repo = OrderRepository(db_session)
        orders = [
            fake_order(quantity=1.0),
            fake_order(quantity=2.0),
            fake_order(quantity=3.0),
        ]
        await repo.add_all(orders)
        await db_session.flush()

        result = await repo.get_multi(order_by=Order.quantity.desc())
        assert result[0].quantity >= result[1].quantity >= result[2].quantity

    async def test_get_multi_with_pagination(self, db_session):
        """get_multi with skip/limit should paginate correctly."""
        repo = OrderRepository(db_session)
        orders = [fake_order() for _ in range(10)]
        await repo.add_all(orders)
        await db_session.flush()

        page1 = await repo.get_multi(skip=0, limit=3)
        assert len(page1) == 3

        page2 = await repo.get_multi(skip=3, limit=3)
        assert len(page2) == 3
        # Ensure different items
        ids_p1 = {o.id for o in page1}
        ids_p2 = {o.id for o in page2}
        assert ids_p1.isdisjoint(ids_p2)

    async def test_count(self, db_session):
        """count should return the total number of matching entities."""
        repo = OrderRepository(db_session)
        orders = [fake_order() for _ in range(7)]
        await repo.add_all(orders)
        await db_session.flush()

        total = await repo.count()
        assert total >= 7

    async def test_count_with_filters(self, db_session):
        """count with filters should return filtered count."""
        repo = OrderRepository(db_session)
        orders = [
            fake_order(symbol="EURUSD"),
            fake_order(symbol="EURUSD"),
            fake_order(symbol="GBPUSD"),
        ]
        await repo.add_all(orders)
        await db_session.flush()

        count = await repo.count(filters=[Order.symbol == "EURUSD"])
        assert count == 2

    async def test_update(self, db_session):
        """Updating an entity should persist changes."""
        repo = OrderRepository(db_session)
        order = fake_order()
        await repo.add(order)
        await db_session.flush()

        await repo.update(order, {"quantity": 5.0, "status": OrderStatus.FILLED})
        await db_session.flush()

        fetched = await repo.get(order.id)
        assert fetched.quantity == 5.0
        assert fetched.status == OrderStatus.FILLED

    async def test_delete(self, db_session):
        """Deleting an entity should remove it."""
        repo = OrderRepository(db_session)
        order = fake_order()
        await repo.add(order)
        await db_session.flush()

        await repo.delete(order)
        await db_session.flush()

        fetched = await repo.get(order.id)
        assert fetched is None

    async def test_exists(self, db_session):
        """exists should return True/False correctly."""
        repo = OrderRepository(db_session)
        order = fake_order()
        await repo.add(order)
        await db_session.flush()

        assert await repo.exists(order.id) is True
        assert await repo.exists(uuid4()) is False


class TestOrderRepository:
    """Tests for OrderRepository-specific methods."""

    async def test_get_by_broker_id(self, db_session):
        repo = OrderRepository(db_session)
        order = fake_order(broker_order_id="BRK-001")
        await repo.add(order)
        await db_session.flush()

        fetched = await repo.get_by_broker_id("BRK-001")
        assert fetched is not None
        assert fetched.id == order.id

        missing = await repo.get_by_broker_id("NONEXISTENT")
        assert missing is None

    async def test_get_by_symbol_and_status(self, db_session):
        repo = OrderRepository(db_session)
        orders = [
            fake_order(symbol="EURUSD", status=OrderStatus.PENDING),
            fake_order(symbol="EURUSD", status=OrderStatus.PENDING),
            fake_order(symbol="GBPUSD", status=OrderStatus.FILLED),
        ]
        await repo.add_all(orders)
        await db_session.flush()

        result = await repo.get_by_symbol_and_status("EURUSD", OrderStatus.PENDING)
        assert len(result) == 2

    async def test_get_pending_orders(self, db_session):
        repo = OrderRepository(db_session)
        orders = [
            fake_order(status=OrderStatus.PENDING),
            fake_order(status=OrderStatus.NEW),
            fake_order(status=OrderStatus.FILLED),
            fake_order(status=OrderStatus.CANCELLED),
        ]
        await repo.add_all(orders)
        await db_session.flush()

        pending = await repo.get_pending_orders()
        assert len(pending) == 2
        assert all(o.status in (OrderStatus.PENDING, OrderStatus.NEW) for o in pending)


class TestPositionRepository:
    """Tests for PositionRepository-specific methods."""

    async def test_get_open_positions(self, db_session):
        repo = PositionRepository(db_session)
        positions = [
            fake_position(status=PositionStatus.OPEN),
            fake_position(status=PositionStatus.OPEN),
            fake_position(status=PositionStatus.CLOSED),
        ]
        await repo.add_all(positions)
        await db_session.flush()

        open_positions = await repo.get_open_positions()
        assert len(open_positions) == 2
        assert all(p.status == PositionStatus.OPEN for p in open_positions)

    async def test_get_by_symbol(self, db_session):
        repo = PositionRepository(db_session)
        positions = [
            fake_position(symbol="EURUSD", status=PositionStatus.OPEN),
            fake_position(symbol="EURUSD", status=PositionStatus.CLOSED),
            fake_position(symbol="GBPUSD", status=PositionStatus.OPEN),
        ]
        await repo.add_all(positions)
        await db_session.flush()

        eur_positions = await repo.get_by_symbol("EURUSD")
        assert len(eur_positions) == 2

        eur_open = await repo.get_by_symbol("EURUSD", status=PositionStatus.OPEN)
        assert len(eur_open) == 1

    async def test_get_by_broker_position_id(self, db_session):
        repo = PositionRepository(db_session)
        pos = fake_position(broker_position_id="BP-001")
        await repo.add(pos)
        await db_session.flush()

        fetched = await repo.get_by_broker_position_id("BP-001")
        assert fetched is not None
        assert fetched.id == pos.id


class TestRiskStateRepository:
    """Tests for RiskStateRepository-specific methods."""

    async def test_get_by_account(self, db_session):
        repo = RiskStateRepository(db_session)
        account_id = uuid4()
        state = fake_risk_state(broker_account_id=account_id)
        await repo.add(state)
        await db_session.flush()

        fetched = await repo.get_by_account(account_id)
        assert fetched is not None
        assert fetched.broker_account_id == account_id

    async def test_upsert_new(self, db_session):
        repo = RiskStateRepository(db_session)
        account_id = uuid4()
        state = await repo.upsert(account_id, {"current_equity": 5000.0})
        assert state.broker_account_id == account_id
        assert state.current_equity == 5000.0
        await db_session.flush()

        fetched = await repo.get_by_account(account_id)
        assert fetched is not None

    async def test_upsert_existing(self, db_session):
        repo = RiskStateRepository(db_session)
        account_id = uuid4()
        original = await repo.upsert(account_id, {"current_equity": 5000.0})
        await db_session.flush()

        updated = await repo.upsert(account_id, {"current_equity": 7500.0})
        assert updated.id == original.id
        assert updated.current_equity == 7500.0
