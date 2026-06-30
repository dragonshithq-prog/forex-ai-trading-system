"""Application configuration management using Pydantic Settings."""

from functools import lru_cache
from enum import Enum
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    SECRET_KEY: str = "change-me-in-production-use-vault"
    API_PREFIX: str = "/api/v1"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./forex_trading.db"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_EXCHANGE: str = "forex_trading"

    # JWT Authentication
    JWT_SECRET_KEY: str = "jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Broker Configuration
    OANDA_API_KEY: Optional[str] = None
    OANDA_ACCOUNT_ID: Optional[str] = None
    OANDA_ENVIRONMENT: str = "practice"  # practice | live

    MT4_HOST: str = "localhost"
    MT4_PORT: int = 3000

    MT5_HOST: str = "localhost"
    MT5_PORT: int = 3001

    # Risk Management
    MAX_POSITION_SIZE_PCT: float = 2.0
    MAX_TOTAL_EXPOSURE_PCT: float = 20.0
    MAX_DRAWDOWN_DAILY_PCT: float = 3.0
    MAX_DRAWDOWN_WEEKLY_PCT: float = 5.0
    MAX_DRAWDOWN_MONTHLY_PCT: float = 10.0
    MAX_DRAWDOWN_TOTAL_PCT: float = 15.0
    MAX_POSITIONS: int = 10
    RISK_PER_TRADE_PCT: float = 1.0

    # AI Configuration
    AI_MIN_AGENTS: int = 4
    AI_MIN_AGREEMENT_THRESHOLD: float = 0.60
    AI_MAX_CONFLICT_THRESHOLD: float = 0.30
    AI_MODEL_PATH: str = "./ml/artifacts"

    # Market Data
    MARKET_DATA_HISTORY_DAYS: int = 365
    TIMEFRAMES: list[str] = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"]

    # Monitoring
    PROMETHEUS_ENABLED: bool = True
    PROMETHEUS_PORT: int = 9090
    JAEGER_ENDPOINT: str = "http://localhost:14268/api/traces"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json | console

    # Notifications
    SLACK_WEBHOOK_URL: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    EMAIL_SMTP_HOST: Optional[str] = None
    EMAIL_SMTP_PORT: int = 587
    EMAIL_FROM: Optional[str] = None

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT == Environment.TESTING


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
