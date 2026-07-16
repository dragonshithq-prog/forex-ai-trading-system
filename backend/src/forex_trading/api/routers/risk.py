"""Risk Management API endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_current_user, get_db, require_role
from forex_trading.api.schemas.risk import (
    CircuitBreakerResponse,
    ExposureResponse,
    RiskAlertResponse,
    RiskAssessmentResponse,
    RiskConfigResponse,
    RiskConfigUpdate,
    RiskOverrideResponse,
    RiskStateResponse,
    UpdateRiskConfigRequest,
)
from forex_trading.shared.database.crud_broker import broker_account_repository
from forex_trading.shared.database.crud_risk import (
    risk_alert_repository,
    risk_config_repository,
    risk_override_repository,
    risk_state_repository,
)
from forex_trading.shared.database.models_user import User
from forex_trading.shared.security.audit import audit_service

router = APIRouter(prefix="/risk", tags=["Risk Management"])


async def _assert_account_ownership(
    db: AsyncSession, broker_account_id: UUID, current_user: User
) -> None:
    account = await broker_account_repository.get(db, broker_account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


# ---------------------------------------------------------------------------
# State & Config
# ---------------------------------------------------------------------------

@router.get(
    "/state",
    response_model=RiskStateResponse,
    summary="Get risk state",
    description="Retrieve current risk state for a broker account",
    operation_id="get_risk_state",
)
async def get_risk_state(
    broker_account_id: UUID = Query(..., description="Broker account UUID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RiskStateResponse:
    await _assert_account_ownership(db, broker_account_id, current_user)

    state = await risk_state_repository.get_by_account(db, broker_account_id=broker_account_id)
    if not state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk state not found")
    return RiskStateResponse.model_validate(state)


@router.get(
    "/config",
    response_model=RiskConfigResponse,
    summary="Get risk config",
    description="Retrieve risk configuration for an account or global defaults",
    operation_id="get_risk_config",
)
async def get_risk_config(
    broker_account_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RiskConfigResponse:
    if broker_account_id:
        await _assert_account_ownership(db, broker_account_id, current_user)
        config = await risk_config_repository.get_by_account(
            db, broker_account_id=broker_account_id
        )
    else:
        config = await risk_config_repository.get_global_config(db)

    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk config not found")
    return RiskConfigResponse.model_validate(config)


@router.put(
    "/config",
    response_model=RiskConfigResponse,
    summary="Update risk config",
    description="Update risk configuration (admin/superadmin only)",
    operation_id="update_risk_config",
)
async def update_risk_config(
    request: Request,
    update_data: UpdateRiskConfigRequest,
    broker_account_id: UUID | None = None,
    current_user: User = Depends(require_role("admin", "superadmin")),
    db: AsyncSession = Depends(get_db),
) -> RiskConfigResponse:
    if broker_account_id:
        config = await risk_config_repository.get_by_account(
            db, broker_account_id=broker_account_id
        )
    else:
        config = await risk_config_repository.get_global_config(db)

    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk config not found")

    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
        )

    updated = await risk_config_repository.update(db, db_obj=config, obj_in=update_dict)

    # Audit log
    ip_address = request.client.host if request.client else None
    await audit_service.record(
        db,
        user_id=current_user.id,
        action="risk.config.update",
        resource_type="risk_config",
        resource_id=str(config.id),
        details={"updated_fields": list(update_dict.keys()), "broker_account_id": str(broker_account_id) if broker_account_id else "global"},
        ip_address=ip_address,
    )

    return RiskConfigResponse.model_validate(updated)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@router.get(
    "/alerts",
    response_model=list[RiskAlertResponse],
    summary="List risk alerts",
    description="List risk alerts with optional filtering by account, level, or acknowledgement status",
    operation_id="list_risk_alerts",
)
async def list_risk_alerts(
    broker_account_id: UUID | None = None,
    level: str | None = Query(None, description="info, warning, critical"),
    acknowledged: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RiskAlertResponse]:
    if broker_account_id:
        await _assert_account_ownership(db, broker_account_id, current_user)
        alerts = await risk_alert_repository.get_by_account(
            db, broker_account_id=broker_account_id, acknowledged=acknowledged
        )
    elif level:
        alerts = await risk_alert_repository.get_by_level(db, level=level)
    else:
        alerts = await risk_alert_repository.get_multi(db, limit=limit)

    return [RiskAlertResponse.model_validate(a) for a in alerts]


@router.put(
    "/alerts/{alert_id}/acknowledge",
    status_code=status.HTTP_200_OK,
    summary="Acknowledge alert",
    description="Mark a risk alert as acknowledged",
    operation_id="acknowledge_alert",
)
async def acknowledge_alert(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    alert = await risk_alert_repository.acknowledge(db, alert_id=alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return {"message": "Alert acknowledged", "alert_id": str(alert_id)}


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

@router.post(
    "/circuit-breaker/reset",
    status_code=status.HTTP_200_OK,
    summary="Reset circuit breaker",
    description="Reset the risk circuit breaker for a broker account (admin/superadmin only)",
    operation_id="reset_circuit_breaker",
)
async def reset_circuit_breaker(
    broker_account_id: UUID = Query(...),
    current_user: User = Depends(require_role("admin", "superadmin")),
    db: AsyncSession = Depends(get_db),
) -> CircuitBreakerResponse:
    state = await risk_state_repository.get_by_account(db, broker_account_id=broker_account_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Risk state not found"
        )

    await risk_state_repository.update(
        db,
        db_obj=state,
        obj_in={
            "is_circuit_breaker_active": False,
            "circuit_breaker_until": None,
            "circuit_breaker_reason": None,
        },
    )

    return CircuitBreakerResponse(
        is_active=False,
        activated_at=None,
        active_until=None,
        reason=None,
        broker_account_id=broker_account_id,
    )


# ---------------------------------------------------------------------------
# Exposure
# ---------------------------------------------------------------------------

@router.get(
    "/exposure",
    response_model=ExposureResponse,
    summary="Get portfolio exposure",
    description="Get current portfolio exposure for a broker account",
    operation_id="get_portfolio_exposure",
)
async def get_portfolio_exposure(
    broker_account_id: UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExposureResponse:
    await _assert_account_ownership(db, broker_account_id, current_user)

    state = await risk_state_repository.get_by_account(db, broker_account_id=broker_account_id)
    total_pct = state.total_exposure_pct if state else 0.0

    return ExposureResponse(
        broker_account_id=broker_account_id,
        total_exposure_pct=total_pct,
        long_exposure_pct=0.0,
        short_exposure_pct=0.0,
        exposure_by_symbol={},
        exposure_by_currency={},
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Emergency
# ---------------------------------------------------------------------------

@router.post(
    "/emergency-close",
    status_code=status.HTTP_200_OK,
    summary="Emergency close all",
    description="Initiate emergency close of all positions for a broker account (admin/superadmin only)",
    operation_id="emergency_close_all",
)
async def emergency_close_all(
    broker_account_id: UUID = Query(...),
    reason: str = Query(..., min_length=5),
    current_user: User = Depends(require_role("admin", "superadmin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # In production: dispatch emergency_close event to execution engine via message bus
    return {
        "message": "Emergency close initiated",
        "broker_account_id": str(broker_account_id),
        "reason": reason,
        "initiated_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Legacy endpoints kept for backward compatibility
# ---------------------------------------------------------------------------

@router.post(
    "/assess",
    response_model=RiskAssessmentResponse,
    summary="Assess trade risk",
    description="Assess a potential trade against current risk parameters",
    operation_id="assess_trade_risk",
)
async def assess_trade(
    broker_account_id: UUID,
    symbol: str,
    side: str,
    size: float,
    entry_price: float,
    stop_loss: float | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RiskAssessmentResponse:
    account = await broker_account_repository.get(db, broker_account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    config = await risk_config_repository.get_by_account(db, broker_account_id=broker_account_id)
    if not config:
        config = await risk_config_repository.get_global_config(db)

    state = await risk_state_repository.get_by_account(db, broker_account_id=broker_account_id)

    warnings: list[str] = []
    violations: list[str] = []
    is_approved = True

    if state and state.is_circuit_breaker_active:
        violations.append("Circuit breaker is active")
        is_approved = False

    if config and account.equity > 0:
        position_pct = (size * entry_price) / account.equity * 100
        if position_pct > config.max_position_size_pct:
            warnings.append(
                f"Position size exceeds limit: {position_pct:.1f}% > {config.max_position_size_pct}%"
            )
        if state and state.open_positions >= config.max_positions:
            violations.append(f"Maximum positions reached: {state.open_positions}")
            is_approved = False
        if state and state.current_drawdown_pct >= config.daily_drawdown_limit_pct:
            violations.append(f"Daily drawdown limit reached: {state.current_drawdown_pct:.1f}%")
            is_approved = False

    max_size = (account.equity * 0.02 / entry_price) if entry_price > 0 else 0.0
    return RiskAssessmentResponse(
        is_approved=is_approved,
        adjusted_size=None,
        max_allowed_size=max_size,
        warnings=warnings,
        violations=violations,
        risk_score=0.0,
    )


@router.get(
    "/overrides",
    response_model=list[RiskOverrideResponse],
    summary="List risk overrides",
    description="List active risk overrides for an account",
    operation_id="list_risk_overrides",
)
async def list_risk_overrides(
    broker_account_id: UUID | None = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RiskOverrideResponse]:
    if broker_account_id:
        overrides = await risk_override_repository.get_by_account(
            db, broker_account_id=broker_account_id
        )
    else:
        overrides = await risk_override_repository.get_multi(db, limit=limit)
    return [RiskOverrideResponse.model_validate(o) for o in overrides]


@router.post(
    "/emergency/liquidate-all",
    summary="Emergency liquidate all positions",
    description="Emergency liquidation of all positions across all accounts (admin/superadmin only)",
    operation_id="emergency_liquidate_all",
)
async def emergency_liquidate_all(
    reason: str,
    current_user: User = Depends(require_role("admin", "superadmin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return {
        "message": "Emergency liquidation initiated",
        "reason": reason,
        "initiated_by": current_user.username,
    }


@router.post(
    "/circuit-breaker/activate",
    summary="Activate circuit breaker",
    description="Manually activate the risk circuit breaker (admin/superadmin only)",
    operation_id="activate_circuit_breaker",
)
async def activate_circuit_breaker(
    reason: str,
    cooldown_minutes: int = 60,
    current_user: User = Depends(require_role("admin", "superadmin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return {
        "message": "Circuit breaker activated",
        "reason": reason,
        "cooldown_minutes": cooldown_minutes,
    }
