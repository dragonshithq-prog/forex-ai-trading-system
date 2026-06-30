"""Common Pydantic schemas."""

from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field
from uuid import UUID

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination parameters."""
    skip: int = Field(0, ge=0, description="Number of records to skip")
    limit: int = Field(100, ge=1, le=1000, description="Maximum records to return")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""
    items: list[T]
    total: int
    skip: int
    limit: int
    has_more: bool


class ErrorResponse(BaseModel):
    """Error response."""
    error: dict[str, Any]


class SuccessResponse(BaseModel):
    """Success response."""
    message: str
    data: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    environment: str | None = None
