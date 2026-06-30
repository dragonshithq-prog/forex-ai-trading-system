"""Notification channel base class."""

from abc import ABC, abstractmethod

from forex_trading.notifications.domain.models import NotificationMessage


class BaseNotificationChannel(ABC):
    """Abstract base for all notification channels."""

    @abstractmethod
    async def send(self, message: NotificationMessage) -> bool:
        """Send a notification message. Returns True on success."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Unique channel identifier."""
