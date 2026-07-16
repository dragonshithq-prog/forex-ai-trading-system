"""Application configuration management using Pydantic Settings.

Uses production-hardened defaults:
  - Secrets are validated (fail-fast in production via SecretsSettings)
  - JWT access tokens expire in 5 minutes (not 15)
  - JWT refresh tokens expire in 24 hours (not 7 days)
  - Logging of loaded config (without secrets) on startup
  - Range validation for all numeric parameters
"""

from __future__ import annotations

from functools import lru_cache
from enum import Enum
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import structlog

from forex_trading.shared.security.secrets import get_secrets_settings, SecretsSettings

logger = structlog.get_logger()


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Forex AI Trading System"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = Field(default=8000, ge=1, le=65535)
    WORKERS: int = Field(default=4, ge=1, le=64)
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]
    MAX_REQUEST_SIZE_BYTES: int = Field(default=1_048_576, ge=1024, le=104_857_600)

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./forex_trading.db"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = Field(default=20, ge=1, le=200)
    DATABASE_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100)
    DATABASE_POOL_TIMEOUT: int = Field(default=30, ge=1, le=300)
    DATABASE_POOL_RECYCLE: int = Field(default=3600, ge=60, le=86400)
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_QUERY_TIMEOUT: int = Field(default=30, ge=1, le=300)
    DATABASE_STATEMENT_CACHE_SIZE: int = Field(default=500, ge=0, le=10000)

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = Field(default=50, ge=1, le=500)
    REDIS_SOCKET_KEEPALIVE: int = Field(default=60, ge=0, le=600)
    REDIS_SOCKET_TIMEOUT: int = Field(default=10, ge=1, le=120)
    REDIS_RETRY_ON_TIMEOUT: bool = True
    REDIS_HEALTH_CHECK_INTERVAL: int = Field(default=30, ge=5, le=300)
    REDIS_PRELOAD_CONNECTIONS: int = Field(default=5, ge=0, le=50)

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_EXCHANGE: str = "forex_trading"

    # JWT Authentication — hardened defaults
    # Actual values sourced from SecretsSettings for production validation
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=5, ge=1, le=60)
    JWT_REFRESH_TOKEN_EXPIRE_HOURS: int = Field(default=24, ge=1, le=168)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=1, ge=1, le=30)
    JWT_ISSUER: str = "forex-trading-bot"
    JWT_AUDIENCE_ACCESS: str = "forex-trading:access"
    JWT_AUDIENCE_REFRESH: str = "forex-trading:refresh"

    # Broker Configuration
    OANDA_API_KEY: Optional[str] = None
    OANDA_ACCOUNT_ID: Optional[str] = None
    OANDA_ENVIRONMENT: str = "practice"  # practice | live

    MT4_HOST: str = "localhost"
    MT4_PORT: int = Field(default=3000, ge=1, le=65535)

    MT5_HOST: str = "localhost"
    MT5_PORT: int = Field(default=3001, ge=1, le=65535)

    # Risk Management
    MAX_POSITION_SIZE_PCT: float = Field(default=2.0, ge=0.1, le=100.0)
    MAX_TOTAL_EXPOSURE_PCT: float = Field(default=20.0, ge=0.1, le=500.0)
    MAX_DRAWDOWN_DAILY_PCT: float = Field(default=3.0, ge=0.1, le=50.0)
    MAX_DRAWDOWN_WEEKLY_PCT: float = Field(default=5.0, ge=0.1, le=50.0)
    MAX_DRAWDOWN_MONTHLY_PCT: float = Field(default=10.0, ge=0.1, le=50.0)
    MAX_DRAWDOWN_TOTAL_PCT: float = Field(default=15.0, ge=0.1, le=100.0)
    MAX_POSITIONS: int = Field(default=10, ge=1, le=1000)
    RISK_PER_TRADE_PCT: float = Field(default=1.0, ge=0.01, le=100.0)

    # AI Configuration
    AI_MIN_AGENTS: int = Field(default=4, ge=1, le=50)
    AI_MIN_AGREEMENT_THRESHOLD: float = Field(default=0.60, ge=0.0, le=1.0)
    AI_MAX_CONFLICT_THRESHOLD: float = Field(default=0.30, ge=0.0, le=1.0)
    AI_MODEL_PATH: str = "./ml/artifacts"
    AI_AGENT_TIMEOUT_SECONDS: float = Field(default=10.0, ge=0.1, le=300.0)
    AI_CIRCUIT_BREAKER_THRESHOLD: int = Field(default=3, ge=1, le=100)
    AI_CIRCUIT_BREAKER_RESET_SECONDS: int = Field(default=300, ge=10, le=86400)
    AI_MAX_CONCURRENT_ANALYSES: int = Field(default=5, ge=1, le=100)
    AI_AGENT_CACHE_TTL_SECONDS: int = Field(default=60, ge=0, le=3600)

    # Market Data
    MARKET_DATA_HISTORY_DAYS: int = Field(default=365, ge=1, le=3650)
    TIMEFRAMES: list[str] = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"]

    # Monitoring
    PROMETHEUS_ENABLED: bool = True
    PROMETHEUS_PORT: int = Field(default=9090, ge=1024, le=65535)
    JAEGER_ENDPOINT: str = "http://localhost:14268/api/traces"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json | console

    # Notifications
    SLACK_WEBHOOK_URL: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    EMAIL_SMTP_HOST: Optional[str] = None
    EMAIL_SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    EMAIL_FROM: Optional[str] = None

    # Compliance & Auditing Configuration
    COMPLIANCE_RETENTION_TRADES_DAYS: int = Field(default=2555, ge=1, le=36500)
    COMPLIANCE_RETENTION_DECISIONS_DAYS: int = Field(default=1825, ge=1, le=36500)
    COMPLIANCE_RETENTION_AUDIT_LOGS_DAYS: int = Field(default=2555, ge=1, le=36500)
    COMPLIANCE_RETENTION_NOTIFICATIONS_DAYS: int = Field(default=365, ge=1, le=36500)
    COMPLIANCE_RETENTION_SESSIONS_DAYS: int = Field(default=90, ge=1, le=3650)
    COMPLIANCE_RETENTION_PI_DATA_DAYS: int = Field(default=730, ge=1, le=36500)
    COMPLIANCE_RETENTION_CONSENT_DAYS: int = Field(default=2555, ge=1, le=36500)
    COMPLIANCE_ARCHIVE_ENABLED: bool = True
    COMPLIANCE_ARCHIVE_DIRECTORY: str = "~/.forex_trading/archives"
    COMPLIANCE_AUDIT_CHAIN_WITNESS_BACKEND: str = ""       # "s3" or "" (disabled)
    COMPLIANCE_AUDIT_WITNESS_S3_BUCKET: str = "forex-trading-audit-chain"
    COMPLIANCE_AUDIT_WITNESS_S3_PREFIX: str = "audit-chain/"
    COMPLIANCE_DEFAULT_JURISDICTION: str = "global"
    COMPLIANCE_DISCLOSURE_VERSION: str = "1.0.0"

    # Request size limits by content type
    MAX_JSON_PAYLOAD_BYTES: int = Field(default=512_000, ge=1024, le=104_857_600)
    MAX_FILE_UPLOAD_BYTES: int = Field(default=10_485_760, ge=1024, le=1_073_741_824)

    # ── Field Validators ────────────────────────────────────────────────────────

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of: {allowed}")
        return v.upper()

    @field_validator("LOG_FORMAT")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        allowed = {"json", "console", "plain"}
        if v.lower() not in allowed:
            raise ValueError(f"LOG_FORMAT must be one of: {allowed}")
        return v.lower()

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def validate_jwt_algorithm(cls, v: str) -> str:
        allowed = {"HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
        if v.upper() not in allowed:
            raise ValueError(f"JWT_ALGORITHM must be one of: {allowed}")
        return v.upper()

    @field_validator("OANDA_ENVIRONMENT")
    @classmethod
    def validate_oanda_env(cls, v: str) -> str:
        allowed = {"practice", "live"}
        if v.lower() not in allowed:
            raise ValueError(f"OANDA_ENVIRONMENT must be one of: {allowed}")
        return v.lower()

    @field_validator("COMPLIANCE_DEFAULT_JURISDICTION")
    @classmethod
    def validate_jurisdiction(cls, v: str) -> str:
        allowed = {"global", "eu", "uk", "us", "sg", "hk", "au", "jp", "ch"}
        if v.lower() not in allowed:
            raise ValueError(f"COMPLIANCE_DEFAULT_JURISDICTION must be one of: {allowed}")
        return v.lower()

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT == Environment.TESTING

    @property
    def jwt_secret_key(self) -> str:
        """Resolve the JWT secret from SecretsSettings (never the default)."""
        return get_secrets_settings().JWT_SECRET_KEY

    @property
    def secret_key(self) -> str:
        """Resolve the app secret key from SecretsSettings."""
        return get_secrets_settings().SECRET_KEY

    def get_safe_dict(self) -> dict:
        """Return config with secrets masked for logging."""
        d = self.model_dump()
        secrets_keys = {
            "DATABASE_URL", "REDIS_URL", "RABBITMQ_URL",
            "OANDA_API_KEY", "SLACK_WEBHOOK_URL",
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
            "EMAIL_SMTP_HOST", "EMAIL_FROM",
            "JWT_ALGORITHM", "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
            "JWT_REFRESH_TOKEN_EXPIRE_HOURS",
            "MT4_HOST", "MT4_PORT", "MT5_HOST", "MT5_PORT",
        }
        for key in d:
            if key not in secrets_keys and "secret" in key.lower() or "key" in key.lower() or "token" in key.lower() or "password" in key.lower():
                d[key] = "***masked***"
        # Always mask the URL fields
        if "DATABASE_URL" in d and d["DATABASE_URL"]:
            d["DATABASE_URL"] = d["DATABASE_URL"].split("@")[-1] if "@" in d["DATABASE_URL"] else "***set***"
        if "REDIS_URL" in d and d["REDIS_URL"]:
            d["REDIS_URL"] = "redis://***masked***@..." if "@" in d["REDIS_URL"] else "***set***"
        if "RABBITMQ_URL" in d and d["RABBITMQ_URL"]:
            d["RABBITMQ_URL"] = "amqp://***masked***@..."
        return d


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    settings = Settings()
    safe_config = settings.get_safe_dict()
    logger.info(
        "configuration_loaded",
        environment=settings.ENVIRONMENT.value,
        app_name=settings.APP_NAME,
        api_prefix=settings.API_PREFIX,
        log_level=settings.LOG_LEVEL,
        database_pool_size=settings.DATABASE_POOL_SIZE,
        redis_max_connections=settings.REDIS_MAX_CONNECTIONS,
        ai_min_agents=settings.AI_MIN_AGENTS,
        compliance_retention_days=settings.COMPLIANCE_RETENTION_TRADES_DAYS,
        config=safe_config,
    )
    return settings


def validate_production_settings() -> None:
    """Fail-fast in production: check that all required secrets are set.

    Call this at application startup **after** calling ``get_settings()``.
    """
    secrets = get_secrets_settings()
    secrets.fail_fast()
