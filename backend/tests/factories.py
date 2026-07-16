"""Test data factories for forex trading system models.

Provides factory functions and classes to create model instances
with sensible defaults for testing.  All factories use ``uuid4()``
for primary keys so instances are always unique.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from forex_trading.shared.database.models_trading import (
    Deal,
    EventOutbox,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    PositionStatus,
    TimeInForce,
)
from forex_trading.shared.database.models_risk import (
    RiskAlert,
    RiskLevel,
    RiskOverride,
    RiskState,
    OverrideAction,
)
from forex_trading.shared.database.models_strategy import (
    AIDecision,
    AgentType,
    SignalDirection,
)

_rng = random.Random(42)


def _dt(offset_minutes: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)


def fake_order(
    *,
    id: UUID | None = None,
    broker_account_id: UUID | None = None,
    symbol: str = "EURUSD",
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    quantity: float = 0.1,
    price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    status: OrderStatus = OrderStatus.PENDING,
    **overrides,
) -> Order:
    """Create an Order instance with sensible defaults."""
    order = Order(
        id=id or uuid4(),
        broker_account_id=broker_account_id or uuid4(),
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price or (1.1000 if side == OrderSide.BUY else 1.0900),
        stop_loss=stop_loss or (1.0900 if side == OrderSide.BUY else 1.1000),
        take_profit=take_profit or (1.1100 if side == OrderSide.BUY else 1.0800),
        time_in_force=TimeInForce.GTC,
        status=status,
        filled_quantity=0.0,
        commission=0.0,
        slippage=0.0,
    )
    for k, v in overrides.items():
        setattr(order, k, v)
    return order


def fake_position(
    *,
    id: UUID | None = None,
    broker_account_id: UUID | None = None,
    symbol: str = "EURUSD",
    side: PositionSide = PositionSide.LONG,
    size: float = 0.1,
    entry_price: float = 1.1000,
    current_price: float = 1.1020,
    status: PositionStatus = PositionStatus.OPEN,
    **overrides,
) -> Position:
    """Create a Position instance with sensible defaults."""
    pnl = (current_price - entry_price) * size * 100_000 if side == PositionSide.LONG else (entry_price - current_price) * size * 100_000
    pos = Position(
        id=id or uuid4(),
        broker_account_id=broker_account_id or uuid4(),
        symbol=symbol,
        side=side,
        size=size,
        entry_price=entry_price,
        current_price=current_price,
        unrealized_pnl=pnl,
        realized_pnl=0.0,
        stop_loss=entry_price * 0.99 if side == PositionSide.LONG else entry_price * 1.01,
        take_profit=entry_price * 1.01 if side == PositionSide.LONG else entry_price * 0.99,
        status=status,
        opened_at=_dt(60),
    )
    for k, v in overrides.items():
        setattr(pos, k, v)
    return pos


def fake_ai_decision(
    *,
    id: UUID | None = None,
    symbol: str = "EURUSD",
    direction: SignalDirection = SignalDirection.LONG,
    confidence: float = 0.75,
    agreement_ratio: float = 0.65,
    conflict_ratio: float = 0.15,
    **overrides,
) -> AIDecision:
    """Create an AIDecision instance with sensible defaults."""
    agents = ["market_structure", "trend_ai", "sentiment_ai", "liquidity_ai", "volatility_ai"]
    dec = AIDecision(
        id=id or uuid4(),
        symbol=symbol,
        timeframe="H1",
        direction=direction,
        confidence=confidence,
        agreement_ratio=agreement_ratio,
        conflict_ratio=conflict_ratio,
        agents_responding=len(agents),
        total_agents=len(agents),
        was_rejected=False,
        market_regime="ranging",
        agent_signals={
            aid: {
                "direction": direction.value,
                "confidence": round(_rng.uniform(0.5, 1.0), 3),
                "reasoning": f"{aid} analysis",
                "supporting_data": {},
            }
            for aid in agents
        },
        rationale=f"Consensus: {direction.value} at {confidence:.0%} confidence",
        was_executed=False,
        decision_time=_dt(5),
    )
    for k, v in overrides.items():
        setattr(dec, k, v)
    return dec


def fake_risk_state(
    *,
    id: UUID | None = None,
    broker_account_id: UUID | None = None,
    equity: float = 10_000.0,
    peak_equity: float = 10_000.0,
    drawdown_pct: float = 0.0,
    **overrides,
) -> RiskState:
    """Create a RiskState instance with sensible defaults."""
    state = RiskState(
        id=id or uuid4(),
        broker_account_id=broker_account_id or uuid4(),
        current_equity=equity,
        peak_equity=peak_equity,
        current_drawdown_pct=drawdown_pct,
        max_drawdown_pct=drawdown_pct,
        daily_pnl=0.0,
        weekly_pnl=0.0,
        monthly_pnl=0.0,
        total_exposure_pct=0.0,
        open_positions=0,
        consecutive_losses=0,
        daily_trades=0,
        is_circuit_breaker_active=False,
    )
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


def fake_event_outbox(
    *,
    id: UUID | None = None,
    event_type: str = "trading.order.placed",
    status: EventOutbox.OutboxStatus = EventOutbox.OutboxStatus.PENDING,
    **overrides,
) -> EventOutbox:
    """Create an EventOutbox instance with sensible defaults."""
    entry = EventOutbox(
        id=id or uuid4(),
        aggregate_type="order",
        aggregate_id=uuid4(),
        event_type=event_type,
        event_version=1,
        payload={"order_id": str(uuid4()), "symbol": "EURUSD"},
        status=status,
        publish_attempts=0,
    )
    for k, v in overrides.items():
        setattr(entry, k, v)
    return entry


def fake_risk_alert(
    *,
    id: UUID | None = None,
    level: RiskLevel = RiskLevel.WARNING,
    category: str = "drawdown",
    **overrides,
) -> RiskAlert:
    """Create a RiskAlert instance with sensible defaults."""
    alert = RiskAlert(
        id=id or uuid4(),
        level=level,
        category=category,
        message=f"Test {category} alert",
        current_value=5.0,
        threshold_value=3.0,
        action_required=False,
        acknowledged=False,
    )
    for k, v in overrides.items():
        setattr(alert, k, v)
    return alert


def fake_deal(
    *,
    id: UUID | None = None,
    order_id: UUID | None = None,
    position_id: UUID | None = None,
    **overrides,
) -> Deal:
    """Create a Deal instance with sensible defaults."""
    deal = Deal(
        id=id or uuid4(),
        order_id=order_id or uuid4(),
        position_id=position_id or uuid4(),
        symbol="EURUSD",
        side=OrderSide.BUY,
        quantity=0.1,
        price=1.1000,
        commission=0.0,
        slippage=0.0,
        realized_pnl=0.0,
    )
    for k, v in overrides.items():
        setattr(deal, k, v)
    return deal
