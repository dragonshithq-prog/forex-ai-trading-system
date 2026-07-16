"""Tests for DatabaseEngine."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.engine import DatabaseEngine


pytestmark = pytest.mark.asyncio


class TestDatabaseEngine:
    """Tests for the DatabaseEngine class."""

    async def test_initialize_creates_engine(self):
        """Initialize should create the async engine and session factory."""
        engine = DatabaseEngine("sqlite+aiosqlite://", echo=False)
        assert engine._engine is None
        assert engine._session_factory is None

        await engine.initialize()
        assert engine._engine is not None
        assert engine._session_factory is not None
        await engine.close()

    async def test_engine_property(self):
        """The engine property should return the underlying engine."""
        engine = DatabaseEngine("sqlite+aiosqlite://", echo=False)
        await engine.initialize()
        assert engine.engine is engine._engine
        await engine.close()

    async def test_session_factory_property(self):
        """The session_factory property should return the session maker."""
        engine = DatabaseEngine("sqlite+aiosqlite://", echo=False)
        await engine.initialize()
        assert engine.session_factory is engine._session_factory
        await engine.close()

    async def test_close_clears_engine(self):
        """Close should dispose the engine and clear references."""
        engine = DatabaseEngine("sqlite+aiosqlite://", echo=False)
        await engine.initialize()
        assert engine._engine is not None

        await engine.close()
        assert engine._engine is None
        assert engine._session_factory is None

    async def test_double_initialize_replaces_engine(self):
        """Calling initialize twice should dispose the first and create a new engine.

        The current implementation does not guard against re-initialization,
        so a second call creates a fresh engine while the first is disposed.
        """
        engine = DatabaseEngine("sqlite+aiosqlite://", echo=False)

        await engine.initialize()
        e1 = engine._engine

        # Second initialize — disposes the first, creates a new one
        await engine.initialize()
        e2 = engine._engine

        assert e1 is not e2  # New engine object
        assert engine._session_factory is not None
        await engine.close()

    async def test_initialize_with_pool_params_supported(self):
        """Engine should accept pool_size/max_overflow for non-SQLite dialects.

        For SQLite these are ignored during actual engine creation to avoid
        StaticPool incompatibility, but the parameters should be stored.
        """
        engine = DatabaseEngine("sqlite+aiosqlite://", echo=False, pool_size=5, max_overflow=2)
        assert engine._pool_size == 5
        assert engine._max_overflow == 2

    async def test_health_check_healthy(self):
        """health_check should return True when engine is initialized."""
        engine = DatabaseEngine("sqlite+aiosqlite://", echo=False)
        is_healthy = await engine.health_check()
        assert is_healthy is False  # not initialized

        await engine.initialize()
        is_healthy = await engine.health_check()
        assert is_healthy is True
        await engine.close()

    async def test_health_check_after_close(self):
        """health_check should return False after the engine is closed."""
        engine = DatabaseEngine("sqlite+aiosqlite://", echo=False)
        await engine.initialize()
        await engine.close()
        is_healthy = await engine.health_check()
        assert is_healthy is False
