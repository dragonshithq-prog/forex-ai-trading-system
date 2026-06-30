"""Broker Account and Connection models."""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forex_trading.shared.database.base import BaseModel, SoftDeleteMixin


class BrokerType(str, enum.Enum):
    """Supported broker types."""
    MT4 = "mt4"
    MT5 = "mt5"
    OANDA = "oanda"
    FXCM = "fxcm"
    CTRADER = "ctrader"
    IBKR = "ibkr"


class ConnectionStatus(str, enum.Enum):
    """Broker connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class BrokerAccount(BaseModel, SoftDeleteMixin):
    """Broker account linked to a user."""

    __tablename__ = "broker_accounts"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    broker_type: Mapped[BrokerType] = mapped_column(
        Enum(BrokerType),
        nullable=False,
    )
    account_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    account_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    environment: Mapped[str] = mapped_column(
        String(50),
        default="practice",
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )
    leverage: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
    )

    credentials_encrypted: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    last_sync: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    equity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    margin: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    free_margin: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    extra_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Relationships
    user = relationship("User", back_populates="broker_accounts")
    connections = relationship("BrokerConnection", back_populates="account", lazy="selectin")
    orders = relationship("Order", back_populates="broker_account", lazy="selectin")
    positions = relationship("Position", back_populates="broker_account", lazy="selectin")


class BrokerConnection(BaseModel):
    """Active broker connection tracking."""

    __tablename__ = "broker_connections"

    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus),
        default=ConnectionStatus.DISCONNECTED,
        nullable=False,
    )
    connected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    connection_info: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Relationships
    account = relationship("BrokerAccount", back_populates="connections")
