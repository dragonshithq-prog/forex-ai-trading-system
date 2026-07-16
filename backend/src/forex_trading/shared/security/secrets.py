"""Secret management with strict validation, fail-fast, and pluggable backends.

Supports Vault/HSM integration via a pluggable backend pattern.
Never logs or prints secret values. Always validates secrets exist in
production before allowing the application to start.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import structlog
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Pluggable secret backend
# ---------------------------------------------------------------------------


class SecretBackend(ABC):
    """Abstract base for a secret-store backend (Vault, HSM, env, etc.)."""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Retrieve a secret by key. Return None if not found."""

    @abstractmethod
    async def set(self, key: str, value: str) -> None:
        """Store a secret."""

    @abstractmethod
    async def rotate(self, key: str, new_value: str) -> None:
        """Rotate a secret value."""


class EnvironmentBackend(SecretBackend):
    """Read secrets from environment variables (default backend)."""

    async def get(self, key: str) -> str | None:
        return os.environ.get(key)

    async def set(self, key: str, value: str) -> None:
        os.environ[key] = value

    async def rotate(self, key: str, new_value: str) -> None:
        old = os.environ.get(key)
        os.environ[key] = new_value
        if old:
            logger.info("secret_rotated", key=key, backend="env")


# ---------------------------------------------------------------------------
# Secrets settings — validates required secrets in production
# ---------------------------------------------------------------------------

SECRET_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-!@#$%^&*()+=]{32,}$")
# Require at least 32 characters with mixed content for production keys


class SecretsSettings(BaseSettings):
    """Strict secrets loaded from environment / .env.

    In production (``ENVIRONMENT=production``) the application will
    **fail to start** if any required secret is missing or uses the
    default development placeholder.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Never print or log secret values
        secrets_dir="/run/secrets" if os.path.exists("/run/secrets") else None,
    )

    # Application
    ENVIRONMENT: str = Field(default="development", alias="ENVIRONMENT")
    SECRET_KEY: str = Field(default="change-me-in-production-use-vault", min_length=16)

    # JWT
    JWT_SECRET_KEY: str = Field(default="jwt-secret-change-in-production", min_length=16)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 5
    JWT_REFRESH_TOKEN_EXPIRE_HOURS: int = 24

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./forex_trading.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Broker API keys (optional but warned if missing in production)
    OANDA_API_KEY: str | None = None
    OANDA_ACCOUNT_ID: str | None = None

    # Notification tokens
    SLACK_WEBHOOK_URL: str | None = None
    TELEGRAM_BOT_TOKEN: str | None = None

    # Kafka / Messaging
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

    # Encryption
    ENCRYPTION_KEY: str | None = None

    # ---- Backend reference ----
    _backend: SecretBackend | None = None

    @field_validator("SECRET_KEY", "JWT_SECRET_KEY")
    @classmethod
    def _production_secrets_must_be_strong(cls, v: str, info: Any) -> str:
        """In production, refuse default / weak secret values."""
        field_name = info.field_name if info else "secret"
        defaults = {
            "SECRET_KEY": "change-me-in-production-use-vault",
            "JWT_SECRET_KEY": "jwt-secret-change-in-production",
        }
        if v == defaults.get(field_name, "__not_a_default__"):
            # In production this would be a hard failure, but we let the
            # caller decide.  The ``fail_fast`` method below does the kill.
            logger.warning(
                "secret_uses_default_value",
                field=field_name,
                hint="Set a strong value in your .env or environment",
            )
        if not SECRET_KEY_PATTERN.match(v):
            logger.warning(
                "secret_may_be_weak",
                field=field_name,
                hint="Use at least 32 characters with mixed symbols",
            )
        return v

    def set_backend(self, backend: SecretBackend) -> None:
        """Swap the secret backend (e.g. to Vault)."""
        self._backend = backend

    async def resolve(self, key: str) -> str | None:
        """Resolve a secret from the configured backend, falling back to env."""
        if self._backend is not None:
            try:
                value = await self._backend.get(key)
                if value is not None:
                    return value
            except Exception:
                logger.warning("secret_backend_failed", key=key, backend=type(self._backend).__name__)
        return getattr(self, key, None) or os.environ.get(key)

    def fail_fast(self) -> None:
        """Crash the process if we are in production and required secrets are missing.

        Call this during application startup **after** loading settings.
        """
        if self.ENVIRONMENT != "production":
            return

        required: list[tuple[str, str]] = [
            ("SECRET_KEY", self.SECRET_KEY),
            ("JWT_SECRET_KEY", self.JWT_SECRET_KEY),
            ("DATABASE_URL", self.DATABASE_URL),
            ("REDIS_URL", self.REDIS_URL),
        ]

        defaults = {
            "SECRET_KEY": "change-me-in-production-use-vault",
            "JWT_SECRET_KEY": "jwt-secret-change-in-production",
        }

        missing: list[str] = []
        for name, value in required:
            if not value or value == defaults.get(name):
                missing.append(name)

        if missing:
            import sys

            logger.critical(
                "production_secrets_check_failed",
                missing=missing,
                message="Application will exit: set strong secrets via .env or environment",
            )
            sys.exit(1)

        logger.info("production_secrets_check_passed")


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

_secrets_settings: SecretsSettings | None = None


def get_secrets_settings() -> SecretsSettings:
    """Return the global SecretsSettings singleton."""
    global _secrets_settings
    if _secrets_settings is None:
        _secrets_settings = SecretsSettings()
    return _secrets_settings


def set_secret_backend(backend: SecretBackend) -> None:
    """Inject a custom secret backend (call before ``fail_fast``)."""
    settings = get_secrets_settings()
    settings.set_backend(backend)


# ---------------------------------------------------------------------------
# Redactor — never leak secrets in logs / traces
# ---------------------------------------------------------------------------

# Common secret key names that must be redacted
_SECRET_KEYS = {
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "ENCRYPTION_KEY",
    "OANDA_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "SLACK_WEBHOOK_URL",
    "password",
    "api_key",
    "api_secret",
    "access_token",
    "refresh_token",
    "secret",
    "token",
}


def redact_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *payload* with secret values replaced by ``"***"``."""
    redacted: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(k, str) and (k.upper() in _SECRET_KEYS or k.lower() in _SECRET_KEYS):
            redacted[k] = "***"
        elif isinstance(v, dict):
            redacted[k] = redact_secrets(v)
        elif isinstance(v, str) and len(v) > 20 and any(c in v for c in (":", "/")):
            # Heuristic: if it looks like a token or URL with embedded secret, mask it
            redacted[k] = "***"
        else:
            redacted[k] = v
    return redacted
