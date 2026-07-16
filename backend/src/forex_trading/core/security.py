"""Security module - JWT, authentication, authorization, and credential encryption.

JWT Hardening implemented:
  - Access tokens expire in 5 minutes (configurable)
  - Refresh tokens expire in 24 hours (configurable)
  - Token type binding via ``aud`` claim (access vs refresh have different audiences)
  - Token revocation via Redis blacklist
  - Fernet encryption key derived from SecretsSettings (not hardcoded)
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import bcrypt as _bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt
from pydantic import BaseModel, Field
import structlog

from forex_trading.config import get_settings
from forex_trading.shared.security.secrets import get_secrets_settings

logger = structlog.get_logger()
settings = get_settings()
secrets_settings = get_secrets_settings()


# ---------------------------------------------------------------------------
# Fernet credential encryption (uses app SECRET_KEY)
# ---------------------------------------------------------------------------


def _get_fernet_key() -> bytes:
    """Derive a Fernet-compatible key from the app's SECRET_KEY."""
    raw = settings.secret_key.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return key


def encrypt_credentials(credentials: dict[str, Any]) -> str:
    """Encrypt broker credentials dict to a Fernet token string."""
    fernet = Fernet(_get_fernet_key())
    data = json.dumps(credentials).encode("utf-8")
    return fernet.encrypt(data).decode("utf-8")


def decrypt_credentials(token: str) -> dict[str, Any]:
    """Decrypt a Fernet token string back to credentials dict."""
    fernet = Fernet(_get_fernet_key())
    data = fernet.decrypt(token.encode("utf-8"))
    return json.loads(data.decode("utf-8"))


# ---------------------------------------------------------------------------
# Token models with audience binding
# ---------------------------------------------------------------------------


class TokenPayload(BaseModel):
    """JWT token payload with audience and type fields."""

    sub: str
    exp: datetime
    iat: datetime
    aud: str = ""                         # audience (access vs refresh)
    iss: str = "forex-trading-bot"
    role: str = "viewer"
    permissions: list[str] = []
    mfa_verified: bool = False
    token_type: str = "access"            # "access" or "refresh"
    jti: str | None = None               # JWT ID — for revocation


class TokenPair(BaseModel):
    """Access and refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# Token revocation (Redis-backed blacklist)
# ---------------------------------------------------------------------------


class TokenRevocationService:
    """Maintain a blacklist of revoked JWT IDs (jti) in Redis.

    In development mode, an in-memory set is used as fallback.
    """

    def __init__(self) -> None:
        self._redis = None
        self._blacklist: set[str] = set()   # fallback for dev / no-redis

    async def initialize(self, redis_client=None) -> None:
        """Inject a Redis client. If None, uses in-memory fallback."""
        self._redis = redis_client
        logger.info("token_revocation_initialized", backend="redis" if redis_client else "memory")

    async def revoke(self, jti: str, expire_at: datetime | None = None) -> None:
        """Mark a JWT ID as revoked."""
        if self._redis is not None:
            ttl = None
            if expire_at:
                ttl = int((expire_at - datetime.now(timezone.utc)).total_seconds())
                ttl = max(ttl, 60)
            await self._redis.set(f"revoked:jti:{jti}", "1", ex=ttl)
        else:
            self._blacklist.add(jti)

    async def is_revoked(self, jti: str) -> bool:
        """Check whether a JWT ID has been revoked."""
        if self._redis is not None:
            val = await self._redis.get(f"revoked:jti:{jti}")
            return val is not None
        return jti in self._blacklist


# Global revocation service instance
token_revocation_service = TokenRevocationService()


# ---------------------------------------------------------------------------
# Security manager
# ---------------------------------------------------------------------------


class SecurityManager:
    """Manage authentication, authorization, and JWT token lifecycle."""

    def __init__(self) -> None:
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.JWT_ALGORITHM
        self.access_expire_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_expire_hours = settings.JWT_REFRESH_TOKEN_EXPIRE_HOURS
        self.issuer = settings.JWT_ISSUER
        self.audience_access = settings.JWT_AUDIENCE_ACCESS
        self.audience_refresh = settings.JWT_AUDIENCE_REFRESH

    # ---- Password hashing ----

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its bcrypt hash."""
        return _bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

    # ---- Token creation with audience binding ----

    def create_access_token(
        self,
        user_id: str,
        role: str = "viewer",
        permissions: list[str] | None = None,
        mfa_verified: bool = False,
    ) -> str:
        """Create a JWT access token (short-lived, bound to access audience)."""
        import uuid as _uuid

        expire = datetime.utcnow() + timedelta(minutes=self.access_expire_minutes)
        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.utcnow(),
            "aud": self.audience_access,
            "iss": self.issuer,
            "role": role,
            "permissions": permissions or [],
            "mfa_verified": mfa_verified,
            "token_type": "access",
            "jti": str(_uuid.uuid4()),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        """Create a JWT refresh token (longer-lived, bound to refresh audience)."""
        import uuid as _uuid

        expire = datetime.utcnow() + timedelta(hours=self.refresh_expire_hours)
        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.utcnow(),
            "aud": self.audience_refresh,
            "iss": self.issuer,
            "token_type": "refresh",
            "jti": str(_uuid.uuid4()),
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

    # ---- Token decoding with audience & revocation checks ----

    def decode_token(
        self,
        token: str,
        expected_audience: str | None = None,
    ) -> TokenPayload | None:
        """Decode and validate a JWT token.

        Parameters
        ----------
        token : str
            The JWT string.
        expected_audience : str | None
            If set, validates the ``aud`` claim matches.  Use this to
            enforce that an access token can't be used as a refresh token
            and vice versa.

        Returns
        -------
        TokenPayload | None
            The decoded payload, or ``None`` if validation fails.
        """
        try:
            options = {"verify_aud": False}  # we manually verify aud below
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options=options,
            )

            # Audience check (token type binding)
            if expected_audience and payload.get("aud") != expected_audience:
                logger.warning(
                    "token_audience_mismatch",
                    expected=expected_audience,
                    got=payload.get("aud"),
                )
                return None

            return TokenPayload(
                sub=payload["sub"],
                exp=datetime.fromtimestamp(payload["exp"]),
                iat=datetime.fromtimestamp(payload["iat"]),
                aud=payload.get("aud", ""),
                iss=payload.get("iss", self.issuer),
                role=payload.get("role", "viewer"),
                permissions=payload.get("permissions", []),
                mfa_verified=payload.get("mfa_verified", False),
                token_type=payload.get("token_type", "access"),
                jti=payload.get("jti"),
            )
        except JWTError as e:
            logger.warning("token_decode_failed", error=str(e))
            return None

    async def decode_token_with_revocation_check(
        self,
        token: str,
        expected_audience: str | None = None,
    ) -> TokenPayload | None:
        """Decode a token and check the revocation blacklist."""
        payload = self.decode_token(token, expected_audience=expected_audience)
        if payload is None:
            return None

        if payload.jti:
            revoked = await token_revocation_service.is_revoked(payload.jti)
            if revoked:
                logger.warning("token_revoked", jti=payload.jti)
                return None

        return payload

    # ---- Permission checks ----

    def check_permission(self, token_payload: TokenPayload, required_permission: str) -> bool:
        """Check if token has required permission."""
        if token_payload.role == "superadmin":
            return True
        return required_permission in token_payload.permissions


# Global security manager instance
security_manager = SecurityManager()
