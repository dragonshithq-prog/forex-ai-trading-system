"""User Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID


class UserResponse(BaseModel):
    """User response schema."""
    id: UUID
    email: str
    username: str
    full_name: str | None
    role: str
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    last_login: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """User update schema."""
    full_name: str | None = Field(None, max_length=255)
    email: EmailStr | None = None


class UserListResponse(BaseModel):
    """User list response."""
    users: list[UserResponse]
    total: int
