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
    failed_login_attempts: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """User update schema."""
    full_name: str | None = Field(None, max_length=255)
    email: EmailStr | None = None


class UserUpdateAdmin(BaseModel):
    """Admin user update schema."""
    full_name: str | None = Field(None, max_length=255)
    email: EmailStr | None = None
    role: str | None = None
    is_active: bool | None = None


class UserListResponse(BaseModel):
    """User list response."""
    users: list[UserResponse]
    total: int


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128)
