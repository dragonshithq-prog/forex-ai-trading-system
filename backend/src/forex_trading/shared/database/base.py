"""SQLAlchemy base model and mixins."""

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import DateTime, JSON, String, Uuid, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    registry,
)


class Base(DeclarativeBase):
    """Base class for all database models."""

    type_annotation_map = {
        PyUUID: Uuid,
        dict: JSON,
    }


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Mixin for UUID primary key."""

    id: Mapped[PyUUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin for soft delete functionality."""

    is_deleted: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class BaseModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Abstract base model with UUID PK and timestamps."""

    __abstract__ = True

    def to_dict(self) -> dict[str, Any]:
        """Convert model instance to dictionary."""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"
