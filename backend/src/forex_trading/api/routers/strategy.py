"""Strategy and AI API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_db, get_current_user, require_role
from forex_trading.api.schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    AIDecisionResponse,
    AgentPerformanceResponse,
)
from forex_trading.shared.database.crud_strategy import (
    strategy_repository,
    ai_decision_repository,
    agent_performance_repository,
)
from forex_trading.shared.database.models_user import User

router = APIRouter(prefix="/strategy", tags=["Strategy & AI"])


# Strategy endpoints
@router.get(
    "/strategies",
    response_model=list[StrategyResponse],
    summary="List strategies",
    description="List strategies with optional filters by type or status",
    operation_id="list_strategies",
)
async def list_strategies(
    strategy_type: str | None = None,
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StrategyResponse]:
    """List strategies with optional filters."""
    if strategy_type:
        strategies = await strategy_repository.get_by_type(db, strategy_type=strategy_type)
    elif status_filter:
        strategies = await strategy_repository.get_multi(
            db, filters=[strategy_repository.model.status == status_filter]
        )
    else:
        strategies = await strategy_repository.get_active_strategies(db)

    return [StrategyResponse.model_validate(s) for s in strategies]


@router.post(
    "/strategies",
    response_model=StrategyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create strategy",
    description="Create a new strategy (admin only)",
    operation_id="create_strategy",
)
async def create_strategy(
    strategy_data: StrategyCreate,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    """Create a new strategy (admin only)."""
    # Check if name exists
    existing = await strategy_repository.get_by_name(db, name=strategy_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Strategy name already exists",
        )

    strategy = await strategy_repository.create(
        db,
        obj_in=strategy_data.model_dump(),
    )
    return StrategyResponse.model_validate(strategy)


@router.get(
    "/strategies/{strategy_id}",
    response_model=StrategyResponse,
    summary="Get strategy",
    description="Get a strategy by its ID",
    operation_id="get_strategy",
)
async def get_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    """Get strategy by ID."""
    strategy = await strategy_repository.get(db, strategy_id)
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    return StrategyResponse.model_validate(strategy)


@router.put(
    "/strategies/{strategy_id}",
    response_model=StrategyResponse,
    summary="Update strategy",
    description="Update an existing strategy (admin only)",
    operation_id="update_strategy",
)
async def update_strategy(
    strategy_id: UUID,
    update_data: StrategyUpdate,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> StrategyResponse:
    """Update strategy (admin only)."""
    strategy = await strategy_repository.get(db, strategy_id)
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    updated_strategy = await strategy_repository.update(
        db, db_obj=strategy, obj_in=update_dict
    )
    return StrategyResponse.model_validate(updated_strategy)


@router.delete(
    "/strategies/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete strategy",
    description="Soft delete a strategy (superadmin only)",
    operation_id="delete_strategy",
)
async def delete_strategy(
    strategy_id: UUID,
    current_user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft delete strategy (superadmin only)."""
    success = await strategy_repository.soft_delete(db, id=strategy_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )


# AI Decision endpoints
@router.get(
    "/decisions",
    response_model=list[AIDecisionResponse],
    summary="List AI decisions",
    description="List AI trading decisions with optional filters",
    operation_id="list_ai_decisions",
)
async def list_ai_decisions(
    symbol: str | None = None,
    rejected_only: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AIDecisionResponse]:
    """List AI decisions with optional filters."""
    if rejected_only:
        decisions = await ai_decision_repository.get_rejected_decisions(db, limit=limit)
    elif symbol:
        decisions = await ai_decision_repository.get_by_symbol(
            db, symbol=symbol, limit=limit
        )
    else:
        decisions = await ai_decision_repository.get_recent_decisions(db, limit=limit)

    return [AIDecisionResponse.model_validate(d) for d in decisions]


@router.get(
    "/decisions/{decision_id}",
    response_model=AIDecisionResponse,
    summary="Get AI decision",
    description="Get an AI decision by ID with explainability details",
    operation_id="get_ai_decision",
)
async def get_ai_decision(
    decision_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIDecisionResponse:
    """Get AI decision by ID (XAI detail)."""
    decision = await ai_decision_repository.get(db, decision_id)
    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI decision not found",
        )
    return AIDecisionResponse.model_validate(decision)


# Agent Performance endpoints
@router.get(
    "/agents",
    response_model=list[AgentPerformanceResponse],
    summary="List agent performance",
    description="List AI agent performance metrics with optional filtering",
    operation_id="list_agent_performance",
)
async def list_agent_performance(
    agent_type: str | None = None,
    symbol: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentPerformanceResponse]:
    """List agent performance metrics."""
    if agent_type:
        performance = await agent_performance_repository.get_by_agent_type(
            db, agent_type=agent_type, symbol=symbol
        )
    else:
        performance = await agent_performance_repository.get_multi(db)

    return [AgentPerformanceResponse.model_validate(p) for p in performance]
