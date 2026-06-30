"""Market Data API endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.api.dependencies import get_current_user, get_db
from forex_trading.api.schemas.market import (
    CandleResponse,
    CurrencyStrengthResponse,
    EconomicEventResponse,
    MarketStructureLegacyResponse,
    MarketStructureResponse,
    PairInfoResponse,
    SessionInfoResponse,
    SessionResponse,
    SymbolResponse,
    TickLegacyResponse,
    TickResponse,
)
from forex_trading.market_data.services.demo_data import generate_demo_candles, generate_demo_tick
from forex_trading.market_data.services.session_detector import (
    SESSION_TIMES,
    SessionDetector,
    TradingSession,
)
from forex_trading.shared.database.models_user import User

router = APIRouter(prefix="/market", tags=["Market Data"])

_SUPPORTED_TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"}

_PAIR_SESSION_AFFINITY: dict[str, list[str]] = {
    "AUDUSD": ["sydney", "tokyo"],
    "NZDUSD": ["sydney", "tokyo"],
    "AUDJPY": ["sydney", "tokyo"],
    "USDJPY": ["tokyo", "new_york"],
    "EURJPY": ["tokyo", "london"],
    "GBPJPY": ["tokyo", "london"],
    "EURUSD": ["london", "new_york"],
    "GBPUSD": ["london", "new_york"],
    "EURGBP": ["london"],
    "USDCHF": ["london", "new_york"],
    "USDCAD": ["new_york"],
    "EURCHF": ["london"],
    "EURAUD": ["sydney", "london"],
    "GBPAUD": ["sydney", "london"],
}

_SUPPORTED_PAIRS: list[dict] = [
    {"symbol": sym, "base": sym[:3], "quote": sym[3:], "pip_size": 0.0001 if sym[-3:] != "JPY" else 0.01}
    for sym in _PAIR_SESSION_AFFINITY
]


@router.get("/candles/{symbol}", response_model=list[CandleResponse])
async def get_candles(
    symbol: str,
    timeframe: str = Query("H1", description="M1, M5, M15, M30, H1, H4, D1, W1"),
    count: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
) -> list[CandleResponse]:
    if timeframe not in _SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported timeframe '{timeframe}'. Must be one of: {sorted(_SUPPORTED_TIMEFRAMES)}",
        )
    # In production: query TimescaleDB / cache
    candles = generate_demo_candles(symbol, timeframe, count)
    return [CandleResponse(**c) for c in candles]


@router.get("/tick/{symbol}", response_model=TickResponse)
async def get_tick(
    symbol: str,
    current_user: User = Depends(get_current_user),
) -> TickResponse:
    # In production: get from Redis latest-tick cache
    tick = generate_demo_tick(symbol)
    return TickResponse(**tick)


@router.get("/session", response_model=SessionResponse)
async def get_current_session(
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    detector = SessionDetector()
    session = detector.get_current_session()

    minutes_to_next: int | None = None
    if session.time_to_next_session is not None:
        minutes_to_next = int(session.time_to_next_session.total_seconds() // 60)

    return SessionResponse(
        active_session=session.active_session.value,
        sessions_active=[s.value for s in session.sessions_active],
        is_overlap=session.is_overlap,
        session_strength=session.session_strength,
        time_to_next_session_minutes=minutes_to_next,
    )


@router.get("/structure/{symbol}", response_model=MarketStructureResponse)
async def get_market_structure(
    symbol: str,
    timeframe: str = Query("H1", description="Timeframe for analysis"),
    current_user: User = Depends(get_current_user),
) -> MarketStructureResponse:
    if timeframe not in _SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported timeframe '{timeframe}'",
        )
    # In production: run ICT/SMC structure analyzer
    return MarketStructureResponse(
        symbol=symbol.upper(),
        timeframe=timeframe,
        trend_direction="neutral",
        support_levels=[],
        resistance_levels=[],
        order_blocks=[],
        fair_value_gaps=[],
    )


@router.get("/strength", response_model=list[CurrencyStrengthResponse])
async def get_currency_strength(
    current_user: User = Depends(get_current_user),
) -> list[CurrencyStrengthResponse]:
    # In production: aggregate bid/ask changes across all major pairs and rank
    currencies = ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"]
    now = datetime.now(timezone.utc)
    return [
        CurrencyStrengthResponse(
            currency=ccy,
            strength_score=0.0,
            rank=i + 1,
            pairs_analyzed=0,
            timestamp=now,
        )
        for i, ccy in enumerate(currencies)
    ]


@router.get("/symbols", response_model=list[SymbolResponse])
async def list_symbols(
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SymbolResponse]:
    from forex_trading.shared.database.models_market import SymbolInfo
    from sqlalchemy import select

    query = select(SymbolInfo)
    if active_only:
        query = query.where(SymbolInfo.is_active == True)  # noqa: E712

    result = await db.execute(query)
    symbols = result.scalars().all()
    return [SymbolResponse.model_validate(s) for s in symbols]


@router.get("/calendar", response_model=list[EconomicEventResponse])
async def get_economic_calendar(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    currency: str | None = None,
    impact: str | None = Query(None, description="low, medium, high"),
    current_user: User = Depends(get_current_user),
) -> list[EconomicEventResponse]:
    # In production: fetch from ForexFactory / Investing.com cache in Redis/DB
    return []


@router.get("/pairs", response_model=list[PairInfoResponse])
async def list_pairs(
    session: str | None = Query(None, description="Filter by session: sydney, tokyo, london, new_york"),
    current_user: User = Depends(get_current_user),
) -> list[PairInfoResponse]:
    pairs = [
        PairInfoResponse(
            symbol=p["symbol"],
            base_currency=p["base"],
            quote_currency=p["quote"],
            session_affinity=_PAIR_SESSION_AFFINITY.get(p["symbol"], []),
            typical_spread=None,
            pip_size=p["pip_size"],
        )
        for p in _SUPPORTED_PAIRS
    ]
    if session:
        pairs = [p for p in pairs if session.lower() in p.session_affinity]
    return pairs


# ---------------------------------------------------------------------------
# Legacy endpoints kept for backward compatibility
# ---------------------------------------------------------------------------

@router.get("/symbols/{symbol}", response_model=SymbolResponse)
async def get_symbol(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SymbolResponse:
    from forex_trading.shared.database.models_market import SymbolInfo
    from sqlalchemy import select

    result = await db.execute(
        select(SymbolInfo).where(SymbolInfo.symbol == symbol.upper())
    )
    symbol_info = result.scalar_one_or_none()
    if not symbol_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Symbol {symbol} not found")
    return SymbolResponse.model_validate(symbol_info)


@router.get("/symbols/{symbol}/candles", response_model=list[CandleResponse])
async def get_symbol_candles(
    symbol: str,
    timeframe: str = Query("H1"),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
) -> list[CandleResponse]:
    candles = generate_demo_candles(symbol, timeframe, limit)
    return [CandleResponse(**c) for c in candles]


@router.get("/symbols/{symbol}/ticks", response_model=list[TickLegacyResponse])
async def get_ticks(
    symbol: str,
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
) -> list[TickLegacyResponse]:
    return []


@router.get("/symbols/{symbol}/structure", response_model=MarketStructureLegacyResponse)
async def get_symbol_market_structure(
    symbol: str,
    timeframe: str = Query("H1"),
    current_user: User = Depends(get_current_user),
) -> MarketStructureLegacyResponse:
    return MarketStructureLegacyResponse(
        symbol=symbol.upper(),
        timeframe=timeframe,
        structure_type="ranging",
        break_type="none",
        trend_direction="neutral",
        strength=0.5,
        order_blocks=[],
        fair_value_gaps=[],
        liquidity_zones=[],
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/prices/{symbol}")
async def get_current_price(
    symbol: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    tick = generate_demo_tick(symbol)
    return tick
