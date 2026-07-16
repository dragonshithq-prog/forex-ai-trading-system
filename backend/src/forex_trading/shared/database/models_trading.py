"""Order, Position, and Deal models."""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forex_trading.shared.database.base import BaseModel


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    NEW = "new"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TimeInForce(str, enum.Enum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    DAY = "day"


class PositionSide(str, enum.Enum):
    LONG = "long"
    SHORT = "short"


class PositionStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    PARTIALLY_CLOSED = "partially_closed"


class Order(BaseModel):
    """Order model."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("idx_orders_symbol_status", "symbol", "status"),
        Index("idx_orders_broker_account_created", "broker_account_id", "created_at"),
    )

    broker_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("broker_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    signal_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("ai_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    strategy_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
    )

    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    time_in_force: Mapped[TimeInForce] = mapped_column(
        Enum(TimeInForce), default=TimeInForce.GTC, nullable=False
    )

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False, index=True
    )
    filled_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    filled_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    commission: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    slippage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    broker_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    broker_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    strategy = relationship("Strategy", back_populates="orders")
    broker_account = relationship("BrokerAccount", back_populates="orders")
    deal = relationship("Deal", back_populates="order", uselist=False, lazy="selectin")


class Position(BaseModel):
    """Position model."""

    __tablename__ = "positions"
    __table_args__ = (
        Index("idx_positions_symbol_status", "symbol", "status"),
        Index("idx_positions_broker_account_status", "broker_account_id", "status"),
    )

    broker_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("broker_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
    )

    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[PositionSide] = mapped_column(Enum(PositionSide), nullable=False)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trailing_stop: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    status: Mapped[PositionStatus] = mapped_column(
        Enum(PositionStatus), default=PositionStatus.OPEN, nullable=False, index=True
    )
    broker_position_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    commission: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    swap: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    strategy = relationship("Strategy", back_populates="positions")
    broker_account = relationship("BrokerAccount", back_populates="positions")
    deals = relationship("Deal", back_populates="position", lazy="selectin")


class Deal(BaseModel):
    """Deal model."""

    __tablename__ = "deals"

    order_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("positions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    commission: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    slippage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    broker_deal_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    order = relationship("Order", back_populates="deal")
    position = relationship("Position", back_populates="deals")


class EventOutbox(BaseModel):
    """Transactional outbox for reliable event publication.

    Every domain event that must be published to Kafka is first written to this
    table in the same DB transaction as the aggregate write. A background worker
    polls this table and publishes to Kafka, deleting rows only after Kafka acks.
    """

    __tablename__ = "event_outbox"
    __table_args__ = (
        Index("idx_outbox_status_created", "status", "created_at"),
        Index("idx_outbox_event_type", "event_type"),
    )

    class OutboxStatus(str, enum.Enum):
        PENDING = "pending"
        PUBLISHING = "publishing"
        PUBLISHED = "published"
        FAILED = "failed"
        DEAD_LETTER = "dead_letter"

    aggregate_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid, nullable=True, index=True,
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )
    event_version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSON, nullable=False,
    )
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus), default=OutboxStatus.PENDING, nullable=False, index=True,
    )
    publish_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    trace_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
    )


class EventOutboxDeadLetter(BaseModel):
    """Dead-letter queue for events that failed permanently."""

    __tablename__ = "event_outbox_dead_letter"

    original_outbox_id: Mapped[UUID] = mapped_column(
        Uuid, nullable=False,
    )
    aggregate_id: Mapped[Optional[UUID]] = mapped_column(Uuid, nullable=True)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
