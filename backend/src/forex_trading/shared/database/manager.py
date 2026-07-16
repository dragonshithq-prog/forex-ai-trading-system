"""Database manager - async SQLAlchemy session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
import structlog

from forex_trading.shared.database.models import Base

logger = structlog.get_logger()


class DatabaseManager:
    """
    Async database manager using SQLAlchemy 2.0.

    Provides:
    - Async session management
    - Connection pooling
    - Transaction handling
    """

    def __init__(self, database_url: str | None = None) -> None:
        from forex_trading.config import get_settings

        self._settings = get_settings()
        self._database_url = database_url or self._settings.DATABASE_URL
        self._engine = None
        self._session_factory = None

    async def initialize(self) -> None:
        """Initialize database engine and session factory."""
        self._engine = create_async_engine(
            self._database_url,
            echo=self._settings.DATABASE_ECHO,
            pool_size=self._settings.DATABASE_POOL_SIZE,
            max_overflow=self._settings.DATABASE_MAX_OVERFLOW,
        )
        # Create all tables on startup
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("database_initialized")

    async def close(self) -> None:
        """Close database engine."""
        if self._engine:
            await self._engine.dispose()
            logger.info("database_closed")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an async database session."""
        if not self._session_factory:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            from sqlalchemy import text
            async with self.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error("database_health_check_failed", error=str(e))
            return False


# Global database manager instance (lazy — created on first access to avoid circular imports)
_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def __getattr__(name: str):
    if name == "db_manager":
        return get_db_manager()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
