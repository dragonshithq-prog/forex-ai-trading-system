"""User CRUD operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.crud_base import CRUDBase
from forex_trading.shared.database.models_user import User, UserSession


class UserRepository(CRUDBase[User]):
    """User repository with custom query methods."""

    async def get_by_email(self, db: AsyncSession, *, email: str) -> User | None:
        """Get user by email."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_username(self, db: AsyncSession, *, username: str) -> User | None:
        """Get user by username."""
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_active_users(self, db: AsyncSession) -> list[User]:
        """Get all active users."""
        return await self.get_multi(
            db,
            filters=[User.is_active == True, User.is_deleted == False],
        )

    async def update_last_login(self, db: AsyncSession, *, user_id: UUID) -> None:
        """Update user's last login timestamp."""
        from datetime import datetime

        user = await self.get(db, user_id)
        if user:
            user.last_login = datetime.utcnow()
            db.add(user)
            await db.commit()

    async def verify_user(self, db: AsyncSession, *, user_id: UUID) -> bool:
        """Verify user email."""
        user = await self.get(db, user_id)
        if user:
            user.is_verified = True
            db.add(user)
            await db.commit()
            return True
        return False


class UserSessionRepository(CRUDBase[UserSession]):
    """User session repository for refresh token management."""

    async def get_by_refresh_token(
        self, db: AsyncSession, *, refresh_token: str
    ) -> UserSession | None:
        """Get session by refresh token."""
        result = await db.execute(
            select(UserSession).where(UserSession.refresh_token == refresh_token)
        )
        return result.scalar_one_or_none()

    async def revoke_all_user_sessions(
        self, db: AsyncSession, *, user_id: UUID
    ) -> int:
        """Revoke all sessions for a user."""
        from sqlalchemy import update

        result = await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.is_revoked == False)
            .values(is_revoked=True)
        )
        await db.commit()
        return result.rowcount


# Repository instances
user_repository = UserRepository(User)
user_session_repository = UserSessionRepository(UserSession)
