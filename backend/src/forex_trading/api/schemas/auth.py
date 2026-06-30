"""Authentication Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from forex_trading.api.schemas.user import UserResponse


class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_token: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class MFASetupResponse(BaseModel):
    secret: str
    qr_code_url: str
    backup_codes: list[str]


class MFAVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(None, max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: str
    exp: datetime
    iat: datetime
    role: str = "viewer"
    permissions: list[str] = []
    mfa_verified: bool = False


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class MFAEnableResponse(BaseModel):
    secret: str
    qr_code_url: str


class LoginUsernameRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    mfa_code: str | None = Field(None, min_length=6, max_length=6)
