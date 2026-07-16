"""Async database engine factory with performance optimizations.

Optimizations:
- Connection pool timeout, max overflow, and pre-ping with exponential backoff
- Query timeout configuration via dialect-level settings
- Statement cache size tuning (asyncpg)
- Prepared statement caching for asyncpg connections
- Pool status metrics for monitoring
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from forex_trading.shared.monitoring import db_pool_size

logger = structlog.get_logger()

# Default performance tuning values
_DEFAULT_POOL_SIZE = 20
_DEFAULT_MAX_OVERFLOW = 10
_DEFAULT_POOL_TIMEOUT = 30  # seconds
_DEFAULT_POOL_RECYCLE = 3600  # seconds
_DEFAULT_POOL_PRE_PING = True
_DEFAULT_QUERY_TIMEOUT = 30  # seconds
_DEFAULT_STATEMENT_CACHE_SIZE = 500
_DEFAULT_MAX_BACKOFF = 60  # seconds for exponential backoff


class DatabaseEngine:
    """Wraps an async SQLAlchemy engine with performance-optimized connection pooling.

    Explicitly NOT a singleton. Created once per application instance
    and injected via the DI container.

    Features:
    - Connection pool with timeout, overflow, and pre-ping
    - Exponential backoff on connection failure
    - Query timeout configuration
    - Statement cache size tuning for asyncpg
    - Pool status metrics exported to Prometheus
    """

    def __init__(
        self,
        database_url: str,
        echo: bool = False,
        pool_size: int | None = None,
        max_overflow: int | None = None,
        pool_timeout: int = _DEFAULT_POOL_TIMEOUT,
        pool_pre_ping: bool = _DEFAULT_POOL_PRE_PING,
        pool_recycle: int = _DEFAULT_POOL_RECYCLE,
        query_timeout: int = _DEFAULT_QUERY_TIMEOUT,
        statement_cache_size: int = _DEFAULT_STATEMENT_CACHE_SIZE,
        max_backoff_seconds: int = _DEFAULT_MAX_BACKOFF,
    ) -> None:
        self._url = database_url
        self._echo = echo
        self._pool_size = pool_size or _DEFAULT_POOL_SIZE
        self._max_overflow = max_overflow or _DEFAULT_MAX_OVERFLOW
        self._pool_timeout = pool_timeout
        self._pool_pre_ping = pool_pre_ping
        self._pool_recycle = pool_recycle
        self._query_timeout = query_timeout
        self._statement_cache_size = statement_cache_size
        self._max_backoff = max_backoff_seconds

        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

        # Backoff state for pre-ping failures
        self._consecutive_failures = 0
        self._last_failure_time: float | None = None

        # Periodic pool metrics task
        self._metrics_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """Create the engine and session factory with optimized pooling."""
        engine_kwargs: dict[str, Any] = {
            "echo": self._echo,
            "pool_pre_ping": self._pool_pre_ping,
            "pool_recycle": self._pool_recycle,
        }

        # Determine dialect and apply appropriate settings
        is_sqlite = "aiosqlite" in self._url
        is_asyncpg = "asyncpg" in self._url

        if is_sqlite:
            # SQLite uses StaticPool — pool params not supported
            engine_kwargs["connect_args"] = {
                "timeout": self._query_timeout,
            }
        else:
            # PostgreSQL / asyncpg — apply pooling and optimizations
            engine_kwargs["pool_size"] = self._pool_size
            engine_kwargs["max_overflow"] = self._max_overflow
            engine_kwargs["pool_timeout"] = self._pool_timeout

        if is_asyncpg:
            engine_kwargs.update({
                "connect_args": {
                    "statement_cache_size": self._statement_cache_size,
                    "prepared_statement_cache_size": self._statement_cache_size,
                    "timeout": self._query_timeout,
                },
                "json_serializer": _json_serializer,
                "json_deserializer": _json_deserializer,
            })

        self._engine = create_async_engine(self._url, **engine_kwargs)

        # Set query timeout at the execution level
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            info={"query_timeout": self._query_timeout},
        )

        # Start pool metrics reporting
        self._metrics_task = asyncio.create_task(self._report_pool_metrics())

        logger.info(
            "database_engine_initialized",
            pool_size=self._pool_size,
            max_overflow=self._max_overflow,
            pool_timeout=self._pool_timeout,
            pool_pre_ping=self._pool_pre_ping,
            pool_recycle=self._pool_recycle,
            query_timeout=self._query_timeout,
            statement_cache_size=self._statement_cache_size,
        )

    async def close(self) -> None:
        """Dispose of the engine and cancel metrics task."""
        if self._metrics_task:
            self._metrics_task.cancel()
            try:
                await self._metrics_task
            except asyncio.CancelledError:
                pass
            self._metrics_task = None

        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._consecutive_failures = 0
            logger.info("database_engine_closed")

    def _get_execution_options(self) -> dict[str, Any]:
        """Return execution options including query timeout."""
        options: dict[str, Any] = {}
        if "asyncpg" in self._url:
            # asyncpg supports statement timeout per execution
            options.setdefault("statement_timeout", self._query_timeout * 1000)  # milliseconds
        return options

    async def get_session(self) -> AsyncSession:
        """Get a new session with execution options applied."""
        if self._session_factory is None:
            raise RuntimeError("DatabaseEngine not initialized. Call initialize() first.")
        session = self._session_factory()
        if self._query_timeout:
            options = self._get_execution_options()
            if options:
                session = session.execution_options(**options)
        return session

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError("DatabaseEngine not initialized. Call initialize() first.")
        return self._session_factory

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("DatabaseEngine not initialized. Call initialize() first.")
        return self._engine

    async def health_check(self) -> bool:
        """Return True if the database is reachable, with exponential backoff."""
        if self._engine is None:
            return False

        # Apply exponential backoff if we have consecutive failures
        if self._consecutive_failures > 0:
            backoff = min(
                2 ** self._consecutive_failures,
                self._max_backoff,
            )
            if self._last_failure_time and (time.monotonic() - self._last_failure_time) < backoff:
                return False

        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            self._consecutive_failures = 0
            self._last_failure_time = None
            return True
        except Exception as exc:
            self._consecutive_failures += 1
            self._last_failure_time = time.monotonic()
            logger.error(
                "database_health_check_failed",
                error=str(exc),
                consecutive_failures=self._consecutive_failures,
            )
            return False

    async def _report_pool_metrics(self) -> None:
        """Periodically report pool status to Prometheus."""
        while True:
            try:
                await asyncio.sleep(15)
                if self._engine is not None:
                    pool = self._engine.pool
                    if hasattr(pool, "size"):
                        db_pool_size.labels(state="total").set(pool.size())
                    if hasattr(pool, "checkedin"):
                        db_pool_size.labels(state="checkedin").set(pool.checkedin())
                    if hasattr(pool, "overflow"):
                        db_pool_size.labels(state="overflow").set(pool.overflow())
                    db_pool_size.labels(state="consecutive_failures").set(self._consecutive_failures)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    @property
    def pool_status(self) -> dict[str, Any]:
        """Return current pool status for debugging."""
        if self._engine is None:
            return {"status": "not_initialized"}
        pool = self._engine.pool
        status: dict[str, Any] = {
            "pool_size": self._pool_size,
            "max_overflow": self._max_overflow,
            "pool_timeout": self._pool_timeout,
            "pool_recycle": self._pool_recycle,
            "pool_pre_ping": self._pool_pre_ping,
            "query_timeout": self._query_timeout,
            "statement_cache_size": self._statement_cache_size,
            "consecutive_failures": self._consecutive_failures,
            "url_driver": self._url.split("://")[0] if "://" in self._url else "unknown",
        }
        if hasattr(pool, "size"):
            status["current_size"] = pool.size()
        if hasattr(pool, "checkedin"):
            status["checkedin"] = pool.checkedin()
        if hasattr(pool, "overflow"):
            status["overflow"] = pool.overflow()
        return status


def _json_serializer(obj: Any) -> str:
    """Fast JSON serialization for asyncpg."""
    import json
    return json.dumps(obj, default=str)


def _json_deserializer(data: str) -> Any:
    """Fast JSON deserialization for asyncpg."""
    import json
    return json.loads(data)
