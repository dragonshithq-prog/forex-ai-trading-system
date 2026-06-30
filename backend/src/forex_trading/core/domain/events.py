"""Domain events and event bus for event-driven architecture."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import UUID, uuid4


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""

    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    aggregate_id: UUID | None = None
    event_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketTickEvent(DomainEvent):
    """Event emitted when a new market tick is received."""

    symbol: str = ""
    bid: float = 0.0
    ask: float = 0.0
    volume: float = 0.0
    event_type: str = "market.tick"


@dataclass(frozen=True)
class TradeSignalEvent(DomainEvent):
    """Event emitted when a trade signal is generated."""

    signal_id: UUID = field(default_factory=uuid4)
    strategy: str = ""
    symbol: str = ""
    direction: str = ""  # "long" | "short"
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    confidence: float = 0.0
    agents: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    event_type: str = "trading.signal.generated"


@dataclass(frozen=True)
class OrderEvent(DomainEvent):
    """Event emitted for order lifecycle changes."""

    order_id: UUID = field(default_factory=uuid4)
    broker_account_id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    side: str = ""  # "buy" | "sell"
    quantity: float = 0.0
    price: float = 0.0
    status: str = ""  # "new" | "filled" | "partial" | "cancelled" | "rejected"
    event_type: str = "order.new"


@dataclass(frozen=True)
class RiskAlertEvent(DomainEvent):
    """Event emitted for risk management alerts."""

    alert_id: UUID = field(default_factory=uuid4)
    level: str = ""  # "info" | "warning" | "critical"
    category: str = ""  # "drawdown" | "exposure" | "correlation" | "volatility"
    message: str = ""
    current_value: float = 0.0
    threshold_value: float = 0.0
    action_required: bool = False
    event_type: str = "risk.alert"


@dataclass(frozen=True)
class RiskOverrideEvent(DomainEvent):
    """Event emitted when risk engine overrides a decision."""

    override_id: UUID = field(default_factory=uuid4)
    target_order_id: UUID | None = None
    target_position_id: UUID | None = None
    action: str = ""  # "reject_order" | "close_position" | "reduce_size"
    reason: str = ""
    event_type: str = "risk.override"


class EventHandler(ABC):
    """Interface for domain event handlers."""

    @abstractmethod
    async def handle(self, event: DomainEvent) -> None:
        pass


class EventBus(ABC):
    """Interface for the domain event bus."""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        pass

    @abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        pass

    @abstractmethod
    def subscribe_function(self, event_type: str, handler: Callable) -> None:
        pass
