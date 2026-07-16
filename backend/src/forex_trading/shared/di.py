"""Dependency injection container — no global singletons.

All application services are wired together here at startup and injected
into constructors. No module-level ``db_manager``, ``cache_manager``, etc.
"""

from __future__ import annotations

from typing import Any

import structlog

from forex_trading.config import get_settings
from forex_trading.shared.database.engine import DatabaseEngine
from forex_trading.shared.database.uow import UnitOfWorkFactory
from forex_trading.shared.database.outbox import OutboxPublisher
from forex_trading.shared.messaging.kafka_producer import KafkaEventBus
from forex_trading.shared.cache import CacheManager

logger = structlog.get_logger()


class Container:
    """Application DI container.

    Explicitly NOT a singleton. Created once by ``create_application()``
    in ``main.py`` and passed to every service.
    """

    def __init__(self) -> None:
        # Core infrastructure
        self.db: DatabaseEngine | None = None
        self.event_bus: KafkaEventBus | None = None
        self.cache: CacheManager | None = None
        self.uow_factory: UnitOfWorkFactory | None = None
        self.outbox_publisher: OutboxPublisher | None = None

        # Trading services
        self.market_data: Any | None = None
        self.risk_engine: Any | None = None
        self.strategy_engine: Any | None = None
        self.execution_engine: Any | None = None
        self.broker_gateway: Any | None = None
        self.ai_orchestrator: Any | None = None
        self.auto_trader: Any | None = None
        self.position_manager: Any | None = None
        self.position_sizer: Any | None = None
        self.feature_service: Any | None = None

    async def start(self) -> None:
        """Initialize all services in dependency order."""
        settings = get_settings()

        # 1. Core infrastructure (no deps)
        await self.init_db(settings.DATABASE_URL)
        kafka_servers = getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        await self.init_event_bus(kafka_servers)
        await self.init_cache(settings.REDIS_URL)

        # 2. Feature service (cache dep)
        await self.init_feature_service()

        # 3. Broker gateway
        await self.init_broker_gateway()

        # 4. Market data (broker dep)
        await self.init_market_data()

        # 5. Strategy engine
        await self.init_strategy_engine()

        # 6. Risk engine (db dep)
        await self.init_risk_engine()

        # 7. Position sizer
        await self.init_position_sizer()

        # 8. Position manager (broker + db + event deps)
        await self.init_position_manager()

        # 9. Execution engine (risk + broker + strategy + position deps)
        await self.init_execution_engine()

        # 10. AI orchestration
        await self.init_ai_orchestrator()

        # 11. Auto trader (top-level orchestrator)
        await self.init_auto_trader()

        # 12. Outbox publisher (must be last — publishes events from all services)
        await self.init_outbox_publisher()

        logger.info("container_started", services=[k for k, v in self.__dict__.items() if v is not None])

    async def stop(self) -> None:
        """Graceful shutdown in reverse order of initialization."""
        if self.auto_trader:
            await self.auto_trader.stop()
        if self.position_manager:
            await self.position_manager.stop()
        if self.execution_engine:
            pass
        if self.outbox_publisher:
            await self.outbox_publisher.stop()
        if self.event_bus:
            await self.event_bus.close()
        if self.cache:
            await self.cache.close()
        if self.db:
            await self.db.close()
        logger.info("container_shutdown_complete")

    async def init_db(self, database_url: str, echo: bool = False, pool_size: int = 20, max_overflow: int = 10) -> None:
        self.db = DatabaseEngine(database_url=database_url, echo=echo, pool_size=pool_size, max_overflow=max_overflow)
        await self.db.initialize()
        self.uow_factory = UnitOfWorkFactory(self.db.session_factory)

    async def init_event_bus(self, bootstrap_servers: str) -> None:
        self.event_bus = KafkaEventBus(bootstrap_servers=bootstrap_servers)
        await self.event_bus.start()

    async def init_cache(self, redis_url: str) -> None:
        self.cache = CacheManager(redis_url)
        await self.cache.initialize()

    async def init_outbox_publisher(self) -> None:
        if self.event_bus is None or self.db is None:
            raise RuntimeError("event_bus and db must be initialized before outbox_publisher")
        self.outbox_publisher = OutboxPublisher(
            kafka_producer=self.event_bus,
            session_factory=self.db.session_factory,
        )
        await self.outbox_publisher.start()

    async def init_broker_gateway(self) -> None:
        from forex_trading.broker.gateway import BrokerGateway
        from forex_trading.broker.plugins import MT5BridgePlugin, MT4BridgePlugin, OANDAPlugin

        self.broker_gateway = BrokerGateway()
        self.broker_gateway.register_plugin(MT5BridgePlugin())
        self.broker_gateway.register_plugin(MT4BridgePlugin())
        self.broker_gateway.register_plugin(OANDAPlugin())

    async def init_market_data(self) -> None:
        from forex_trading.market_data.services.market_data_service import MarketDataService

        self.market_data = MarketDataService(
            cache_manager=self.cache,
            broker_gateway=self.broker_gateway,
        )

    async def init_strategy_engine(self) -> None:
        from forex_trading.strategy.engine import StrategyEngine
        from forex_trading.strategy.registry.strategy_registry import StrategyRegistry

        self.strategy_engine = StrategyEngine()
        registry = StrategyRegistry()
        for strategy in registry.all():
            self.strategy_engine.register_strategy(strategy)

    async def init_risk_engine(self) -> None:
        from forex_trading.risk.engine import RiskEngine

        if self.uow_factory is None:
            raise RuntimeError("uow_factory must be initialized before risk_engine")
        self.risk_engine = RiskEngine(uow_factory=self.uow_factory)

    async def init_position_sizer(self) -> None:
        from forex_trading.execution.services.position_sizer import PositionSizer

        self.position_sizer = PositionSizer()

    async def init_position_manager(self) -> None:
        from forex_trading.execution.position_manager import PositionManager

        if self.uow_factory is None or self.event_bus is None or self.broker_gateway is None:
            raise RuntimeError("dependencies not initialized for position_manager")
        self.position_manager = PositionManager(
            uow_factory=self.uow_factory,
            event_bus=self.event_bus,
            broker_gateway=self.broker_gateway,
        )
        await self.position_manager.start()

    async def init_execution_engine(self) -> None:
        from forex_trading.execution.engine import ExecutionEngine

        if any(
            x is None
            for x in [self.risk_engine, self.broker_gateway, self.strategy_engine, self.position_manager, self.uow_factory, self.event_bus]
        ):
            raise RuntimeError("dependencies not initialized for execution_engine")
        self.execution_engine = ExecutionEngine(
            risk_engine=self.risk_engine,
            broker_gateway=self.broker_gateway,
            strategy_engine=self.strategy_engine,
            position_manager=self.position_manager,
            uow_factory=self.uow_factory,
            event_bus=self.event_bus,
        )

    async def init_feature_service(self) -> None:
        from forex_trading.ai.services.feature_service import FeatureService

        self.feature_service = FeatureService(cache=self.cache)

    async def init_ai_orchestrator(self) -> None:
        from forex_trading.ai.orchestrator import AIOrchestrator

        if self.uow_factory is None:
            raise RuntimeError("uow_factory must be initialized before ai_orchestrator")
        self.ai_orchestrator = AIOrchestrator(
            uow_factory=self.uow_factory,
            cache=self.cache,
        )

    async def init_auto_trader(self) -> None:
        from forex_trading.execution.services.auto_trader import AutoTrader

        if any(
            x is None
            for x in [self.market_data, self.broker_gateway, self.risk_engine, self.strategy_engine, self.execution_engine, self.position_manager, self.position_sizer]
        ):
            raise RuntimeError("dependencies not initialized for auto_trader")
        self.auto_trader = AutoTrader(
            market_data=self.market_data,
            broker_gateway=self.broker_gateway,
            risk_engine=self.risk_engine,
            strategy_engine=self.strategy_engine,
            execution_engine=self.execution_engine,
            position_manager=self.position_manager,
            position_sizer=self.position_sizer,
        )
