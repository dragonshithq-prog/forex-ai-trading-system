"""API dependencies for dependency injection."""

from typing import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.config import get_settings
from forex_trading.core.security import security_manager, TokenPayload
from forex_trading.shared.database import db_manager
from forex_trading.shared.database.crud_user import user_repository
from forex_trading.shared.database.crud_broker import broker_account_repository
from forex_trading.shared.database.crud_trading import (
    order_repository,
    position_repository,
)
from forex_trading.shared.database.crud_strategy import (
    strategy_repository,
    ai_decision_repository,
)
from forex_trading.shared.database.crud_risk import (
    risk_config_repository,
    risk_state_repository,
)
from forex_trading.shared.database.models_user import User

settings = get_settings()
security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.session() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = security_manager.decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await user_repository.get(db, UUID(payload.sub))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User email not verified",
        )
    return current_user


def require_role(*roles: str):
    async def check_role(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role.value not in roles and current_user.role.value != "superadmin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {', '.join(roles)}",
            )
        return current_user

    return check_role


def require_permission(permission: str):
    async def check_permission(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role.value == "superadmin":
            return current_user

        user_permissions = (
            current_user.preferences.get("permissions", [])
            if current_user.preferences
            else []
        )
        if permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required permission: {permission}",
            )
        return current_user

    return check_permission


# Convenience role aliases
require_trader = require_role("trader", "admin", "superadmin")
require_admin = require_role("admin", "superadmin")


# Repository dependencies
def get_user_repository():
    return user_repository


def get_broker_account_repository():
    return broker_account_repository


def get_order_repository():
    return order_repository


def get_position_repository():
    return position_repository


def get_strategy_repository():
    return strategy_repository


def get_risk_config_repository():
    return risk_config_repository
