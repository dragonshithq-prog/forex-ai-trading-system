"""Market Data models (TimescaleDB hypertables)."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from forex_trading.shared.database.base import Base


class Tick(Base):
    """
    Tick data model - TimescaleDB hypertable.

    This is a high-frequency table optimized for time-series queries.
    """

    __tablename__ = "ticks"
    __table_args__ = (
        Index("idx_ticks_symbol_timestamp", "symbol", "timestamp"),
    )

    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    bid: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    ask: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    spread: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    volume: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class Candle(Base):
    """
    OHLCV Candle model - TimescaleDB hypertable.

    Stores aggregated candle data across multiple timeframes.
    """

    __tablename__ = "candles"
    __table_args__ = (
        Index("idx_candles_symbol_timeframe_timestamp", "symbol", "timeframe", "timestamp"),
    )

    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    open: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    high: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    low: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    close: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    volume: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    tick_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class MarketStructure(Base):
    """
    Market Structure analysis results - TimescaleDB hypertable.

    Stores periodic structure analysis for each symbol/timeframe.
    """

    __tablename__ = "market_structures"
    __table_args__ = (
        Index("idx_market_structures_symbol_timeframe", "symbol", "timeframe", "timestamp"),
    )

    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    structure_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    break_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    trend_direction: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    strength: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    order_blocks: Mapped[dict | None] = mapped_column(
        nullable=True,
    )
    fair_value_gaps: Mapped[dict | None] = mapped_column(
        nullable=True,
    )
    liquidity_zones: Mapped[dict | None] = mapped_column(
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class SymbolInfo(Base):
    """Symbol information and metadata."""

    __tablename__ = "symbol_info"

    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    base_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    quote_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    pip_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    pip_size: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    min_lot_size: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    max_lot_size: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    lot_step: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    typical_spread: Mapped[float] = mapped_column(
        Float,
        nullable=True,
    )
    trading_sessions: Mapped[dict | None] = mapped_column(
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )
