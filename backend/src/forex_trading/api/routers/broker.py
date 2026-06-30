"""Broker Account API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_db, get_current_user
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

router = APIRouter(prefix="/broker", tags=["Broker"])


@router.get("/accounts", response_model=list[BrokerAccountResponse])
async def list_broker_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BrokerAccountResponse]:
    """List broker accounts for current user."""
    accounts = await broker_account_repository.get_by_user(
        db, user_id=current_user.id
    )
    return [BrokerAccountResponse.model_validate(a) for a in accounts]


@router.post("/accounts", response_model=BrokerAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_broker_account(
    account_data: BrokerAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerAccountResponse:
    """Create a new broker account."""
    # In production, encrypt credentials before storing
    account = await broker_account_repository.create(
        db,
        obj_in={
            "user_id": current_user.id,
            "broker_type": account_data.broker_type,
            "account_name": account_data.account_name,
            "account_number": account_data.account_number,
            "environment": account_data.environment,
            "balance": 0.0,
            "equity": 0.0,
            "margin": 0.0,
            "free_margin": 0.0,
        },
    )
    return BrokerAccountResponse.model_validate(account)


@router.get("/accounts/{account_id}", response_model=BrokerAccountResponse)
async def get_broker_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerAccountResponse:
    """Get broker account by ID."""
    account = await broker_account_repository.get(db, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broker account not found",
        )
    if account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return BrokerAccountResponse.model_validate(account)


@router.put("/accounts/{account_id}", response_model=BrokerAccountResponse)
async def update_broker_account(
    account_id: UUID,
    update_data: BrokerAccountUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerAccountResponse:
    """Update broker account."""
    account = await broker_account_repository.get(db, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broker account not found",
        )
    if account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    updated_account = await broker_account_repository.update(
        db, db_obj=account, obj_in=update_dict
    )
    return BrokerAccountResponse.model_validate(updated_account)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_broker_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft delete broker account."""
    account = await broker_account_repository.get(db, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broker account not found",
        )
    if account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    await broker_account_repository.soft_delete(db, id=account_id)


@router.get("/accounts/{account_id}/connections", response_model=list[BrokerConnectionResponse])
async def list_connections(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BrokerConnectionResponse]:
    """List connections for a broker account."""
    account = await broker_account_repository.get(db, account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    connections = await broker_connection_repository.get_by_account(db, account_id=account_id)
    return [BrokerConnectionResponse.model_validate(c) for c in connections]


@router.post("/accounts/{account_id}/sync")
async def sync_broker_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Sync account data from broker."""
    account = await broker_account_repository.get(db, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broker account not found",
        )
    if account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # In production, this would call the broker API
    return {"message": "Sync initiated", "account_id": str(account_id)}
