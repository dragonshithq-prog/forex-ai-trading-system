"""Execution Engine — saga-based order lifecycle with compensating transactions.

Each order submission follows a saga pattern:
  1. Validate (pre-trade checklist)
  2. Persist order as PENDING in DB
  3. Submit to broker
  4. On broker ack → mark NEW/ACCEPTED
  5. On fill → create Position via PositionManager
  6. On failure at any step → run compensating actions (cancel, reject)

All state transitions are persisted via UnitOfWork and published as events.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import structlog

from forex_trading.shared.database.models_trading import (
    Order as DBOrder,
    PositionSide,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
)
from forex_trading.shared.database.uow import UnitOfWorkFactory
from forex_trading.shared.messaging.event_bus import EventBus
from forex_trading.shared.monitoring import (
    trade_execution_duration_seconds,
    trade_executions_total,
    trade_fills_total,
    trade_volume_lots,
)
from forex_trading.execution.position_manager import PositionManager
from forex_trading.risk.engine import RiskEngine
from forex_trading.strategy.engine import StrategyEngine, TradeSignal

logger = structlog.get_logger()

# ─── Pre-trade checklist constants ───────────────────────────────────────────

_MIN_AI_CONFIDENCE = 0.6
_MAX_CORRELATED_POSITIONS = 3
_NEWS_BLACKOUT_MINUTES = 5
_OFF_HOURS_START_UTC = 22
_OFF_HOURS_END_UTC = 0

# ─── Position management thresholds (multiples of ATR) ────────────────────────

_BREAKEVEN_ATR_MULTIPLE = 1.0
_PARTIAL_CLOSE_1_ATR = 2.0
_PARTIAL_CLOSE_2_ATR = 3.0
_EARLY_EXIT_REVERSAL_ATR = 0.5

# ─── Saga step types ──────────────────────────────────────────────────────────


class SagaStep(str, Enum):
    VALIDATE = "validate"
    PERSIST_ORDER = "persist_order"
    SUBMIT_BROKER = "submit_broker"
    AWAIT_FILL = "await_fill"
    CREATE_POSITION = "create_position"
    COMPLETE = "complete"


class SagaStatus(str, Enum):
    PENDING = "pending"
    STEP_RUNNING = "step_running"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


@dataclass
class Order:
    order_id: UUID = field(default_factory=uuid4)
    broker_account_id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: float = 0.0
    price: float | None = None
    stop_price: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: float | None = None
    commission: float = 0.0
    slippage: float = 0.0
    broker_order_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    saga_status: SagaStatus = SagaStatus.PENDING
    current_step: SagaStep = SagaStep.VALIDATE
    strategy_id: UUID | None = None


@dataclass
class OrderResult:
    success: bool
    order: Order
    message: str = ""
    error_code: str | None = None


@dataclass
class Fill:
    fill_id: UUID = field(default_factory=uuid4)
    order_id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    price: float = 0.0
    commission: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExecutionResult:
    success: bool
    order_id: UUID | None = None
    broker_order_id: str | None = None
    filled_price: float | None = None
    filled_quantity: float | None = None
    slippage_pips: float = 0.0
    rejection_reason: str | None = None
    execution_time_ms: float = 0.0


@dataclass
class ManagementAction:
    action: str
    new_stop_loss: float | None = None
    close_pct: float | None = None
    reason: str = ""


@dataclass
class _TrackedPosition:
    position_id: UUID
    symbol: str
    direction: str
    entry_price: float
    current_stop_loss: float
    take_profit: float
    quantity: float
    atr: float
    strategy_type: str
    max_holding_minutes: int
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    highest_price: float = 0.0
    lowest_price: float = 0.0
    partial_1_done: bool = False
    partial_2_done: bool = False
    breakeven_moved: bool = False
    broker_connection_id: UUID | None = None


class ExecutionEngine:
    """Saga-based trade execution engine with compensating transactions.

    Orchestrates the full trade lifecycle:
      1. Validate signal through pre-trade checklist
      2. Create order in DB (PENDING)
      3. Submit to broker gateway
      4. On fill, create Position via PositionManager
      5. Manage ongoing position (SL trailing, partial closes)
      6. On failure → compensate (cancel broker order, reject in DB)
    """

    def __init__(
        self,
        risk_engine: RiskEngine,
        broker_gateway: Any,
        strategy_engine: StrategyEngine,
        position_manager: PositionManager,
        uow_factory: UnitOfWorkFactory,
        event_bus: EventBus,
        allow_off_hours: bool = False,
        max_spread_pips: float = 5.0,
    ) -> None:
        self._risk_engine = risk_engine
        self._broker_gateway = broker_gateway
        self._strategy_engine = strategy_engine
        self._position_manager = position_manager
        self._uow_factory = uow_factory
        self._event_bus = event_bus
        self._allow_off_hours = allow_off_hours
        self._max_spread_pips = max_spread_pips

        # In-memory sagas (order_id → Order) for active orders only.
        # Full state is in the DB; this is a fast cache for the management loop.
        self._active_sagas: dict[UUID, Order] = {}
        self._tracked_positions: dict[UUID, _TrackedPosition] = {}
        self._order_history: list[Order] = []
        self._news_events: list[datetime] = []

    # ─── Public API ──────────────────────────────────────────────────────────

    async def process_signal(
        self,
        signal: TradeSignal,
        broker_connection_id: UUID,
    ) -> ExecutionResult:
        """Submit a trade signal through the saga pipeline.

        Returns ExecutionResult with success=False and rejection_reason
        if any step fails (and compensating actions were taken).
        """
        t_start = time.monotonic()
        log = logger.bind(
            signal_id=str(signal.signal_id),
            symbol=signal.symbol,
            direction=signal.direction.value,
        )

        # Step 1: Validate
        rejection = await self._run_pre_trade_checklist(signal, broker_connection_id)
        if rejection:
            log.warning("signal_rejected", reason=rejection)
            return ExecutionResult(
                success=False,
                rejection_reason=rejection,
                execution_time_ms=(time.monotonic() - t_start) * 1000,
            )

        from forex_trading.ai.agents.base import SignalDirection
        side = (
            OrderSide.BUY
            if signal.direction == SignalDirection.LONG
            else OrderSide.SELL
        )

        # Create saga order object
        order = Order(
            broker_account_id=broker_connection_id,
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=0.0,  # set after sizing
            stop_loss=signal.stop_loss if signal.stop_loss > 0 else None,
            take_profit=signal.take_profit if signal.take_profit > 0 else None,
            strategy_id=signal.signal_id,
            metadata={"signal_id": str(signal.signal_id)},
            saga_status=SagaStatus.PENDING,
            current_step=SagaStep.VALIDATE,
        )

        # Step 2: Risk assessment (also gets us the sized quantity)
        account_info = await self._broker_gateway.get_account_info(broker_connection_id)
        if account_info is None:
            return ExecutionResult(
                success=False,
                rejection_reason="Cannot fetch account info from broker",
                execution_time_ms=(time.monotonic() - t_start) * 1000,
            )

        async with self._uow_factory as uow:
            self._risk_engine.attach_uow(uow)
            risk_assessment = await self._risk_engine.assess_trade(
                broker_account_id=broker_connection_id,
                symbol=signal.symbol,
                side=signal.direction.value,
                size=1.0,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss if signal.stop_loss > 0 else None,
            )

        if not risk_assessment.is_approved:
            violations = "; ".join(risk_assessment.violations)
            log.warning("risk_engine_rejection", violations=risk_assessment.violations)
            return ExecutionResult(
                success=False,
                rejection_reason=f"Risk engine: {violations}",
                execution_time_ms=(time.monotonic() - t_start) * 1000,
            )

        # Use the size from risk assessment or signal metadata
        order.quantity = risk_assessment.adjusted_size or signal.parameters.metadata.get("lots", 0.01)

        # Step 3: Persist order in DB and submit to broker via saga
        result = await self._run_saga(order, broker_connection_id, signal)

        elapsed_ms = (time.monotonic() - t_start) * 1000
        result.execution_time_ms = elapsed_ms

        status_label = "approved" if result.success else "rejected"
        trade_executions_total.labels(
            symbol=signal.symbol,
            side=signal.direction.value,
            status=status_label,
        ).inc()
        if result.success:
            trade_execution_duration_seconds.labels(
                symbol=signal.symbol,
            ).observe(elapsed_ms / 1000.0)
            trade_volume_lots.labels(symbol=signal.symbol).inc(order.quantity)

        return result

    async def manage_position(
        self,
        position_id: UUID,
        current_price: float,
    ) -> ManagementAction:
        """Apply position management rules (breakeven, trailing, partial close)."""
        pos = self._tracked_positions.get(position_id)
        if pos is None:
            return ManagementAction(action="hold", reason="position not tracked")

        if current_price <= 0:
            return ManagementAction(action="hold", reason="invalid current_price")

        atr = pos.atr if pos.atr > 0 else 0.0001
        is_long = pos.direction == "long"

        if is_long:
            pos.highest_price = max(pos.highest_price, current_price)
            favour_distance = current_price - pos.entry_price
            peak_distance = pos.highest_price - pos.entry_price
        else:
            pos.lowest_price = min(pos.lowest_price, current_price)
            favour_distance = pos.entry_price - current_price
            peak_distance = pos.entry_price - pos.lowest_price

        holding_minutes = (
            datetime.now(timezone.utc) - pos.opened_at
        ).total_seconds() / 60.0
        if holding_minutes > pos.max_holding_minutes:
            return ManagementAction(
                action="close",
                close_pct=100.0,
                reason=f"max holding time exceeded ({pos.max_holding_minutes} min)",
            )

        reversal_from_peak = peak_distance - favour_distance
        if reversal_from_peak > _EARLY_EXIT_REVERSAL_ATR * atr and pos.partial_1_done:
            return ManagementAction(
                action="close",
                close_pct=100.0,
                reason=f"reversal {reversal_from_peak/atr:.2f}×ATR from peak",
            )

        if favour_distance >= _PARTIAL_CLOSE_2_ATR * atr and not pos.partial_2_done:
            pos.partial_2_done = True
            new_sl = (
                current_price - 0.5 * atr if is_long else current_price + 0.5 * atr
            )
            pos.current_stop_loss = new_sl
            return ManagementAction(
                action="partial_close",
                new_stop_loss=new_sl,
                close_pct=33.0,
                reason=f"price moved {_PARTIAL_CLOSE_2_ATR}×ATR; close second partial",
            )

        if favour_distance >= _PARTIAL_CLOSE_1_ATR * atr and not pos.partial_1_done:
            pos.partial_1_done = True
            new_sl = (
                current_price - atr if is_long else current_price + atr
            )
            pos.current_stop_loss = new_sl
            return ManagementAction(
                action="partial_close",
                new_stop_loss=new_sl,
                close_pct=33.0,
                reason=f"price moved {_PARTIAL_CLOSE_1_ATR}×ATR; close first partial",
            )

        if favour_distance >= _BREAKEVEN_ATR_MULTIPLE * atr and not pos.breakeven_moved:
            pos.breakeven_moved = True
            pos.current_stop_loss = pos.entry_price
            return ManagementAction(
                action="move_breakeven",
                new_stop_loss=pos.entry_price,
                reason=f"price moved {_BREAKEVEN_ATR_MULTIPLE}×ATR; SL to breakeven",
            )

        if pos.partial_1_done:
            trail_distance = atr * (0.5 if pos.partial_2_done else 1.0)
            new_sl = (
                current_price - trail_distance if is_long else current_price + trail_distance
            )
            improved = (
                (is_long and new_sl > pos.current_stop_loss)
                or (not is_long and new_sl < pos.current_stop_loss)
            )
            if improved:
                pos.current_stop_loss = new_sl
                return ManagementAction(
                    action="trail_stop",
                    new_stop_loss=new_sl,
                    reason="trailing stop updated",
                )

        return ManagementAction(action="hold", reason="no action required")

    async def close_position(
        self,
        position_id: UUID,
        reason: str,
        partial_pct: float = 100.0,
    ) -> bool:
        if partial_pct <= 0 or partial_pct > 100:
            logger.error("invalid_partial_pct", partial_pct=partial_pct)
            return False

        pos = self._tracked_positions.get(position_id)
        if pos is None:
            logger.warning("close_position_not_found", position_id=str(position_id))
            return False

        close_qty = max(round(pos.quantity * (partial_pct / 100.0), 2), 0.01)
        connection_id = pos.broker_connection_id
        if connection_id is None:
            logger.error("no_broker_connection", position_id=str(position_id))
            return False

        side = "sell" if pos.direction == "long" else "buy"
        result = await self._broker_gateway.place_order(
            connection_id=connection_id,
            symbol=pos.symbol,
            side=side,
            quantity=close_qty,
            order_type="market",
        )

        if result.get("error"):
            logger.error(
                "close_position_failed",
                position_id=str(position_id),
                error=result["error"],
                reason=reason,
            )
            return False

        # Persist close via PositionManager
        if partial_pct >= 100.0:
            await self._position_manager.close_position(
                position_id=position_id,
                exit_price=result.get("fill_price", pos.entry_price),
                realized_pnl=0.0,
                reason=reason,
            )
            self._tracked_positions.pop(position_id, None)
            saga = self._active_sagas.pop(position_id, None)
            if saga:
                saga.status = OrderStatus.FILLED
                self._order_history.append(saga)
        else:
            remaining = round(pos.quantity - close_qty, 2)
            pos.quantity = remaining
            await self._position_manager.update_position(
                position_id=position_id,
                current_price=result.get("fill_price", pos.entry_price),
            )

        logger.info(
            "position_closed",
            position_id=str(position_id),
            partial_pct=partial_pct,
            reason=reason,
        )
        return True

    async def emergency_close_all(self, reason: str) -> dict[str, Any]:
        logger.critical("emergency_close_all", reason=reason, positions=len(self._tracked_positions))
        results: dict[str, Any] = {"reason": reason, "closed": [], "failed": []}
        for pid in list(self._tracked_positions.keys()):
            if await self.close_position(pid, reason=reason, partial_pct=100.0):
                results["closed"].append(str(pid))
            else:
                results["failed"].append(str(pid))
        return results

    async def on_fill(self, order_id: UUID, fill: Fill) -> None:
        """Handle a fill notification from the broker gateway."""
        saga = self._active_sagas.get(order_id)
        if saga is None:
            logger.warning("fill_unknown_order", order_id=str(order_id))
            return

        saga.filled_quantity += fill.quantity
        saga.filled_price = fill.price
        saga.commission += fill.commission

        if saga.filled_quantity >= saga.quantity:
            saga.status = OrderStatus.FILLED
            saga.current_step = SagaStep.CREATE_POSITION
            saga.updated_at = datetime.now(timezone.utc)

            # Persist the fill in DB via order repository
            async with self._uow_factory as uow:
                db_order = await uow.orders.get(order_id)
                if db_order is not None:
                    await uow.orders.update(db_order, {
                        "status": OrderStatus.FILLED,
                        "filled_quantity": saga.filled_quantity,
                        "filled_price": saga.filled_price,
                        "broker_order_id": saga.broker_order_id,
                        "commission": saga.commission,
                    })
                    uow.add_event(
                        aggregate_type="order",
                        aggregate_id=order_id,
                        event_type="trading.order.filled",
                        payload={
                            "order_id": str(order_id),
                            "symbol": saga.symbol,
                            "side": saga.side.value,
                            "filled_qty": saga.filled_quantity,
                            "fill_price": saga.filled_price,
                            "broker_order_id": saga.broker_order_id,
                        },
                    )
                    await uow.commit()

            # Create position in DB
            await self._position_manager.open_position(
                broker_account_id=saga.broker_account_id,
                symbol=saga.symbol,
                side=PositionSide.LONG if saga.side == OrderSide.BUY else PositionSide.SHORT,
                size=saga.filled_quantity,
                entry_price=fill.price,
                broker_position_id=saga.broker_order_id,
                stop_loss=saga.stop_loss,
                take_profit=saga.take_profit,
                strategy_id=saga.strategy_id,
            )

            # Register in-memory tracking
            atr = saga.metadata.get("atr", 0.001)
            holding_minutes = saga.metadata.get("max_holding_minutes", 240)
            self._tracked_positions[order_id] = _TrackedPosition(
                position_id=order_id,
                symbol=saga.symbol,
                direction="long" if saga.side == OrderSide.BUY else "short",
                entry_price=fill.price,
                current_stop_loss=saga.stop_loss or fill.price,
                take_profit=saga.take_profit or fill.price,
                quantity=saga.filled_quantity,
                atr=atr,
                strategy_type=saga.metadata.get("strategy", ""),
                max_holding_minutes=holding_minutes,
                highest_price=fill.price,
                lowest_price=fill.price,
                broker_connection_id=saga.broker_account_id,
            )

            trade_fills_total.labels(
                symbol=saga.symbol,
                side=saga.side.value,
            ).inc()

            saga.saga_status = SagaStatus.COMPLETED
            saga.current_step = SagaStep.COMPLETE
            logger.info(
                "order_filled",
                order_id=str(order_id),
                filled_qty=fill.quantity,
                fill_price=fill.price,
            )
        else:
            saga.status = OrderStatus.PARTIALLY_FILLED
            saga.updated_at = datetime.now(timezone.utc)

    # ─── Saga internals ─────────────────────────────────────────────────────

    async def _run_saga(
        self,
        order: Order,
        broker_connection_id: UUID,
        signal: TradeSignal,
    ) -> ExecutionResult:
        """Execute the full saga pipeline with compensating transactions."""
        # Step 1: Persist order in DB
        order.current_step = SagaStep.PERSIST_ORDER
        try:
            async with self._uow_factory as uow:
                # Map to DB Order model
                db_order = DBOrder(
                    id=order.order_id,
                    broker_account_id=order.broker_account_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    order_type=order.order_type.value,
                    quantity=order.quantity,
                    price=order.price,
                    stop_price=order.stop_price,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    time_in_force=order.time_in_force.value,
                    status=OrderStatus.PENDING.value,
                    metadata=order.metadata,
                )
                await uow.orders.add(db_order)
                uow.add_event(
                    aggregate_type="order",
                    aggregate_id=order.order_id,
                    event_type="trading.order.created",
                    payload={
                        "order_id": str(order.order_id),
                        "symbol": order.symbol,
                        "side": order.side.value,
                        "quantity": order.quantity,
                        "broker_account_id": str(broker_connection_id),
                    },
                )
                await uow.commit()
        except Exception as exc:
            logger.error("saga_persist_failed", error=str(exc))
            return ExecutionResult(
                success=False,
                rejection_reason=f"DB persist failed: {exc}",
            )

        # Step 2: Submit to broker
        order.current_step = SagaStep.SUBMIT_BROKER
        order.saga_status = SagaStatus.STEP_RUNNING
        atr = signal.parameters.metadata.get("atr", 0.001)
        order.metadata["atr"] = atr
        order.metadata["max_holding_minutes"] = signal.parameters.max_holding_time_minutes
        order.metadata["strategy"] = signal.strategy.value

        broker_result = await self._broker_gateway.place_order(
            connection_id=broker_connection_id,
            symbol=signal.symbol,
            side=order.side.value,
            quantity=order.quantity,
            order_type=order.order_type.value,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
        )

        if broker_result.get("error"):
            # Compensate: mark order REJECTED in DB
            order.status = OrderStatus.REJECTED
            order.saga_status = SagaStatus.FAILED
            async with self._uow_factory as uow:
                db_order = await uow.orders.get(order.order_id)
                if db_order is not None:
                    await uow.orders.update(db_order, {
                        "status": OrderStatus.REJECTED.value,
                        "rejection_reason": broker_result["error"],
                    })
                    uow.add_event(
                        aggregate_type="order",
                        aggregate_id=order.order_id,
                        event_type="trading.order.rejected",
                        payload={
                            "order_id": str(order.order_id),
                            "reason": broker_result["error"],
                        },
                    )
                    await uow.commit()
            self._order_history.append(order)
            return ExecutionResult(
                success=False,
                order_id=order.order_id,
                rejection_reason=broker_result["error"],
            )

        # Broker accepted
        order.status = OrderStatus.NEW
        order.broker_order_id = broker_result.get("order_id")
        filled_price = broker_result.get("fill_price")
        if filled_price:
            # Immediate fill (market order)
            fill = Fill(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=filled_price,
            )
            await self.on_fill(order.order_id, fill)
            slippage_pips = abs(filled_price - signal.entry_price) / 0.0001
            return ExecutionResult(
                success=True,
                order_id=order.order_id,
                broker_order_id=order.broker_order_id,
                filled_price=filled_price,
                filled_quantity=order.quantity,
                slippage_pips=round(slippage_pips, 1),
            )

        # Not yet filled — register active saga for async fill monitoring
        order.current_step = SagaStep.AWAIT_FILL
        self._active_sagas[order.order_id] = order
        async with self._uow_factory as uow:
            db_order = await uow.orders.get(order.order_id)
            if db_order is not None:
                await uow.orders.update(db_order, {
                    "status": OrderStatus.NEW.value,
                    "broker_order_id": order.broker_order_id,
                })
                await uow.commit()

        logger.info(
            "order_submitted",
            order_id=str(order.order_id),
            symbol=order.symbol,
            broker_order_id=order.broker_order_id,
        )
        return ExecutionResult(
            success=True,
            order_id=order.order_id,
            broker_order_id=order.broker_order_id,
        )

    # ─── Pre-trade checklist ─────────────────────────────────────────────────

    async def _run_pre_trade_checklist(
        self,
        signal: TradeSignal,
        broker_connection_id: UUID,
    ) -> str | None:
        strategy = self._strategy_engine.get_strategy(signal.strategy)
        if strategy is not None:
            from forex_trading.ai.agents.base import MarketContext
            ctx = MarketContext(symbol=signal.symbol, timeframe="H1")
            validation = strategy.validate_signal(ctx, signal)
            if not validation.is_valid:
                return f"Strategy validation: {'; '.join(validation.errors)}"

        if not self._allow_off_hours:
            now_hour = datetime.now(timezone.utc).hour
            if _OFF_HOURS_START_UTC <= now_hour or now_hour < _OFF_HOURS_END_UTC:
                return (
                    f"Off-hours trading blocked (UTC hour {now_hour}); "
                    "set allow_off_hours=True to override"
                )

        spread_pips = signal.parameters.metadata.get("current_spread_pips")
        if spread_pips is not None and spread_pips > self._max_spread_pips:
            return (
                f"Spread {spread_pips:.1f} pips exceeds max {self._max_spread_pips:.1f}"
            )

        news_rejection = self._check_news_blackout()
        if news_rejection:
            return news_rejection

        correlated_count = self._count_correlated_positions(signal.symbol)
        if correlated_count >= _MAX_CORRELATED_POSITIONS:
            return (
                f"Too many correlated positions ({correlated_count}); "
                f"max is {_MAX_CORRELATED_POSITIONS}"
            )

        if signal.confidence < _MIN_AI_CONFIDENCE:
            return (
                f"AI confidence {signal.confidence:.2f} below threshold {_MIN_AI_CONFIDENCE:.2f}"
            )

        return None

    def _check_news_blackout(self) -> str | None:
        now = datetime.now(timezone.utc)
        window = timedelta(minutes=_NEWS_BLACKOUT_MINUTES)
        for event_time in self._news_events:
            if abs((now - event_time).total_seconds()) <= window.total_seconds():
                return (
                    f"News blackout active; event at {event_time.isoformat()} UTC"
                )
        return None

    def _count_correlated_positions(self, symbol: str) -> int:
        if len(symbol) < 6:
            return 0
        base = symbol[:3].upper()
        quote = symbol[3:6].upper()
        count = 0
        for pos in self._tracked_positions.values():
            s = pos.symbol.upper()
            if len(s) >= 6 and (s[:3] in (base, quote) or s[3:6] in (base, quote)):
                count += 1
        return count

    def add_news_event(self, event_time: datetime) -> None:
        self._news_events.append(event_time)

    def clear_news_events(self) -> None:
        self._news_events.clear()

    # ─── Compatibility surface ───────────────────────────────────────────────

    async def create_order(
        self,
        broker_account_id: UUID,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        metadata: dict[str, Any] | None = None,
    ) -> Order:
        order = Order(
            broker_account_id=broker_account_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            take_profit=take_profit,
            stop_loss=stop_loss,
            time_in_force=time_in_force,
            metadata=metadata or {},
        )
        self._active_sagas[order.order_id] = order
        logger.info(
            "order_created",
            order_id=str(order.order_id),
            symbol=symbol,
            side=side.value,
        )
        return order

    async def submit_order(self, order: Order) -> OrderResult:
        validation = self._validate_order(order)
        if not validation["valid"]:
            order.status = OrderStatus.REJECTED
            return OrderResult(
                success=False,
                order=order,
                message=validation["reason"],
                error_code="VALIDATION_FAILED",
            )
        order.status = OrderStatus.NEW
        order.updated_at = datetime.now(timezone.utc)
        self._active_sagas[order.order_id] = order
        return OrderResult(success=True, order=order, message="Order submitted")

    async def cancel_order(self, order_id: UUID) -> OrderResult:
        saga = self._active_sagas.get(order_id)
        if not saga:
            return OrderResult(
                success=False,
                order=Order(order_id=order_id),
                message="Order not found",
                error_code="NOT_FOUND",
            )
        saga.status = OrderStatus.CANCELLED
        saga.saga_status = SagaStatus.COMPENSATED
        saga.updated_at = datetime.now(timezone.utc)
        self._active_sagas.pop(order_id, None)
        self._order_history.append(saga)
        logger.info("order_cancelled", order_id=str(order_id))
        return OrderResult(success=True, order=saga, message="Order cancelled")

    async def modify_order(
        self,
        order_id: UUID,
        quantity: float | None = None,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        saga = self._active_sagas.get(order_id)
        if not saga:
            return OrderResult(
                success=False,
                order=Order(order_id=order_id),
                message="Order not found",
                error_code="NOT_FOUND",
            )
        if quantity is not None:
            saga.quantity = quantity
        if price is not None:
            saga.price = price
        if stop_loss is not None:
            saga.stop_loss = stop_loss
        if take_profit is not None:
            saga.take_profit = take_profit
        saga.updated_at = datetime.now(timezone.utc)
        return OrderResult(success=True, order=saga, message="Order modified")

    def get_order(self, order_id: UUID) -> Order | None:
        return (
            self._active_sagas.get(order_id)
            or next((o for o in self._order_history if o.order_id == order_id), None)
        )

    def get_active_orders(self, broker_account_id: UUID | None = None) -> list[Order]:
        if broker_account_id:
            return [o for o in self._active_sagas.values() if o.broker_account_id == broker_account_id]
        return list(self._active_sagas.values())

    def get_order_history(self, limit: int = 100) -> list[Order]:
        return self._order_history[-limit:]

    def _validate_order(self, order: Order) -> dict[str, Any]:
        if order.quantity <= 0:
            return {"valid": False, "reason": "Invalid quantity"}
        if order.order_type in (OrderType.LIMIT, OrderType.STOP) and order.price is None:
            return {"valid": False, "reason": "Price required for limit/stop orders"}
        if order.order_type == OrderType.STOP_LIMIT and (
            order.price is None or order.stop_price is None
        ):
            return {"valid": False, "reason": "Both price and stop price required"}
        return {"valid": True, "reason": ""}



