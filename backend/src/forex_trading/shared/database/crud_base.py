"""Base repository with generic CRUD operations."""

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from forex_trading.shared.database.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class CRUDBase(Generic[ModelType]):
    """
    Generic CRUD repository with basic operations.

    Provides Create, Read, Update, Delete operations for any model.
    """

    def __init__(self, model: type[ModelType]) -> None:
        self.model = model

    async def get(self, db: AsyncSession, id: UUID) -> ModelType | None:
        """Get a single record by ID."""
        result = await db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: list | None = None,
    ) -> list[ModelType]:
        """Get multiple records with pagination."""
        query = select(self.model)

        if filters:
            for filter_condition in filters:
                query = query.where(filter_condition)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def count(self, db: AsyncSession, filters: list | None = None) -> int:
        """Count records with optional filters."""
        query = select(func.count()).select_from(self.model)

        if filters:
            for filter_condition in filters:
                query = query.where(filter_condition)

        result = await db.execute(query)
        return result.scalar_one()

    async def create(self, db: AsyncSession, *, obj_in: dict[str, Any]) -> ModelType:
        """Create a new record."""
        db_obj = self.model(**obj_in)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: dict[str, Any],
    ) -> ModelType:
        """Update an existing record."""
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, *, id: UUID) -> bool:
        """Delete a record by ID."""
        obj = await self.get(db, id)
        if obj:
            await db.delete(obj)
            await db.commit()
            return True
        return False

    async def soft_delete(self, db: AsyncSession, *, id: UUID) -> bool:
        """Soft delete a record (set is_deleted=True)."""
        from datetime import datetime

        obj = await self.get(db, id)
        if obj and hasattr(obj, "is_deleted"):
            obj.is_deleted = True
            obj.deleted_at = datetime.utcnow()
            db.add(obj)
            await db.commit()
            return True
        return False

    async def exists(self, db: AsyncSession, *, id: UUID) -> bool:
        """Check if a record exists."""
        result = await db.execute(select(self.model.id).where(self.model.id == id))
        return result.scalar_one_or_none() is not None
