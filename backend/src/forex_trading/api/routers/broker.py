"""Broker Account API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_db, get_current_user
from forex_trading.api.schemas.broker import (
    BrokerAccountCreate,
    BrokerAccountUpdate,
    BrokerAccountResponse,
    AccountInfoResponse,
    BrokerConnectionResponse,
)
from forex_trading.broker.gateway import broker_gateway, BrokerType as GatewayBrokerType
from forex_trading.broker.plugins import get_plugin as get_broker_plugin
from forex_trading.core.security import encrypt_credentials, decrypt_credentials
from forex_trading.shared.database.crud_broker import (
    broker_account_repository,
    broker_connection_repository,
)
from forex_trading.shared.database.models_broker import BrokerAccount
from forex_trading.shared.database.models_user import User
from forex_trading.shared.security.audit import audit_service

router = APIRouter(prefix="/broker", tags=["Broker"])


def _to_enum(broker_type: str) -> GatewayBrokerType:
    """Convert string to GatewayBrokerType enum."""
    mapping = {
        "mt4": GatewayBrokerType.MT4,
        "mt5": GatewayBrokerType.MT5,
        "oanda": GatewayBrokerType.OANDA,
        "fxcm": GatewayBrokerType.FXCM,
        "ctrader": GatewayBrokerType.CTRADER,
        "ibkr": GatewayBrokerType.IBKR,
    }
    return mapping.get(broker_type.lower(), GatewayBrokerType.OANDA)


@router.get(
    "/accounts",
    response_model=list[BrokerAccountResponse],
    summary="List broker accounts",
    description="List all broker accounts for the current user",
    operation_id="list_broker_accounts",
)
async def list_broker_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BrokerAccountResponse]:
    """List broker accounts for current user."""
    accounts = await broker_account_repository.get_by_user(
        db, user_id=current_user.id
    )
    resp = []
    for a in accounts:
        d = BrokerAccountResponse.model_validate(a)
        d.has_credentials = bool(a.credentials_encrypted)
        resp.append(d)
    return resp


@router.post(
    "/accounts",
    response_model=BrokerAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create broker account",
    description="Create a new broker account with encrypted credentials",
    operation_id="create_broker_account",
)
async def create_broker_account(
    request: Request,
    account_data: BrokerAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BrokerAccountResponse:
    """Create a new broker account with encrypted credentials."""
    creds = {}
    if account_data.api_key:
        creds["api_key"] = account_data.api_key
    if account_data.api_secret:
        creds["api_secret"] = account_data.api_secret
    if account_data.password:
        creds["password"] = account_data.password
    if account_data.host:
        creds["host"] = account_data.host
    if account_data.port:
        creds["port"] = account_data.port

    account = await broker_account_repository.create(
        db,
        obj_in={
            "user_id": current_user.id,
            "broker_type": account_data.broker_type,
            "account_name": account_data.account_name,
            "account_number": account_data.account_number,
            "environment": account_data.environment,
            "credentials_encrypted": encrypt_credentials(creds) if creds else None,
            "balance": 0.0,
            "equity": 0.0,
            "margin": 0.0,
            "free_margin": 0.0,
        },
    )
    resp = BrokerAccountResponse.model_validate(account)
    resp.has_credentials = bool(account.credentials_encrypted)

    # Audit log
    ip_address = request.client.host if request.client else None
    await audit_service.record(
        db,
        user_id=current_user.id,
        action="broker.account.create",
        resource_type="broker_account",
        resource_id=str(account.id),
        details={
            "broker_type": account_data.broker_type,
            "account_name": account_data.account_name,
            "environment": account_data.environment,
        },
        ip_address=ip_address,
    )

    return resp


@router.get(
    "/accounts/{account_id}",
    response_model=BrokerAccountResponse,
    summary="Get broker account",
    description="Get broker account details by ID",
    operation_id="get_broker_account",
)
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
    resp = BrokerAccountResponse.model_validate(account)
    resp.has_credentials = bool(account.credentials_encrypted)
    return resp


@router.put(
    "/accounts/{account_id}",
    response_model=BrokerAccountResponse,
    summary="Update broker account",
    description="Update broker account settings and credentials",
    operation_id="update_broker_account",
)
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

    if update_data.api_key or update_data.api_secret or update_data.password:
        creds = {}
        existing = account.credentials_encrypted
        if existing:
            try:
                creds = decrypt_credentials(existing)
            except Exception:
                creds = {}
        if update_data.api_key:
            creds["api_key"] = update_data.api_key
        if update_data.api_secret:
            creds["api_secret"] = update_data.api_secret
        if update_data.password:
            creds["password"] = update_data.password
        if update_data.host:
            creds["host"] = update_data.host
        if update_data.port:
            creds["port"] = update_data.port
        update_dict["credentials_encrypted"] = encrypt_credentials(creds)

    for field in ["api_key", "api_secret", "password", "host", "port"]:
        update_dict.pop(field, None)

    updated_account = await broker_account_repository.update(
        db, db_obj=account, obj_in=update_dict
    )
    resp = BrokerAccountResponse.model_validate(updated_account)
    resp.has_credentials = bool(updated_account.credentials_encrypted)
    return resp


@router.delete(
    "/accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete broker account",
    description="Soft delete a broker account",
    operation_id="delete_broker_account",
)
async def delete_broker_account(
    request: Request,
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

    # Audit log
    ip_address = request.client.host if request.client else None
    await audit_service.record(
        db,
        user_id=current_user.id,
        action="broker.account.delete",
        resource_type="broker_account",
        resource_id=str(account_id),
        details={"account_name": account.account_name, "broker_type": account.broker_type},
        ip_address=ip_address,
    )


@router.get(
    "/accounts/{account_id}/connections",
    response_model=list[BrokerConnectionResponse],
    summary="List broker connections",
    description="List connections for a broker account",
    operation_id="list_broker_connections",
)
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


@router.post(
    "/accounts/{account_id}/test",
    summary="Test broker connection",
    description="Test connectivity to a broker",
    operation_id="test_broker_connection",
)
async def test_broker_connection(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Test broker connection."""
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

    bt = account.broker_type.value if hasattr(account.broker_type, 'value') else account.broker_type
    plugin = get_broker_plugin(bt)
    if not plugin:
        return {"success": False, "message": f"No plugin available for {bt}"}

    try:
        creds = {}
        if account.credentials_encrypted:
            creds = decrypt_credentials(account.credentials_encrypted)
        result = await plugin.test_connection(creds)
        return {"success": result, "message": "Connection successful" if result else "Connection failed"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post(
    "/accounts/{account_id}/connect",
    summary="Connect to broker",
    description="Establish a live connection to a broker",
    operation_id="connect_broker",
)
async def connect_broker_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Connect to broker."""
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

    if not account.credentials_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No credentials configured for this account",
        )

    try:
        creds = decrypt_credentials(account.credentials_encrypted)
        bt = account.broker_type.value if hasattr(account.broker_type, 'value') else account.broker_type
        success = await broker_gateway.connect(
            connection_id=account_id,
            broker_type=_to_enum(bt),
            credentials=creds,
        )
        if success:
            await broker_account_repository.update(
                db, db_obj=account, obj_in={"credentials_encrypted": encrypt_credentials(creds)}
            )
        if success:
            return {"success": True, "connection_id": str(account_id)}
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Connection failed",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Connection failed: {str(e)}",
        )


@router.post(
    "/accounts/{account_id}/disconnect",
    summary="Disconnect from broker",
    description="Disconnect an active broker connection",
    operation_id="disconnect_broker",
)
async def disconnect_broker_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Disconnect from broker."""
    try:
        await broker_gateway.disconnect(connection_id=account_id)
        return {"success": True, "message": "Disconnected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Disconnect failed: {str(e)}",
        )


@router.get(
    "/connected",
    response_model=list[dict],
    summary="List connected brokers",
    description="List all currently connected broker connections",
    operation_id="list_connected_brokers",
)
async def list_connected_brokers(
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List currently connected brokers."""
    connected = broker_gateway.get_connected_brokers()
    return [{"connection_id": str(cid)} for cid in connected]


@router.post(
    "/accounts/{account_id}/sync",
    summary="Sync broker account",
    description="Sync account data (balance, equity, positions) from broker",
    operation_id="sync_broker_account",
)
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

    try:
        account_info = await broker_gateway.get_account_info(connection_id=account_id)
        if account_info:
            await broker_account_repository.update_balance(
                db,
                account_id=account_id,
                balance=account_info.balance,
                equity=account_info.equity,
                margin=account_info.margin,
                free_margin=account_info.free_margin,
                unrealized_pnl=account_info.unrealized_pnl,
            )
            return {"success": True, "message": "Sync completed"}
        return {"success": False, "message": "Could not get account info from broker"}
    except Exception as e:
        return {"success": False, "message": f"Sync failed: {str(e)}"}


@router.get(
    "/accounts/{account_id}/info",
    response_model=AccountInfoResponse,
    summary="Get account info",
    description="Get detailed account information from connected broker",
    operation_id="get_account_info",
)
async def get_account_info(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountInfoResponse:
    """Get detailed account info from connected broker."""
    account = await broker_account_repository.get_with_connections(db, id=account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return AccountInfoResponse(
        account_id=account.id,
        broker_type=account.broker_type.value if hasattr(account.broker_type, 'value') else account.broker_type,
        account_number=account.account_number,
        environment=account.environment,
        currency=account.currency,
        leverage=account.leverage,
        balance=account.balance,
        equity=account.equity,
        margin=account.margin,
        free_margin=account.free_margin,
        margin_level_pct=(account.equity / account.margin * 100) if account.margin and account.margin > 0 else None,
        unrealized_pnl=account.unrealized_pnl,
        open_positions=len(account.positions) if hasattr(account, 'positions') and account.positions else 0,
        last_sync=account.last_sync,
    )
