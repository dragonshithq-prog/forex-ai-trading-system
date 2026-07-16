"""Main API router - aggregates all endpoint routers."""

from fastapi import APIRouter

from forex_trading.api.routers import auth, users, broker, trading, strategy, risk, market, accounts, analytics, ws

api_router = APIRouter()

api_router.include_router(auth.router, tags=["Authentication"])
api_router.include_router(trading.router, tags=["Trading"])
api_router.include_router(market.router, tags=["Market Data"])
api_router.include_router(risk.router, tags=["Risk Management"])
api_router.include_router(strategy.router, tags=["Strategy"])
api_router.include_router(broker.router, tags=["Broker"])
api_router.include_router(accounts.router, tags=["Accounts"])
api_router.include_router(analytics.router, tags=["Analytics"])
api_router.include_router(users.router, tags=["Users"])
api_router.include_router(ws.router, tags=["WebSocket"])


@api_router.get(
    "/health",
    tags=["Health"],
    summary="API health check",
    description="Simple health check for the API",
    operation_id="api_health_check",
)
async def api_health() -> dict:
    return {"status": "healthy", "api": "v1"}


@api_router.get(
    "/system/info",
    tags=["System"],
    summary="System information",
    description="Get system information and service status",
    operation_id="system_info",
)
async def system_info() -> dict:
    return {
        "api_version": "v1",
        "environment": "development",
        "services": {
            "market_data": "operational",
            "ai_orchestrator": "operational",
            "strategy_engine": "operational",
            "risk_engine": "operational",
            "execution_engine": "operational",
        },
    }
