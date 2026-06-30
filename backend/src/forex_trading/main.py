"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import structlog

from forex_trading.config import get_settings
from forex_trading.core.exceptions import setup_exception_handlers
from forex_trading.core.middleware import setup_middleware
from forex_trading.api.router import api_router
from forex_trading.api.websocket import router as ws_router
from forex_trading.shared.database import db_manager
from forex_trading.shared.cache import cache_manager

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("starting_application", version=settings.APP_VERSION)
    await connect_to_databases()
    await connect_to_cache()
    await connect_to_message_bus()
    await start_background_tasks()

    yield

    # Shutdown
    logger.info("shutting_down_application")
    await stop_background_tasks()
    await disconnect_from_message_bus()
    await disconnect_from_cache()
    await disconnect_from_databases()


async def connect_to_databases() -> None:
    """Establish database connections."""
    logger.info("connecting_to_databases")
    await db_manager.initialize()


async def disconnect_from_databases() -> None:
    """Close database connections."""
    logger.info("disconnecting_from_databases")
    await db_manager.close()


async def connect_to_cache() -> None:
    """Connect to Redis cache."""
    logger.info("connecting_to_cache")
    await cache_manager.initialize()


async def disconnect_from_cache() -> None:
    """Disconnect from Redis cache."""
    logger.info("disconnecting_from_cache")
    await cache_manager.close()


async def connect_to_message_bus() -> None:
    """Connect to message bus (RabbitMQ)."""
    logger.info("connecting_to_message_bus")


async def disconnect_from_message_bus() -> None:
    """Disconnect from message bus."""
    logger.info("disconnecting_from_message_bus")


async def start_background_tasks() -> None:
    """Start background services."""
    logger.info("starting_background_tasks")


async def stop_background_tasks() -> None:
    """Stop background services."""
    logger.info("stopping_background_tasks")


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Institutional-grade autonomous AI Forex trading ecosystem",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.is_production:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*.yourdomain.com", "yourdomain.com"],
        )

    # Exception handlers
    setup_exception_handlers(application)

    # Additional middleware
    setup_middleware(application)

    # Include API routers
    application.include_router(api_router, prefix=settings.API_PREFIX)
    application.include_router(ws_router)

    # Health check endpoint
    @application.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "version": settings.APP_VERSION}

    @application.get("/health/detailed")
    async def detailed_health() -> dict[str, str]:
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT.value,
        }

    return application


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "forex_trading.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=settings.WORKERS if not settings.DEBUG else 1,
        log_level=settings.LOG_LEVEL.lower(),
    )
