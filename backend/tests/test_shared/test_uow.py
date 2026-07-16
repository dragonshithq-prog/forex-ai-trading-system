"""Tests for UnitOfWork commit/rollback and event management."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from forex_trading.shared.database.uow import UnitOfWork, UnitOfWorkFactory


pytestmark = pytest.mark.asyncio


class TestUnitOfWork:
    """Tests for the UnitOfWork pattern implementation."""

    async def test_commit_persists_changes(self, db_session):
        """Commit should persist added entities to the database."""
        from tests.factories import fake_order
        from forex_trading.shared.database.repository import OrderRepository

        uow = UnitOfWork(db_session)
        order = fake_order()
        await uow.orders.add(order)
        await uow.commit()

        # Verify in the same session
        repo = OrderRepository(db_session)
        fetched = await repo.get(order.id)
        assert fetched is not None

    async def test_rollback_aborts_changes(self, db_session):
        """Rollback should discard all changes within the UoW."""
        from tests.factories import fake_order
        from forex_trading.shared.database.repository import OrderRepository

        # Start a savepoint so we can roll back without affecting the outer txn
        await db_session.begin_nested()

        uow = UnitOfWork(db_session)
        order = fake_order()
        await uow.orders.add(order)
        await uow.rollback()

        # Order should NOT be in the database after rollback
        repo = OrderRepository(db_session)
        fetched = await repo.get(order.id)
        assert fetched is None

        # Roll back the savepoint to clean up
        await db_session.rollback()

    async def test_add_event(self, db_session):
        """add_event should queue events for outbox."""
        uow = UnitOfWork(db_session)
        assert len(uow._events) == 0

        uow.add_event(
            aggregate_type="order",
            aggregate_id=uuid4(),
            event_type="trading.order.placed",
            payload={"order_id": str(uuid4())},
        )
        assert len(uow._events) == 1
        assert uow._events[0]["event_type"] == "trading.order.placed"

    async def test_commit_flushes_outbox_events(self, db_session):
        """Commit should write queued events to the outbox table."""
        from forex_trading.shared.database.models_trading import EventOutbox

        uow = UnitOfWork(db_session)
        uow.add_event(
            aggregate_type="order",
            aggregate_id=uuid4(),
            event_type="trading.order.placed",
            payload={"order_id": str(uuid4())},
        )
        await uow.commit()

        # Verify the outbox entry was persisted
        from sqlalchemy import select
        result = await db_session.execute(
            select(EventOutbox).where(EventOutbox.event_type == "trading.order.placed")
        )
        entries = result.scalars().all()
        assert len(entries) == 1

    async def test_rollback_clears_events(self, db_session):
        """Rollback should clear queued events without persisting them."""
        from forex_trading.shared.database.models_trading import EventOutbox

        uow = UnitOfWork(db_session)
        uow.add_event(
            aggregate_type="order",
            aggregate_id=uuid4(),
            event_type="trading.order.placed",
            payload={"order_id": str(uuid4())},
        )

        # Note: the event is only added to the internal _events list,
        # not yet written to DB. Rollback just clears the list.
        await uow.rollback()

        # No events should remain queued
        assert len(uow._events) == 0

        # No outbox entries should exist (none were committed)
        from sqlalchemy import select
        result = await db_session.execute(
            select(EventOutbox).where(EventOutbox.event_type == "trading.order.placed")
        )
        entries = result.scalars().all()
        assert len(entries) == 0

    async def test_flush_generates_ids(self, db_session):
        """Flush should assign IDs without committing the transaction."""
        from tests.factories import fake_order

        uow = UnitOfWork(db_session)
        order = fake_order(id=None)  # No ID assigned yet
        await uow.orders.add(order)
        await uow.flush()

        # ID should now be assigned (by the DB or default)
        assert order.id is not None

    async def test_uow_factory_context_manager(self, db_session):
        """UoW factory should provide proper enter/exit semantics."""
        from tests.factories import fake_order

        factory = UnitOfWorkFactory(lambda: db_session)
        async with factory as uow:
            assert isinstance(uow, UnitOfWork)
            order = fake_order()
            await uow.orders.add(order)
            await uow.commit()

    async def test_uow_factory_rollback_on_exception(self, db_session):
        """UoW factory should rollback if an exception occurs in the context."""
        from tests.factories import fake_order

        factory = UnitOfWorkFactory(lambda: db_session)

        # Wrap in a savepoint so the outer txn isn't affected
        await db_session.begin_nested()

        with pytest.raises(ValueError):
            async with factory as uow:
                order = fake_order()
                await uow.orders.add(order)
                raise ValueError("Test error")

        # The factory's __aexit__ calls rollback and closes the session,
        # and then rolls back the savepoint.
        await db_session.rollback()

        # Order should not be persisted
        from forex_trading.shared.database.repository import OrderRepository
        repo = OrderRepository(db_session)
        fetched = await repo.get(order.id)
        assert fetched is None

    async def test_multiple_repositories_in_one_uow(self, db_session):
        """UoW should provide access to all repositories."""
        uow = UnitOfWork(db_session)
        assert uow.orders is not None
        assert uow.positions is not None
        assert uow.trades is not None
        assert uow.risk_states is not None
        assert uow.risk_alerts is not None
        assert uow.risk_overrides is not None
        assert uow.ai_decisions is not None
        assert uow.session is not None

    async def test_uow_repr(self, db_session):
        """UoW should have a useful string representation."""
        uow = UnitOfWork(db_session)
        assert "UnitOfWork" in repr(uow)
