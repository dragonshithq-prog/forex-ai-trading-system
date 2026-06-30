"""User CRUD operations."""

import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.crud_base import CRUDBase
from forex_trading.shared.database.models_user import (
    User,
    UserSession,
    PasswordResetToken,
)

MAX_FAILED_LOGIN_ATTEMPTS = 5
ACCOUNT_LOCKOUT_MINUTES = 15


class UserRepository(CRUDBase[User]):
    """User repository with custom query methods."""

    async def get_by_email(self, db: AsyncSession, *, email: str) -> User | None:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_username(self, db: AsyncSession, *, username: str) -> User | None:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_active_users(self, db: AsyncSession) -> list[User]:
        return await self.get_multi(
            db,
            filters=[User.is_active == True, User.is_deleted == False],
        )

    async def update_last_login(self, db: AsyncSession, *, user_id: UUID) -> None:
        user = await self.get(db, user_id)
        if user:
            user.last_login = datetime.utcnow()
            user.failed_login_attempts = 0
            user.locked_until = None
            db.add(user)
            await db.commit()

    async def record_failed_login(self, db: AsyncSession, *, user_id: UUID) -> bool:
        user = await self.get(db, user_id)
        if not user:
            return False
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=ACCOUNT_LOCKOUT_MINUTES)
        db.add(user)
        await db.commit()
        return True

    async def is_account_locked(self, user: User) -> bool:
        if user.locked_until and user.locked_until > datetime.utcnow():
            return True
        if user.locked_until and user.locked_until <= datetime.utcnow():
            user.locked_until = None
            user.failed_login_attempts = 0
        return False

    async def update_role(self, db: AsyncSession, *, user_id: UUID, role: str) -> User | None:
        user = await self.get(db, user_id)
        if not user:
            return None
        from forex_trading.shared.database.models_user import UserRole
        user.role = UserRole(role)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def set_active_status(self, db: AsyncSession, *, user_id: UUID, is_active: bool) -> User | None:
        user = await self.get(db, user_id)
        if not user:
            return None
        user.is_active = is_active
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def admin_reset_password(self, db: AsyncSession, *, user_id: UUID, new_hashed_password: str) -> bool:
        user = await self.get(db, user_id)
        if not user:
            return False
        user.hashed_password = new_hashed_password
        user.failed_login_attempts = 0
        user.locked_until = None
        db.add(user)
        await db.commit()
        from forex_trading.shared.database.crud_user import user_session_repository
        await user_session_repository.revoke_all_user_sessions(db, user_id=user_id)
        return True

    async def verify_user(self, db: AsyncSession, *, user_id: UUID) -> bool:
        user = await self.get(db, user_id)
        if user:
            user.is_verified = True
            db.add(user)
            await db.commit()
            return True
        return False


class PasswordResetRepository(CRUDBase[PasswordResetToken]):
    """Repository for password reset tokens."""

    async def create_token(self, db: AsyncSession, *, user_id: UUID) -> PasswordResetToken:
        token_str = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        obj = await self.create(db, obj_in={
            "user_id": user_id,
            "token": token_str,
            "expires_at": expires_at,
            "is_used": False,
        })
        return obj

    async def get_by_token(self, db: AsyncSession, *, token: str) -> PasswordResetToken | None:
        result = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token == token,
                PasswordResetToken.is_used == False,
                PasswordResetToken.expires_at > datetime.utcnow(),
            )
        )
        return result.scalar_one_or_none()

    async def mark_used(self, db: AsyncSession, *, token_id: UUID) -> None:
        await db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.id == token_id)
            .values(is_used=True)
        )
        await db.commit()


class UserSessionRepository(CRUDBase[UserSession]):
    """User session repository for refresh token management."""

    async def get_by_refresh_token(
        self, db: AsyncSession, *, refresh_token: str
    ) -> UserSession | None:
        result = await db.execute(
            select(UserSession).where(UserSession.refresh_token == refresh_token)
        )
        return result.scalar_one_or_none()

    async def revoke_all_user_sessions(
        self, db: AsyncSession, *, user_id: UUID
    ) -> int:
        result = await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.is_revoked == False)
            .values(is_revoked=True)
        )
        await db.commit()
        return result.rowcount


user_repository = UserRepository(User)
password_reset_repository = PasswordResetRepository(PasswordResetToken)
user_session_repository = UserSessionRepository(UserSession)
