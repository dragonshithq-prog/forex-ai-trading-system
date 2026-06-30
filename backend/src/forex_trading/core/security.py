"""Security module - JWT, authentication, and authorization."""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import structlog

from forex_trading.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str
    exp: datetime
    iat: datetime
    role: str = "viewer"
    permissions: list[str] = []
    mfa_verified: bool = False


class TokenPair(BaseModel):
    """Access and refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class SecurityManager:
    """Manage authentication and authorization."""

    def __init__(self) -> None:
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_expire_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_expire_days = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS

    def hash_password(self, password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(
        self,
        user_id: str,
        role: str = "viewer",
        permissions: list[str] | None = None,
        mfa_verified: bool = False,
    ) -> str:
        """Create a JWT access token."""
        expire = datetime.utcnow() + timedelta(minutes=self.access_expire_minutes)
        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.utcnow(),
            "role": role,
            "permissions": permissions or [],
            "mfa_verified": mfa_verified,
            "type": "access",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        """Create a JWT refresh token."""
        expire = datetime.utcnow() + timedelta(days=self.refresh_expire_days)
        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_token_pair(
        self,
        user_id: str,
        role: str = "viewer",
        permissions: list[str] | None = None,
    ) -> TokenPair:
        """Create access and refresh token pair."""
        access_token = self.create_access_token(user_id, role, permissions)
        refresh_token = self.create_refresh_token(user_id)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.access_expire_minutes * 60,
        )

    def decode_token(self, token: str) -> TokenPayload | None:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return TokenPayload(
                sub=payload["sub"],
                exp=datetime.fromtimestamp(payload["exp"]),
                iat=datetime.fromtimestamp(payload["iat"]),
                role=payload.get("role", "viewer"),
                permissions=payload.get("permissions", []),
                mfa_verified=payload.get("mfa_verified", False),
            )
        except JWTError as e:
            logger.warning("token_decode_failed", error=str(e))
            return None

    def check_permission(self, token_payload: TokenPayload, required_permission: str) -> bool:
        """Check if token has required permission."""
        if token_payload.role == "superadmin":
            return True
        return required_permission in token_payload.permissions


# Global security manager instance
security_manager = SecurityManager()
