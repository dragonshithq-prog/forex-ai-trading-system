"""Authentication API endpoints."""

import secrets
from uuid import UUID

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_current_user, get_db
from forex_trading.api.schemas.auth import (
    LoginResponse,
    LoginRequest,
    MFASetupResponse,
    MFAVerifyRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from forex_trading.api.schemas.user import UserResponse
from forex_trading.core.security import security_manager
from forex_trading.shared.database.crud_user import user_repository, user_session_repository
from forex_trading.shared.database.models_user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])

_BACKUP_CODE_COUNT = 8
_BACKUP_CODE_LENGTH = 10


def _generate_backup_codes() -> list[str]:
    return [secrets.token_hex(_BACKUP_CODE_LENGTH // 2) for _ in range(_BACKUP_CODE_COUNT)]


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    existing_email = await user_repository.get_by_email(db, email=request.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    existing_username = await user_repository.get_by_username(db, username=request.username)
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    hashed_password = security_manager.hash_password(request.password)
    user = await user_repository.create(
        db,
        obj_in={
            "email": request.email,
            "username": request.username,
            "hashed_password": hashed_password,
            "full_name": request.full_name,
            "role": "viewer",
            "is_active": True,
            "is_verified": False,
        },
    )

    token_pair = security_manager.create_token_pair(
        user_id=str(user.id),
        role=user.role.value,
    )

    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    # Support login by username or email (username field may contain email)
    user: User | None = None
    if "@" in request.username:
        user = await user_repository.get_by_email(db, email=request.username)
    else:
        user = await user_repository.get_by_username(db, username=request.username)

    if user is None or not security_manager.verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    if user.mfa_enabled:
        if not request.mfa_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MFA token required",
            )
        if not user.mfa_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="MFA configuration error",
            )
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(request.mfa_token, valid_window=1):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA token",
            )

    await user_repository.update_last_login(db, user_id=user.id)

    token_pair = security_manager.create_token_pair(
        user_id=str(user.id),
        role=user.role.value,
    )

    return LoginResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    payload = security_manager.decode_token(request.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = await user_repository.get(db, UUID(payload.sub))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    token_pair = security_manager.create_token_pair(
        user_id=str(user.id),
        role=user.role.value,
    )

    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    revoked = await user_session_repository.revoke_all_user_sessions(
        db, user_id=current_user.id
    )
    return {"message": "Successfully logged out", "sessions_revoked": revoked}


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFASetupResponse:
    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA already enabled",
        )

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    qr_url = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="Forex Trading Bot",
    )
    backup_codes = _generate_backup_codes()

    await user_repository.update(
        db,
        db_obj=current_user,
        obj_in={"mfa_secret": secret},
    )

    return MFASetupResponse(
        secret=secret,
        qr_code_url=qr_url,
        backup_codes=backup_codes,
    )


@router.post("/mfa/verify", status_code=status.HTTP_200_OK)
async def verify_mfa(
    request: MFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA not set up. Call /auth/mfa/setup first.",
        )

    totp = pyotp.TOTP(current_user.mfa_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code",
        )

    await user_repository.update(
        db,
        db_obj=current_user,
        obj_in={"mfa_enabled": True},
    )

    return {"message": "MFA enabled successfully"}


@router.post("/password/change", status_code=status.HTTP_200_OK)
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not security_manager.verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if request.current_password == request.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from current password",
        )

    new_hash = security_manager.hash_password(request.new_password)
    await user_repository.update(
        db,
        db_obj=current_user,
        obj_in={"hashed_password": new_hash},
    )

    # Revoke all sessions to force re-login
    await user_session_repository.revoke_all_user_sessions(db, user_id=current_user.id)

    return {"message": "Password changed successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)
