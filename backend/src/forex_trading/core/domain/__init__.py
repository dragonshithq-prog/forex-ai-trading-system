"""Core domain layer - base entities, value objects, and domain events."""

from forex_trading.core.domain.entities import (
    BaseEntity,
    AggregateRoot,
    ValueObject,
)
from forex_trading.core.domain.events import (
    DomainEvent,
    EventBus,
    EventHandler,
)
from forex_trading.core.domain.value_objects import (
    Money,
    Symbol,
    Timestamp,
    UniqueId,
)

__all__ = [
    "BaseEntity",
    "AggregateRoot",
    "ValueObject",
    "DomainEvent",
    "EventBus",
    "EventHandler",
    "Money",
    "Symbol",
    "Timestamp",
    "UniqueId",
]
