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
    PasswordResetRequest,
    PasswordResetConfirm,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from forex_trading.api.schemas.user import UserResponse
from forex_trading.config import get_settings
from forex_trading.core.security import security_manager, token_revocation_service
from forex_trading.shared.database.crud_user import (
    user_repository,
    user_session_repository,
    password_reset_repository,
)
from forex_trading.shared.database.models_user import User

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Authentication"])

_BACKUP_CODE_COUNT = 8
_BACKUP_CODE_LENGTH = 10


def _generate_backup_codes() -> list[str]:
    return [secrets.token_hex(_BACKUP_CODE_LENGTH // 2) for _ in range(_BACKUP_CODE_COUNT)]


@router.post(
    "/register",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account and return JWT token pair",
    operation_id="register_user",
    responses={
        201: {"description": "User registered successfully"},
        409: {"description": "Email or username already registered"},
    },
)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
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

    return LoginResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login",
    description="Authenticate with username/email and password, returns JWT token pair",
    operation_id="login",
)
async def login(
    request: LoginRequest,
    request_obj: Request,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    user: User | None = None
    if "@" in request.username:
        user = await user_repository.get_by_email(db, email=request.username)
    else:
        user = await user_repository.get_by_username(db, username=request.username)

    if user is None or not security_manager.verify_password(request.password, user.hashed_password):
        if user:
            await user_repository.record_failed_login(db, user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if await user_repository.is_account_locked(user):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account locked due to too many failed attempts. Try again later.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    if user.mfa_enabled:
        if not request.mfa_token:
            raise HTTPException(
                status_code=status.HTTP_449_RETRY_WITH,
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


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Exchange a valid refresh token for a new JWT token pair",
    operation_id="refresh_token",
)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # Validate with audience check — only refresh tokens pass
    payload = await security_manager.decode_token_with_revocation_check(
        request.refresh_token,
        expected_audience=settings.JWT_AUDIENCE_REFRESH,
    )
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

    # Revoke the old refresh token
    if payload.jti:
        await token_revocation_service.revoke(
            payload.jti,
            expire_at=payload.exp,
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


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout",
    description="Revoke all active sessions and invalidate current token",
    operation_id="logout",
)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    revoked = await user_session_repository.revoke_all_user_sessions(
        db, user_id=current_user.id
    )

    # Also revoke the current access token's JTI if available
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # Decode to extract JTI and revoke it
        payload = security_manager.decode_token(token)
        if payload and payload.jti:
            await token_revocation_service.revoke(payload.jti)

    return {"message": "Successfully logged out", "sessions_revoked": revoked}


@router.post(
    "/mfa/setup",
    response_model=MFASetupResponse,
    summary="Setup MFA",
    description="Generate MFA secret and backup codes for two-factor authentication",
    operation_id="setup_mfa",
)
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


@router.post(
    "/mfa/verify",
    status_code=status.HTTP_200_OK,
    summary="Verify MFA",
    description="Verify an MFA code and enable two-factor authentication",
    operation_id="verify_mfa",
)
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


@router.post(
    "/password/change",
    status_code=status.HTTP_200_OK,
    summary="Change password",
    description="Change the current user's password (requires current password)",
    operation_id="change_password",
)
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

    await user_session_repository.revoke_all_user_sessions(db, user_id=current_user.id)

    return {"message": "Password changed successfully"}


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_200_OK,
    summary="Request password reset",
    description="Request a password reset token via email",
    operation_id="request_password_reset",
)
async def request_password_reset(
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await user_repository.get_by_email(db, email=request.email)
    if not user:
        return {"message": "If an account with that email exists, a reset link has been sent"}

    reset_token = await password_reset_repository.create_token(db, user_id=user.id)

    return {
        "message": "If an account with that email exists, a reset link has been sent",
        "reset_token": reset_token.token,
    }


@router.post(
    "/password-reset/reset",
    status_code=status.HTTP_200_OK,
    summary="Reset password",
    description="Reset password using a valid reset token",
    operation_id="reset_password",
)
async def reset_password(
    request: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
) -> dict:
    reset_token = await password_reset_repository.get_by_token(db, token=request.token)
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    new_hash = security_manager.hash_password(request.new_password)
    user = await user_repository.get(db, reset_token.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.hashed_password = new_hash
    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    await db.commit()

    await password_reset_repository.mark_used(db, token_id=reset_token.id)
    await user_session_repository.revoke_all_user_sessions(db, user_id=user.id)

    return {"message": "Password reset successfully"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Retrieve the authenticated user's profile",
    operation_id="get_current_user",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)
