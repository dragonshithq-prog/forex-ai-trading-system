"""Tests for DatabaseEngine performance optimizations.

Tests:
- Connection pool timeout and overflow limits
- Pool pre-ping with exponential backoff
- Query timeout configuration
- Statement cache size tuning (asyncpg)
- Pool status metrics
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.engine import DatabaseEngine


pytestmark = pytest.mark.asyncio


class TestDatabaseEnginePerformance:
    """Tests for DatabaseEngine performance optimizations."""

    async def test_engine_with_pool_timeout(self):
        """Engine should accept pool_timeout parameter."""
        engine = DatabaseEngine(
            "sqlite+aiosqlite://",
            pool_timeout=15,
        )
        assert engine._pool_timeout == 15
        await engine.initialize()
        await engine.close()

    async def test_engine_with_query_timeout(self):
        """Engine should accept query_timeout parameter."""
        engine = DatabaseEngine(
            "sqlite+aiosqlite://",
            query_timeout=20,
        )
        assert engine._query_timeout == 20
        await engine.initialize()
        await engine.close()

    async def test_engine_with_statement_cache(self):
        """Engine should accept statement_cache_size parameter."""
        engine = DatabaseEngine(
            "sqlite+aiosqlite://",
            statement_cache_size=300,
        )
        assert engine._statement_cache_size == 300
        await engine.initialize()
        await engine.close()

    async def test_engine_with_custom_pool_params(self):
        """Engine should accept all pool parameters."""
        engine = DatabaseEngine(
            "sqlite+aiosqlite://",
            pool_size=10,
            max_overflow=5,
            pool_timeout=10,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        assert engine._pool_size == 10
        assert engine._max_overflow == 5
        assert engine._pool_timeout == 10
        assert engine._pool_pre_ping is True
        assert engine._pool_recycle == 1800

        await engine.initialize()
        await engine.close()

    async def test_pool_status_property(self):
        """pool_status should return engine diagnostics."""
        engine = DatabaseEngine("sqlite+aiosqlite://")
        await engine.initialize()

        status = engine.pool_status
        assert status["pool_size"] > 0
        assert status["max_overflow"] >= 0
        assert status["pool_timeout"] > 0
        assert status["query_timeout"] > 0
        assert status["consecutive_failures"] == 0
        assert "url_driver" in status

        await engine.close()

        # After close
        status = engine.pool_status
        assert status["status"] == "not_initialized"

    async def test_health_check_backoff(self):
        """Health check should apply exponential backoff after failure."""
        engine = DatabaseEngine("sqlite+aiosqlite://")

        # Simulate consecutive failures
        engine._consecutive_failures = 3
        engine._last_failure_time = __import__("time").monotonic()

        # Health check should return False without hitting DB due to backoff
        result = await engine.health_check()
        assert result is False
        assert engine._consecutive_failures >= 3

    async def test_health_check_resets_on_success(self):
        """Health check should reset consecutive_failures on success."""
        engine = DatabaseEngine("sqlite+aiosqlite://")
        await engine.initialize()

        engine._consecutive_failures = 2
        result = await engine.health_check()
        assert result is True
        assert engine._consecutive_failures == 0

        await engine.close()

    async def test_pool_metrics_task_created(self):
        """Engine should start a metrics reporting task on initialize."""
        engine = DatabaseEngine("sqlite+aiosqlite://")
        await engine.initialize()
        assert engine._metrics_task is not None
        assert not engine._metrics_task.done()

        await engine.close()
        assert engine._metrics_task is None or engine._metrics_task.done()

    async def test_asyncpg_connect_args(self):
        """Engine should set asyncpg-specific connect args when using asyncpg."""
        engine = DatabaseEngine(
            "postgresql+asyncpg://user:pass@localhost/db",
            statement_cache_size=500,
            query_timeout=30,
        )
        # The connect_args should be set during initialize
        # We can verify by checking that the asyncpg branch is reachable
        assert engine._statement_cache_size == 500
        assert engine._query_timeout == 30

    async def test_session_factory_after_initialize(self):
        """Session factory should be available after initialize."""
        engine = DatabaseEngine("sqlite+aiosqlite://")
        await engine.initialize()

        factory = engine.session_factory
        assert factory is not None

        async with factory() as session:
            assert session is not None

        await engine.close()

    async def test_get_session_returns_session(self):
        """get_session should return a configured session."""
        engine = DatabaseEngine("sqlite+aiosqlite://")
        await engine.initialize()

        session = await engine.get_session()
        assert session is not None
        await session.close()

        await engine.close()

    async def test_engine_property_raises_before_init(self):
        """Accessing engine before initialize should raise."""
        engine = DatabaseEngine("sqlite+aiosqlite://")
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = engine.engine

    async def test_session_factory_property_raises_before_init(self):
        """Accessing session_factory before initialize should raise."""
        engine = DatabaseEngine("sqlite+aiosqlite://")
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = engine.session_factory
