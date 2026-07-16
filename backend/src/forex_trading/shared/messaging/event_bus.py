"""Event bus interfaces for the trading system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class EventHandler(ABC):
    """Interface for domain event handlers."""

    @abstractmethod
    async def handle(self, event: dict[str, Any]) -> None:
        pass


class EventBus(ABC):
    """Interface for the domain event bus.

    Implementations:
      - KafkaEventBus (production)
      - InMemoryEventBus (tests only, kept from shared/events.py)
    """

    @abstractmethod
    async def publish(
        self,
        topic: str,
        key: str,
        value: dict[str, Any],
    ) -> None:
        """Publish a single event."""
        pass

    @abstractmethod
    async def publish_batch(
        self,
        topic: str,
        messages: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """Publish a batch of (key, value) pairs to the same topic."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Release all resources."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the bus is operational."""
        pass
