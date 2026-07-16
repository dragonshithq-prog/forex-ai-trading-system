"""Database models package - import all models for Alembic discovery."""

from forex_trading.shared.database.base import Base, BaseModel

# Import all models to ensure they're registered with SQLAlchemy
from forex_trading.shared.database.models_user import (
    User,
    UserSession,
    AuditLog,
    UserRole,
)
from forex_trading.shared.database.models_broker import (
    BrokerAccount,
    BrokerConnection,
    BrokerType,
    ConnectionStatus,
)
from forex_trading.shared.database.models_trading import (
    Order,
    Position,
    Deal,
    EventOutbox,
    EventOutboxDeadLetter,
    OrderSide,
    OrderType,
    OrderStatus,
    PositionSide,
    PositionStatus,
)
from forex_trading.shared.database.models_strategy import (
    Strategy,
    AIDecision,
    AgentPerformance,
    StrategyType,
    StrategyStatus,
    AgentType,
    SignalDirection,
)
from forex_trading.shared.database.models_risk import (
    RiskConfiguration,
    RiskState,
    RiskAlert,
    RiskOverride,
    RiskLevel,
    OverrideAction,
)
from forex_trading.shared.database.models_market import (
    Tick,
    Candle,
    MarketStructure,
    SymbolInfo,
)
from forex_trading.shared.database.models_notification import (
    Notification,
    NotificationPreference,
    NotificationChannel,
    NotificationPriority,
)
from forex_trading.shared.database.models_compliance import (
    ConsentRecord,
    ConsentType,
    ConsentStatus,
    PIIInventory,
    PIICategory,
    DataRetentionPurge,
    DataRetentionCategory,
    PurgeStatus,
    AuditLogChain,
    RegulatoryReport,
    RiskDisclosure,
    ArchiveManifest,
    DataClassificationRule,
    ClassificationLevel,
)

__all__ = [
    # Base
    "Base",
    "BaseModel",
    # User
    "User",
    "UserSession",
    "AuditLog",
    "UserRole",
    # Broker
    "BrokerAccount",
    "BrokerConnection",
    "BrokerType",
    "ConnectionStatus",
    # Trading
    "Order",
    "Position",
    "Deal",
    "EventOutbox",
    "EventOutboxDeadLetter",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "PositionSide",
    "PositionStatus",
    # Strategy
    "Strategy",
    "AIDecision",
    "AgentPerformance",
    "StrategyType",
    "StrategyStatus",
    "AgentType",
    "SignalDirection",
    # Risk
    "RiskConfiguration",
    "RiskState",
    "RiskAlert",
    "RiskOverride",
    "RiskLevel",
    "OverrideAction",
    # Market
    "Tick",
    "Candle",
    "MarketStructure",
    "SymbolInfo",
    # Notifications
    "Notification",
    "NotificationPreference",
    "NotificationChannel",
    "NotificationPriority",
    # Compliance
    "ConsentRecord",
    "ConsentType",
    "ConsentStatus",
    "PIIInventory",
    "PIICategory",
    "DataRetentionPurge",
    "DataRetentionCategory",
    "PurgeStatus",
    "AuditLogChain",
    "RegulatoryReport",
    "RiskDisclosure",
    "ArchiveManifest",
    "DataClassificationRule",
    "ClassificationLevel",
]
