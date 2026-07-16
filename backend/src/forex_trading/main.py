"""FastAPI application entry point — wired via dependency injection container.

Security hardening:
  - Production secret validation (fail-fast on missing secrets)
  - Rate limiting (Redis sliding window)
  - Audit logging middleware for sensitive operations
  - Enhanced security headers (CSP, HSTS preload, Permissions-Policy)
  - Request size limiting
  - Token revocation service initialization
  - Startup dependency health check
  - Graceful shutdown with connection draining
  - Config logging on startup (secrets masked)
"""

from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_client import make_asgi_app
import structlog

from forex_trading.config import get_settings, validate_production_settings
from forex_trading.core.exceptions import setup_exception_handlers
from forex_trading.core.middleware import setup_middleware
from forex_trading.core.rate_limit import RateLimiter, RateLimitMiddleware
from forex_trading.api.router import api_router
from forex_trading.api.websocket import router as ws_router
from forex_trading.shared.di import Container
from forex_trading.shared.monitoring.logging import configure_logging
from forex_trading.shared.monitoring.tracing import configure_tracing, shutdown_tracing

logger = structlog.get_logger()
settings = get_settings()

_container: Container | None = None
_rate_limiter: RateLimiter | None = None

# Graceful shutdown configuration
_SHUTDOWN_TIMEOUT_SECONDS: int = 30
_SHUTDOWN_EVENT: asyncio.Event = asyncio.Event()


async def check_startup_dependencies() -> dict[str, str]:
    """Check all core service dependencies at startup.

    Returns a dict of {service_name: status} where status is 'ok' or 'error'.
    Does NOT block startup — failed dependencies are logged as warnings
    (the ready check will report them as degraded).
    """
    checks: dict[str, str] = {}

    # Container-level checks
    if _container is None:
        logger.warning("startup_dependency_check", service="container", status="not_initialized")
        return checks

    # Database
    if _container.db is not None:
        try:
            db_ok = await asyncio.wait_for(_container.db.health_check(), timeout=5.0)
            checks["database"] = "ok" if db_ok else "degraded"
            if not db_ok:
                logger.warning("startup_dependency_check", service="database", status="degraded")
        except asyncio.TimeoutError:
            checks["database"] = "timeout"
            logger.warning("startup_dependency_check", service="database", status="timeout")
        except Exception as exc:
            checks["database"] = "error"
            logger.warning("startup_dependency_check", service="database", status="error", error=str(exc))

    # Cache (Redis)
    if _container.cache is not None:
        try:
            cache_ok = await asyncio.wait_for(_container.cache.health_check(), timeout=5.0)
            checks["cache"] = "ok" if cache_ok else "degraded"
        except Exception as exc:
            checks["cache"] = "error"
            logger.warning("startup_dependency_check", service="cache", status="error", error=str(exc))

    # Event bus (Kafka)
    if _container.event_bus is not None:
        try:
            eb_ok = await asyncio.wait_for(_container.event_bus.health_check(), timeout=5.0)
            checks["event_bus"] = "ok" if eb_ok else "degraded"
        except Exception as exc:
            checks["event_bus"] = "error"
            logger.warning("startup_dependency_check", service="event_bus", status="error", error=str(exc))

    # Rate limiter
    if _rate_limiter is not None:
        try:
            rl_ok = await asyncio.wait_for(_rate_limiter.health_check(), timeout=5.0)
            checks["rate_limiter"] = "ok" if rl_ok else "degraded"
        except Exception:
            checks["rate_limiter"] = "error"

    return checks


