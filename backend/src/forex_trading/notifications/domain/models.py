"""Notification domain models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class NotificationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class NotificationMessage:
    title: str
    body: str
    priority: NotificationPriority
    category: str  # "trade_executed" | "risk_alert" | "signal" | "system"
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
