"""Base domain entities following DDD patterns."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from forex_trading.core.domain.events import DomainEvent


class ValueObject(ABC):
    """Base class for value objects - immutable and defined by their attributes."""

    @abstractmethod
    def __eq__(self, other: object) -> bool:
        pass

    @abstractmethod
    def __hash__(self) -> int:
        pass

    def _get_equality_components(self) -> tuple[Any, ...]:
        """Override to define equality criteria."""
        raise NotImplementedError


class BaseEntity(ABC):
    """Base class for all domain entities."""

    def __init__(self, id: UUID | None = None) -> None:
        self._id = id or uuid4()
        self._created_at = datetime.utcnow()
        self._updated_at = datetime.utcnow()

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def _mark_updated(self) -> None:
        self._updated_at = datetime.utcnow()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseEntity):
            return False
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)


class AggregateRoot(BaseEntity):
    """Base class for aggregate roots - entities that enforce invariants."""

    def __init__(self, id: UUID | None = None) -> None:
        super().__init__(id)
        self._domain_events: list[DomainEvent] = []

    @property
    def domain_events(self) -> list[DomainEvent]:
        return self._domain_events.copy()

    def add_event(self, event: DomainEvent) -> None:
        """Add a domain event to be published."""
        self._domain_events.append(event)

    def clear_events(self) -> list[DomainEvent]:
        """Clear and return all pending domain events."""
        events = self._domain_events.copy()
        self._domain_events.clear()
        return events

    def _apply_event(self, event: DomainEvent) -> None:
        """Apply a domain event to the aggregate state."""
        self._mark_updated()
