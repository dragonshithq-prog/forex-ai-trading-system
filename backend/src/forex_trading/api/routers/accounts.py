"""Broker Account API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_db, get_current_user, require_trader  # noqa: F401
from forex_trading.api.schemas.broker import (
    BrokerAccountCreate,
    BrokerAccountUpdate,
    BrokerAccountResponse,
    BrokerConnectionResponse,
)
from forex_trading.shared.database.crud_broker import (
    broker_account_repository,
    broker_connection_repository,
)
from forex_trading.shared.database.models_user import User

router = APIRouter(prefix="/accounts", tags=["Broker Accounts"])


@router.get("/", response_model=list[BrokerAccountResponse])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BrokerAccountResponse]:
    """List broker accounts for current user."""
    accounts = await broker_account_repository.get_by_user(
        db, user_id=current_user.id
    )
    return accounts


@router.post("/", response_model=BrokerAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    request: BrokerAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_trader),
) -> BrokerAccountResponse:
    """Create a new broker account."""
    account_data = {
        "user_id": current_user.id,
        "broker_type": request.broker_type,
        "account_name": request.account_name,
        "account_number": request.account_number,
        "environment": request.environment,
        "currency": "USD",
        "leverage": 100,
        "balance": 0.0,
        "equity": 0.0,
        "margin": 0.0,
        "free_margin": 0.0,
        "unrealized_pnl": 0.0,
    }

    account = await broker_account_repository.create(db, obj_in=account_data)
    return account


@router.get("/{account_id}", response_model=BrokerAccountResponse)
async def get_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BrokerAccountResponse:
    """Get broker account by ID."""
    account = await broker_account_repository.get(db, id=account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    # Check ownership
    if account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this account",
        )

    return account


@router.put("/{account_id}", response_model=BrokerAccountResponse)
async def update_account(
    account_id: UUID,
    request: BrokerAccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_trader),
) -> BrokerAccountResponse:
    """Update broker account."""
    account = await broker_account_repository.get(db, id=account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    if account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this account",
        )

    update_data = request.model_dump(exclude_unset=True)
    updated_account = await broker_account_repository.update(
        db, db_obj=account, obj_in=update_data
    )
    return updated_account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_trader),
) -> None:
    """Soft delete broker account."""
    account = await broker_account_repository.get(db, id=account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    if account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this account",
        )

    await broker_account_repository.soft_delete(db, id=account_id)


@router.get("/{account_id}/connections", response_model=list[BrokerConnectionResponse])
async def list_connections(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BrokerConnectionResponse]:
    """List connections for a broker account."""
    account = await broker_account_repository.get(db, id=account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    connections = await broker_connection_repository.get_by_account(
        db, account_id=account_id
    )
    return connections
