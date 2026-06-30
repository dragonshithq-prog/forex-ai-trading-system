"""Trading API endpoints (Orders, Positions)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_current_user, get_db
from forex_trading.api.schemas.trading import (
    ClosePositionRequest,
    DealResponse,
    OrderCreate,
    OrderFullResponse,
    OrderModify,
    OrderResponse,
    PlaceOrderRequest,
    PositionFullResponse,
    PositionResponse,
    UpdateStopLossRequest,
    UpdateTakeProfitRequest,
)
from forex_trading.shared.database.crud_broker import broker_account_repository
from forex_trading.shared.database.crud_trading import (
    deal_repository,
    order_repository,
    position_repository,
)
from forex_trading.shared.database.models_user import User

router = APIRouter(prefix="/trading", tags=["Trading"])

_CANCELLABLE_STATUSES = {"pending", "new"}
_MODIFIABLE_STATUSES = {"pending", "new"}
_CLOSEABLE_STATUSES = {"open"}


def _to_order_response(order) -> OrderResponse:
    return OrderResponse(
        order_id=str(order.id),
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        status=order.status,
        filled_price=order.filled_price,
        created_at=order.created_at,
    )


def _to_position_response(position) -> PositionResponse:
    return PositionResponse(
        position_id=str(position.id),
        symbol=position.symbol,
        side=position.side,
        size=position.size,
        entry_price=position.entry_price,
        current_price=position.current_price,
        unrealized_pnl=position.unrealized_pnl,
        stop_loss=position.stop_loss,
        take_profit=position.take_profit,
        opened_at=position.opened_at,
    )


async def _verify_order_ownership(db: AsyncSession, order, current_user: User) -> None:
    account = await broker_account_repository.get(db, order.broker_account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _verify_position_ownership(db: AsyncSession, position, current_user: User) -> None:
    account = await broker_account_repository.get(db, position.broker_account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(
    order_data: PlaceOrderRequest,
    broker_account_id: UUID = Query(..., description="Broker account to place order on"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    # Rate limit: consider adding slowapi here in production
    account = await broker_account_repository.get(db, broker_account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker account not found")
    if account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if order_data.order_type in {"limit", "stop", "stop_limit"} and order_data.price is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Price required for order_type={order_data.order_type}",
        )

    if order_data.side not in {"buy", "sell"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Side must be 'buy' or 'sell'",
        )

    order = await order_repository.create(
        db,
        obj_in={
            "broker_account_id": broker_account_id,
            "symbol": order_data.symbol.upper(),
            "side": order_data.side,
            "order_type": order_data.order_type,
            "quantity": order_data.quantity,
            "price": order_data.price,
            "stop_price": None,
            "take_profit": order_data.take_profit,
            "stop_loss": order_data.stop_loss,
            "time_in_force": "gtc",
            "status": "pending",
        },
    )

    return _to_order_response(order)


@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(
    broker_account_id: UUID | None = None,
    symbol: str | None = None,
    order_status: str | None = Query(None, alias="status"),
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrderResponse]:
    if broker_account_id:
        account = await broker_account_repository.get(db, broker_account_id)
        if not account or account.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        orders = await order_repository.get_by_broker_account(
            db, broker_account_id=broker_account_id, status=order_status, limit=limit
        )
    elif symbol:
        orders = await order_repository.get_by_symbol(
            db, symbol=symbol.upper(), status=order_status
        )
    else:
        orders = await order_repository.get_multi(db, skip=skip, limit=limit)

    return [_to_order_response(o) for o in orders]


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    order = await order_repository.get(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    await _verify_order_ownership(db, order, current_user)
    return _to_order_response(order)


@router.delete("/orders/{order_id}", status_code=status.HTTP_200_OK)
async def cancel_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await order_repository.get(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    await _verify_order_ownership(db, order, current_user)

    if order.status not in _CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel order with status '{order.status}'",
        )

    await order_repository.update_status(db, order_id=order_id, status="cancelled")
    return {"message": "Order cancelled", "order_id": str(order_id)}


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

@router.get("/positions", response_model=list[PositionResponse])
async def list_positions(
    broker_account_id: UUID | None = None,
    symbol: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PositionResponse]:
    if broker_account_id:
        account = await broker_account_repository.get(db, broker_account_id)
        if not account or account.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        positions = await position_repository.get_open_positions(
            db, broker_account_id=broker_account_id
        )
    elif symbol:
        positions = await position_repository.get_by_symbol(
            db, symbol=symbol.upper(), status="open"
        )
    else:
        positions = await position_repository.get_open_positions(db)

    return [_to_position_response(p) for p in positions]


@router.get("/positions/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PositionResponse:
    position = await position_repository.get(db, position_id)
    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")

    await _verify_position_ownership(db, position, current_user)
    return _to_position_response(position)


@router.post("/positions/{position_id}/close", status_code=status.HTTP_200_OK)
async def close_position(
    position_id: UUID,
    request: ClosePositionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    position = await position_repository.get(db, position_id)
    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")

    await _verify_position_ownership(db, position, current_user)

    if position.status not in _CLOSEABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot close position with status '{position.status}'",
        )

    if request.partial_pct == 100.0:
        await position_repository.update(
            db, db_obj=position, obj_in={"status": "closed"}
        )
        closed_size = position.size
    else:
        closed_size = position.size * (request.partial_pct / 100.0)
        remaining_size = position.size - closed_size
        await position_repository.update(
            db, db_obj=position, obj_in={"size": remaining_size}
        )

    return {
        "message": "Position close initiated",
        "position_id": str(position_id),
        "closed_size": closed_size,
        "partial_pct": request.partial_pct,
        "reason": request.reason,
    }


@router.put("/positions/{position_id}/stop-loss", status_code=status.HTTP_200_OK)
async def update_stop_loss(
    position_id: UUID,
    request: UpdateStopLossRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    position = await position_repository.get(db, position_id)
    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")

    await _verify_position_ownership(db, position, current_user)

    if position.status not in _CLOSEABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot modify position with status '{position.status}'",
        )

    await position_repository.update(
        db, db_obj=position, obj_in={"stop_loss": request.stop_loss}
    )
    return {"message": "Stop loss updated", "position_id": str(position_id), "stop_loss": request.stop_loss}


@router.put("/positions/{position_id}/take-profit", status_code=status.HTTP_200_OK)
async def update_take_profit(
    position_id: UUID,
    request: UpdateTakeProfitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    position = await position_repository.get(db, position_id)
    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")

    await _verify_position_ownership(db, position, current_user)

    if position.status not in _CLOSEABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot modify position with status '{position.status}'",
        )

    await position_repository.update(
        db, db_obj=position, obj_in={"take_profit": request.take_profit}
    )
    return {
        "message": "Take profit updated",
        "position_id": str(position_id),
        "take_profit": request.take_profit,
    }


# ---------------------------------------------------------------------------
# Trade history
# ---------------------------------------------------------------------------

@router.get("/history", response_model=list[DealResponse])
async def trade_history(
    broker_account_id: UUID | None = None,
    symbol: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DealResponse]:
    if broker_account_id:
        account = await broker_account_repository.get(db, broker_account_id)
        if not account or account.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deals = await deal_repository.get_multi(db, skip=skip, limit=limit)
    return [DealResponse.model_validate(d) for d in deals]


# ---------------------------------------------------------------------------
# Legacy endpoints kept for backward compatibility
# ---------------------------------------------------------------------------

@router.put("/orders/{order_id}", response_model=OrderFullResponse)
async def modify_order(
    order_id: UUID,
    modify_data: OrderModify,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderFullResponse:
    order = await order_repository.get(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    await _verify_order_ownership(db, order, current_user)

    if order.status not in _MODIFIABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot modify order with status '{order.status}'",
        )

    update_dict = modify_data.model_dump(exclude_unset=True)
    updated_order = await order_repository.update(db, db_obj=order, obj_in=update_dict)
    return OrderFullResponse.model_validate(updated_order)


@router.get("/deals", response_model=list[DealResponse])
async def list_deals(
    broker_account_id: UUID | None = None,
    order_id: UUID | None = None,
    position_id: UUID | None = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DealResponse]:
    if order_id:
        deals = await deal_repository.get_by_order(db, order_id=order_id)
    elif position_id:
        deals = await deal_repository.get_by_position(db, position_id=position_id)
    else:
        deals = await deal_repository.get_multi(db, skip=skip, limit=limit)

    return [DealResponse.model_validate(d) for d in deals]