async def drain_connections(timeout: int = _SHUTDOWN_TIMEOUT_SECONDS) -> None:
    """Drain all active connections gracefully before shutdown."""
    logger.info("draining_connections", timeout_seconds=timeout)

    if _rate_limiter:
        try:
            await asyncio.wait_for(_rate_limiter.close(), timeout=timeout // 3)
            logger.info("rate_limiter_closed")
        except asyncio.TimeoutError:
            logger.warning("rate_limiter_close_timeout")
        except Exception as exc:
            logger.warning("rate_limiter_close_error", error=str(exc))

    if _container:
        try:
            await asyncio.wait_for(_container.stop(), timeout=timeout // 3)
            logger.info("container_stopped")
        except asyncio.TimeoutError:
            logger.warning("container_stop_timeout")
        except Exception as exc:
            logger.warning("container_stop_error", error=str(exc))

    try:
        shutdown_tracing()
        logger.info("tracing_shutdown")
    except Exception as exc:
        logger.warning("tracing_shutdown_error", error=str(exc))

    logger.info("connections_drained")


def handle_signal(sig: int, frame) -> None:
    """Handle OS termination signals for graceful shutdown."""
    sig_name = signal.Signals(sig).name
    logger.info("received_signal", signal=sig_name)
    _SHUTDOWN_EVENT.set()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _container, _rate_limiter

    logger.info("starting_application", version=settings.APP_VERSION)

    # Register OS signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # ---- Fail-fast in production if secrets are missing ----
    validate_production_settings()

    # ---- Log loaded configuration (secrets masked) ----
    logger.info(
        "configuration",
        app_name=settings.APP_NAME,
        environment=settings.ENVIRONMENT.value,
        log_level=settings.LOG_LEVEL,
        log_format=settings.LOG_FORMAT,
        api_prefix=settings.API_PREFIX,
        database_pool_size=settings.DATABASE_POOL_SIZE,
        redis_max_connections=settings.REDIS_MAX_CONNECTIONS,
        workers=settings.WORKERS,
        prometheus_enabled=settings.PROMETHEUS_ENABLED,
        config=settings.get_safe_dict(),
    )

    configure_logging(
        log_level=settings.LOG_LEVEL,
        log_format=settings.LOG_FORMAT,
    )

    if settings.PROMETHEUS_ENABLED:
        logger.info("prometheus_enabled", port=settings.PROMETHEUS_PORT)

    configure_tracing(
        service_name=settings.APP_NAME,
        jaeger_endpoint=settings.JAEGER_ENDPOINT if not settings.is_production else None,
    )

    # ---- Initialize DI container ----
    _container = Container()
    await _container.start()

    # ---- Initialize rate limiter ----
    try:
        _rate_limiter = RateLimiter(redis_url=settings.REDIS_URL)
        await _rate_limiter.initialize()
    except Exception as exc:
        logger.warning("rate_limiter_init_failed", error=str(exc))
        _rate_limiter = None

    # ---- Initialize token revocation service ----
    try:
        from forex_trading.core.security import token_revocation_service
        if _container and _container.cache and hasattr(_container.cache, '_redis'):
            await token_revocation_service.initialize(_container.cache._redis)
        else:
            await token_revocation_service.initialize(None)
    except Exception as exc:
        logger.warning("token_revocation_init_failed", error=str(exc))

    # ---- Startup dependency check (non-blocking) ----
    try:
        dep_checks = await check_startup_dependencies()
        all_ok = all(v == "ok" for v in dep_checks.values())
        if all_ok:
            logger.info("startup_dependencies_ok", checks=dep_checks)
        else:
            logger.warning("startup_dependencies_degraded", checks=dep_checks)
    except Exception as exc:
        logger.warning("startup_dependency_check_failed", error=str(exc))

    yield

    # ---- Graceful shutdown ----
    logger.info("shutdown_initiated", timeout_seconds=_SHUTDOWN_TIMEOUT_SECONDS)

    try:
        # Wait for signal or timeout, whichever comes first
        shutdown_task = asyncio.create_task(_SHUTDOWN_EVENT.wait())
        done, pending = await asyncio.wait(
            [shutdown_task],
            timeout=_SHUTDOWN_TIMEOUT_SECONDS,
        )
    except Exception:
        pass

    await drain_connections(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
    _container = None
    _rate_limiter = None
    logger.info("shutdown_complete")


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Institutional-grade autonomous AI Forex trading ecosystem",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ---- CORS ----
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Trusted hosts (production only) ----
    if settings.is_production:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*.yourdomain.com", "yourdomain.com"],
        )

    # ---- Core middleware (order matters: outer → inner) ----
    setup_exception_handlers(application)
    setup_middleware(application)

    # ---- Rate limiting middleware ----
    application.add_middleware(RateLimitMiddleware, rate_limiter=_rate_limiter)

    # Mount Prometheus metrics endpoint
    if settings.PROMETHEUS_ENABLED:
        metrics_app = make_asgi_app()
        application.mount("/metrics", metrics_app)

    application.include_router(api_router, prefix=settings.API_PREFIX)
    application.include_router(ws_router)

    @application.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "version": settings.APP_VERSION}

    @application.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @application.get("/health/ready")
    async def readiness() -> dict[str, str]:
        statuses = {"app": "ok"}
        if _container is not None:
            if _container.db:
                try:
                    healthy = await _container.db.health_check()
                    statuses["database"] = "ok" if healthy else "degraded"
                except Exception:
                    statuses["database"] = "error"
            if _container.cache:
                try:
                    healthy = await _container.cache.health_check()
                    statuses["cache"] = "ok" if healthy else "degraded"
                except Exception:
                    statuses["cache"] = "error"
            if _container.event_bus:
                try:
                    healthy = await _container.event_bus.health_check()
                    statuses["event_bus"] = "ok" if healthy else "degraded"
                except Exception:
                    statuses["event_bus"] = "error"
            # Rate limiter health
            if _rate_limiter is not None:
                statuses["rate_limiter"] = "ok"
        all_ok = all(v == "ok" for v in statuses.values())
        return {
            "status": "ok" if all_ok else "degraded",
            "checks": statuses,
        }

    @application.get("/health/detailed")
    async def detailed_health() -> dict[str, str]:
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT.value,
        }

    return application


app = create_application()


def get_container() -> Container:
    if _container is None:
        raise RuntimeError("Container not initialized — application not started")
    return _container


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
