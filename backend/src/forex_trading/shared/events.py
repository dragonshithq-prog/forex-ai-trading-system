"""In-memory event bus implementation."""

from collections import defaultdict
from typing import Any, Callable
import structlog

from forex_trading.core.domain.events import DomainEvent, EventBus, EventHandler

logger = structlog.get_logger()


class InMemoryEventBus(EventBus):
    """
    In-memory event bus for development and testing.

    For production, replace with RabbitMQ/Kafka implementation.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._function_handlers: dict[str, list[Callable]] = defaultdict(list)
        self._event_log: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribed handlers."""
        event_type = event.event_type or event.__class__.__name__

        logger.debug("event_published", event_type=event_type, event_id=str(event.event_id))

        self._event_log.append(event)

        # Call class-based handlers
        for handler in self._handlers.get(event_type, []):
            try:
                await handler.handle(event)
            except Exception as e:
                logger.error(
                    "event_handler_error",
                    event_type=event_type,
                    handler=handler.__class__.__name__,
                    error=str(e),
                )

        # Call function-based handlers
        for handler in self._function_handlers.get(event_type, []):
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    "event_function_handler_error",
                    event_type=event_type,
                    error=str(e),
                )

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        self._handlers[event_type].append(handler)
        logger.debug("event_subscribed", event_type=event_type, handler=handler.__class__.__name__)

    def subscribe_function(self, event_type: str, handler: Callable) -> None:
        """Subscribe a function to an event type."""
        self._function_handlers[event_type].append(handler)
        logger.debug("event_function_subscribed", event_type=event_type)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        if event_type in self._handlers:
            self._handlers[event_type] = [h for h in self._handlers[event_type] if h != handler]

    def get_event_log(self, limit: int = 100) -> list[DomainEvent]:
        """Get recent events."""
        return self._event_log[-limit:]

    def clear_log(self) -> None:
        """Clear event log."""
        self._event_log.clear()


# Global event bus instance
event_bus = InMemoryEventBus()
