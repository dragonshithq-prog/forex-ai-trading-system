"""User API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_db, get_current_user, require_role
from forex_trading.api.schemas.user import (
    UserResponse,
    UserUpdate,
    UserUpdateAdmin,
    UserListResponse,
    AdminResetPasswordRequest,
)
from forex_trading.api.schemas.auth import PasswordChangeRequest
from forex_trading.core.security import security_manager
from forex_trading.shared.database.crud_user import user_repository, user_session_repository
from forex_trading.shared.database.models_user import User, UserRole
from forex_trading.shared.security.audit import audit_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/",
    response_model=UserListResponse,
    summary="List users",
    description="List all users (admin only)",
    operation_id="list_users",
)
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    users = await user_repository.get_multi(db, skip=skip, limit=limit)
    total = await user_repository.count(db)
    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=total,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get my profile",
    description="Get the authenticated user's profile",
    operation_id="get_my_profile",
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user",
    description="Get a user by ID (admin only)",
    operation_id="get_user",
)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await user_repository.get(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse.model_validate(user)


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update my profile",
    description="Update the authenticated user's profile",
    operation_id="update_my_profile",
)
async def update_current_user(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data to update",
        )
    updated_user = await user_repository.update(
        db,
        db_obj=current_user,
        obj_in=update_dict,
    )
    return UserResponse.model_validate(updated_user)


@router.get(
    "/admin/search",
    response_model=UserListResponse,
    summary="Search users",
    description="Search users by username or email (admin only)",
    operation_id="admin_search_users",
)
async def admin_search_users(
    q: str = "",
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    if not q:
        return await list_users(skip=skip, limit=limit, current_user=current_user, db=db)
    query = select(User).where(
        or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))
    ).offset(skip).limit(limit)
    result = await db.execute(query)
    users = list(result.scalars().all())
    count_q = await db.execute(
        select(func.count()).select_from(User).where(
            or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))
        )
    )
    total = count_q.scalar_one()
    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=total,
    )


@router.put(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Update user role",
    description="Update a user's role (admin only)",
    operation_id="admin_update_role",
)
async def admin_update_role(
    request: Request,
    user_id: UUID,
    role: str,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    try:
        new_role = UserRole(role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {[r.value for r in UserRole]}",
        )
    if current_user.role.value != "superadmin" and new_role == UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins can assign superadmin role",
        )
    updated = await user_repository.update_role(db, user_id=user_id, role=role)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Audit log
    ip_address = request.client.host if request.client else None
    await audit_service.record(
        db,
        user_id=current_user.id,
        action="user.role.update",
        resource_type="user",
        resource_id=str(user_id),
        details={"old_role": str(updated.role.value) if hasattr(updated, 'role') else None, "new_role": role},
        ip_address=ip_address,
    )

    return UserResponse.model_validate(updated)


@router.post(
    "/{user_id}/toggle-active",
    response_model=UserResponse,
    summary="Toggle user active status",
    description="Activate or deactivate a user account (admin only)",
    operation_id="admin_toggle_active",
)
async def admin_toggle_active(
    request: Request,
    user_id: UUID,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await user_repository.get(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current_user.id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself")
    updated = await user_repository.set_active_status(db, user_id=user_id, is_active=not user.is_active)

    # Audit log
    ip_address = request.client.host if request.client else None
    await audit_service.record(
        db,
        user_id=current_user.id,
        action="user.toggle_active",
        resource_type="user",
        resource_id=str(user_id),
        details={"is_active": updated.is_active},
        ip_address=ip_address,
    )

    return UserResponse.model_validate(updated)


@router.post(
    "/{user_id}/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset user password",
    description="Admin force-reset of a user's password (admin only)",
    operation_id="admin_reset_password",
)
async def admin_reset_password(
    request: Request,
    user_id: UUID,
    admin_reset_req: AdminResetPasswordRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await user_repository.get(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    new_hash = security_manager.hash_password(admin_reset_req.new_password)
    success = await user_repository.admin_reset_password(db, user_id=user_id, new_hashed_password=new_hash)
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset password")

    # Audit log
    ip_address = request.client.host if request.client else None
    await audit_service.record(
        db,
        user_id=current_user.id,
        action="user.password.reset",
        resource_type="user",
        resource_id=str(user_id),
        details={"reset_by_admin": True},
        ip_address=ip_address,
    )

    return {"message": "Password reset successfully"}


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Admin update user",
    description="Admin update of user profile fields (admin only)",
    operation_id="admin_update_user",
)
async def admin_update_user(
    user_id: UUID,
    update_data: UserUpdateAdmin,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await user_repository.get(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    update_dict = update_data.model_dump(exclude_unset=True, exclude_none=True)
    if not update_dict:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data to update")
    if "role" in update_dict:
        try:
            UserRole(update_dict["role"])
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    updated = await user_repository.update(db, db_obj=user, obj_in=update_dict)
    return UserResponse.model_validate(updated)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Soft delete a user account (superadmin only)",
    operation_id="delete_user",
)
async def delete_user(
    user_id: UUID,
    current_user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    success = await user_repository.soft_delete(db, id=user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
