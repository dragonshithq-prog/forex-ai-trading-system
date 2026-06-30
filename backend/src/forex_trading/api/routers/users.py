"""User API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=UserListResponse)
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


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.get("/{user_id}", response_model=UserResponse)
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


@router.put("/me", response_model=UserResponse)
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


@router.get("/admin/search", response_model=UserListResponse)
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


@router.put("/{user_id}/role", response_model=UserResponse)
async def admin_update_role(
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
    return UserResponse.model_validate(updated)


@router.post("/{user_id}/toggle-active", response_model=UserResponse)
async def admin_toggle_active(
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
    return UserResponse.model_validate(updated)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_200_OK)
async def admin_reset_password(
    user_id: UUID,
    request: AdminResetPasswordRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await user_repository.get(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    new_hash = security_manager.hash_password(request.new_password)
    success = await user_repository.admin_reset_password(db, user_id=user_id, new_hashed_password=new_hash)
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset password")
    return {"message": "Password reset successfully"}


@router.put("/{user_id}", response_model=UserResponse)
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


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
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
