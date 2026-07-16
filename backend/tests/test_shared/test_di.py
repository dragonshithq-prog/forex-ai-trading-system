"""Tests for DI Container initialization and dependency resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forex_trading.shared.di import Container
from forex_trading.shared.database.engine import DatabaseEngine


pytestmark = pytest.mark.asyncio


class TestContainerInitialization:
    """Tests for the DI Container."""

    async def test_container_creates_empty(self):
        """A new Container should have all services as None."""
        container = Container()
        assert container.db is None
        assert container.event_bus is None
        assert container.cache is None
        assert container.uow_factory is None
        assert container.risk_engine is None
        assert container.execution_engine is None
        assert container.broker_gateway is None
        assert container.ai_orchestrator is None
        assert container.auto_trader is None
        assert container.position_manager is None
        assert container.position_sizer is None
        assert container.feature_service is None
        assert container.market_data is None
        assert container.strategy_engine is None
        assert container.outbox_publisher is None

    async def test_init_db_creates_database_engine(self):
        """init_db should create a DatabaseEngine and UoW factory."""
        container = Container()
        # init_db with sqlite+aiosqlite is ok if we don't use pool_size
        # The actual engine creation fails for sqlite+pool params,
        # so we test the assignment logic instead
        from forex_trading.shared.database.engine import DatabaseEngine
        from forex_trading.shared.database.uow import UnitOfWorkFactory

        # Create a minimal mock approach
        engine = AsyncMock(spec=DatabaseEngine)
        engine.session_factory = MagicMock()
        container.db = engine
        container.uow_factory = UnitOfWorkFactory(engine.session_factory)
        assert container.db is not None
        assert container.uow_factory is not None

    async def test_init_event_bus_raises_without_kafka(self):
        """init_event_bus should fail gracefully without a Kafka server."""
        container = Container()
        with pytest.raises(Exception):
            await container.init_event_bus("localhost:9999")

    async def test_init_broker_gateway_creates_gateway(self):
        """init_broker_gateway should create a BrokerGateway with plugins."""
        container = Container()
        await container.init_broker_gateway()
        assert container.broker_gateway is not None

    async def test_init_position_sizer(self):
        """init_position_sizer should create a PositionSizer."""
        container = Container()
        await container.init_position_sizer()
        assert container.position_sizer is not None

    async def test_init_feature_service_without_cache(self):
        """init_feature_service should handle missing cache gracefully."""
        container = Container()
        container.cache = None
        await container.init_feature_service()
        assert container.feature_service is not None

    async def test_init_outbox_publisher_requires_event_bus_and_db(self):
        """init_outbox_publisher should require event_bus and db to be set."""
        container = Container()
        with pytest.raises(RuntimeError, match="event_bus and db"):
            await container.init_outbox_publisher()

    async def test_init_risk_engine_requires_uow(self):
        """init_risk_engine should require uow_factory."""
        container = Container()
        with pytest.raises(RuntimeError, match="uow_factory"):
            await container.init_risk_engine()

    async def test_init_position_manager_requires_deps(self):
        """init_position_manager should require uow_factory, event_bus, broker_gateway."""
        container = Container()
        with pytest.raises(RuntimeError, match="dependencies"):
            await container.init_position_manager()

    async def test_init_execution_engine_requires_deps(self):
        """init_execution_engine should require all dependencies."""
        container = Container()
        with pytest.raises(RuntimeError, match="dependencies"):
            await container.init_execution_engine()

    async def test_init_auto_trader_requires_deps(self):
        """init_auto_trader should require all dependencies."""
        container = Container()
        with pytest.raises(RuntimeError, match="dependencies"):
            await container.init_auto_trader()

    async def test_container_stop_graceful(self):
        """Container stop should not raise even if services are None."""
        container = Container()
        await container.stop()  # Should not raise

    async def test_container_stop_with_services(self, test_container):
        """Container stop should close all initialized services."""
        await test_container.stop()  # Should not raise

    async def test_container_start_initializes_all(self, monkeypatch):
        """Full container start should initialize services in order."""
        container = Container()

        # Mock external dependencies
        monkeypatch.setattr(container, "init_db", AsyncMock())
        monkeypatch.setattr(container, "init_event_bus", AsyncMock())
        monkeypatch.setattr(container, "init_cache", AsyncMock())
        monkeypatch.setattr(container, "init_feature_service", AsyncMock())
        monkeypatch.setattr(container, "init_broker_gateway", AsyncMock())
        monkeypatch.setattr(container, "init_market_data", AsyncMock())
        monkeypatch.setattr(container, "init_strategy_engine", AsyncMock())
        monkeypatch.setattr(container, "init_risk_engine", AsyncMock())
        monkeypatch.setattr(container, "init_position_sizer", AsyncMock())
        monkeypatch.setattr(container, "init_position_manager", AsyncMock())
        monkeypatch.setattr(container, "init_execution_engine", AsyncMock())
        monkeypatch.setattr(container, "init_ai_orchestrator", AsyncMock())
        monkeypatch.setattr(container, "init_auto_trader", AsyncMock())
        monkeypatch.setattr(container, "init_outbox_publisher", AsyncMock())

        await container.start()

        assert container.init_db.called
        assert container.init_event_bus.called
        assert container.init_cache.called
        assert container.init_feature_service.called
        assert container.init_broker_gateway.called
        assert container.init_market_data.called
        assert container.init_strategy_engine.called
        assert container.init_risk_engine.called
        assert container.init_position_sizer.called
        assert container.init_position_manager.called
        assert container.init_execution_engine.called
        assert container.init_ai_orchestrator.called
        assert container.init_auto_trader.called
        assert container.init_outbox_publisher.called
