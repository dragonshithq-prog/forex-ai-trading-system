"""Execution Engine - orchestrates the full trade lifecycle end to end."""

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import structlog

from forex_trading.broker.gateway import BrokerGateway
from forex_trading.risk.engine import RiskEngine
from forex_trading.strategy.engine import StrategyEngine, TradeSignal
from forex_trading.strategy.engine import StrategyType  # noqa: F401 – re-exported for callers

logger = structlog.get_logger()

# ─── Pre-trade checklist constants ───────────────────────────────────────────

_MIN_AI_CONFIDENCE = 0.6
_MAX_CORRELATED_POSITIONS = 3
_NEWS_BLACKOUT_MINUTES = 5
_OFF_HOURS_START_UTC = 22  # 22:00 UTC – weekend / low-liquidity cut-off
_OFF_HOURS_END_UTC = 0    # 00:00 UTC

# ─── Position management thresholds (multiples of ATR) ────────────────────────

_BREAKEVEN_ATR_MULTIPLE = 1.0
_PARTIAL_CLOSE_1_ATR = 2.0   # close 33 % at 2×ATR
_PARTIAL_CLOSE_2_ATR = 3.0   # close another 33 % at 3×ATR
_EARLY_EXIT_REVERSAL_ATR = 0.5


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"
    OCO = "oco"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    NEW = "new"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TimeInForce(str, Enum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    DAY = "day"


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
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


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
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ─── ExecutionEngine-specific types ───────────────────────────────────────────


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
    action: str  # "trail_stop" | "partial_close" | "move_breakeven" | "close" | "hold"
    new_stop_loss: float | None = None
    close_pct: float | None = None
    reason: str = ""


@dataclass
class _TrackedPosition:
    """Internal position tracking record."""
    position_id: UUID
    symbol: str
    direction: str  # "long" | "short"
    entry_price: float
    current_stop_loss: float
    take_profit: float
    quantity: float
    atr: float
    strategy_type: str
    max_holding_minutes: int
    opened_at: datetime = field(default_factory=datetime.utcnow)
    highest_price: float = 0.0  # for trailing – peak in favour
    lowest_price: float = 0.0   # for trailing – trough in favour (short)
    partial_1_done: bool = False
    partial_2_done: bool = False
    breakeven_moved: bool = False
    broker_connection_id: UUID | None = None


class ExecutionEngine:
    """
    Trade Execution Engine.

    Orchestrates the full trade lifecycle:
    1. Receives trade signal from strategy engine
    2. Validates signal through pre-trade checklist
    3. Applies risk-adjusted position sizing
    4. Routes to best broker connection
    5. Submits order and monitors fill
    6. Manages ongoing position (SL trailing, partial close)
    7. Records all execution details
    """

    def __init__(
        self,
        risk_engine: RiskEngine,
        broker_gateway: BrokerGateway,
        strategy_engine: StrategyEngine,
        allow_off_hours: bool = False,
        max_spread_pips: float = 5.0,
    ) -> None:
        self._risk_engine = risk_engine
        self._broker_gateway = broker_gateway
        self._strategy_engine = strategy_engine
        self._allow_off_hours = allow_off_hours
        self._max_spread_pips = max_spread_pips

        self._positions: dict[UUID, _TrackedPosition] = {}
        self._pending_orders: dict[UUID, Order] = {}
        self._active_orders: dict[UUID, Order] = {}
        self._order_history: list[Order] = []
        self._news_events: list[datetime] = []  # high-impact news timestamps

    # ─── Public API ──────────────────────────────────────────────────────────

    async def process_signal(
        self,
        signal: TradeSignal,
        broker_connection_id: UUID,
    ) -> ExecutionResult:
        """
        Run the full pre-trade checklist and submit the order if approved.

        Returns ExecutionResult with success=False and rejection_reason set
        if any checklist item fails.
        """
        t_start = time.monotonic()
        log = logger.bind(
            signal_id=str(signal.signal_id),
            symbol=signal.symbol,
            direction=signal.direction.value,
        )

        rejection = await self._run_pre_trade_checklist(signal, broker_connection_id)
        if rejection:
            log.warning("signal_rejected", reason=rejection)
            return ExecutionResult(
                success=False,
                rejection_reason=rejection,
                execution_time_ms=(time.monotonic() - t_start) * 1000,
            )

        # Determine side
        from forex_trading.ai.agents.base import SignalDirection
        side = (
            OrderSide.BUY
            if signal.direction == SignalDirection.LONG
            else OrderSide.SELL
        )

        # Position sizing via risk engine's state
        account_info = await self._broker_gateway.get_account_info(broker_connection_id)
        if account_info is None:
            return ExecutionResult(
                success=False,
                rejection_reason="Cannot fetch account info from broker",
                execution_time_ms=(time.monotonic() - t_start) * 1000,
            )

        risk_assessment = await self._risk_engine.assess_trade(
            symbol=signal.symbol,
            side=signal.direction.value,
            size=1.0,  # placeholder; actual sizing done by PositionSizer upstream
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss if signal.stop_loss > 0 else None,
        )

        if not risk_assessment.is_approved:
            reason = "; ".join(risk_assessment.violations)
            log.warning("risk_engine_rejection", violations=risk_assessment.violations)
            return ExecutionResult(
                success=False,
                rejection_reason=f"Risk engine: {reason}",
                execution_time_ms=(time.monotonic() - t_start) * 1000,
            )

        # Construct and submit order
        order = Order(
            broker_account_id=broker_connection_id,
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=signal.parameters.metadata.get("lots", 0.01),
            stop_loss=signal.stop_loss if signal.stop_loss > 0 else None,
            take_profit=signal.take_profit if signal.take_profit > 0 else None,
            metadata={"signal_id": str(signal.signal_id)},
        )
        self._pending_orders[order.order_id] = order

        broker_result = await self._broker_gateway.place_order(
            connection_id=broker_connection_id,
            symbol=signal.symbol,
            side=side.value,
            quantity=order.quantity,
            order_type=order.order_type.value,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
        )

        elapsed_ms = (time.monotonic() - t_start) * 1000

        if broker_result.get("error"):
            order.status = OrderStatus.REJECTED
            self._pending_orders.pop(order.order_id, None)
            self._order_history.append(order)
            return ExecutionResult(
                success=False,
                order_id=order.order_id,
                rejection_reason=broker_result["error"],
                execution_time_ms=elapsed_ms,
            )

        order.status = OrderStatus.FILLED
        order.broker_order_id = broker_result.get("order_id")
        filled_price = broker_result.get("fill_price") or signal.entry_price
        order.filled_price = filled_price
        order.filled_quantity = order.quantity
        self._pending_orders.pop(order.order_id, None)
        self._active_orders[order.order_id] = order

        # Compute slippage
        slippage_pips = abs(filled_price - signal.entry_price) / 0.0001

        # Register position for ongoing management
        atr = signal.parameters.metadata.get("atr", 0.001)
        self._positions[order.order_id] = _TrackedPosition(
            position_id=order.order_id,
            symbol=signal.symbol,
            direction=signal.direction.value,
            entry_price=filled_price,
            current_stop_loss=signal.stop_loss if signal.stop_loss > 0 else filled_price,
            take_profit=signal.take_profit,
            quantity=order.quantity,
            atr=atr,
            strategy_type=signal.strategy.value,
            max_holding_minutes=signal.parameters.max_holding_time_minutes,
            highest_price=filled_price,
            lowest_price=filled_price,
            broker_connection_id=broker_connection_id,
        )

        log.info(
            "order_executed",
            order_id=str(order.order_id),
            filled_price=filled_price,
            slippage_pips=round(slippage_pips, 1),
            execution_ms=round(elapsed_ms, 1),
        )

        return ExecutionResult(
            success=True,
            order_id=order.order_id,
            broker_order_id=order.broker_order_id,
            filled_price=filled_price,
            filled_quantity=order.quantity,
            slippage_pips=round(slippage_pips, 1),
            execution_time_ms=elapsed_ms,
        )

    async def manage_position(
        self,
        position_id: UUID,
        current_price: float,
    ) -> ManagementAction:
        """
        Apply position management rules.

        Logic (multiples of ATR measured from entry):
        1. 1× ATR in favour  → move SL to breakeven
        2. 2× ATR in favour  → close 33%, trail SL
        3. 3× ATR in favour  → close another 33%, tight trail
        4. 0.5× ATR reversal from peak → consider early exit
        5. Max holding time exceeded    → close
        """
        pos = self._positions.get(position_id)
        if pos is None:
            return ManagementAction(action="hold", reason="position not tracked")

        if current_price <= 0:
            return ManagementAction(action="hold", reason="invalid current_price")

        atr = pos.atr if pos.atr > 0 else 0.0001
        is_long = pos.direction == "long"

        # Track peak/trough in favour
        if is_long:
            pos.highest_price = max(pos.highest_price, current_price)
            favour_distance = current_price - pos.entry_price
            peak_distance = pos.highest_price - pos.entry_price
        else:
            pos.lowest_price = min(pos.lowest_price, current_price)
            favour_distance = pos.entry_price - current_price
            peak_distance = pos.entry_price - pos.lowest_price

        # Rule 5: max holding time
        holding_minutes = (datetime.utcnow() - pos.opened_at).total_seconds() / 60.0
        if holding_minutes > pos.max_holding_minutes:
            return ManagementAction(
                action="close",
                close_pct=100.0,
                reason=f"max holding time exceeded ({pos.max_holding_minutes} min)",
            )

        # Rule 4: reversal from peak
        reversal_from_peak = peak_distance - favour_distance
        if reversal_from_peak > _EARLY_EXIT_REVERSAL_ATR * atr and pos.partial_1_done:
            return ManagementAction(
                action="close",
                close_pct=100.0,
                reason=f"reversal {reversal_from_peak/atr:.2f}×ATR from peak",
            )

        # Rule 3: 3× ATR in favour → close another 33%, tight trail
        if favour_distance >= _PARTIAL_CLOSE_2_ATR * atr and not pos.partial_2_done:
            pos.partial_2_done = True
            new_sl = (
                current_price - 0.5 * atr
                if is_long
                else current_price + 0.5 * atr
            )
            pos.current_stop_loss = new_sl
            return ManagementAction(
                action="partial_close",
                new_stop_loss=new_sl,
                close_pct=33.0,
                reason=f"price moved {_PARTIAL_CLOSE_2_ATR}×ATR; close second partial, tight trail",
            )

        # Rule 2: 2× ATR in favour → close 33%, trail
        if favour_distance >= _PARTIAL_CLOSE_1_ATR * atr and not pos.partial_1_done:
            pos.partial_1_done = True
            new_sl = (
                current_price - atr
                if is_long
                else current_price + atr
            )
            pos.current_stop_loss = new_sl
            return ManagementAction(
                action="partial_close",
                new_stop_loss=new_sl,
                close_pct=33.0,
                reason=f"price moved {_PARTIAL_CLOSE_1_ATR}×ATR; close first partial, trail SL",
            )

        # Rule 1: 1× ATR in favour → move SL to breakeven
        if favour_distance >= _BREAKEVEN_ATR_MULTIPLE * atr and not pos.breakeven_moved:
            pos.breakeven_moved = True
            pos.current_stop_loss = pos.entry_price
            return ManagementAction(
                action="move_breakeven",
                new_stop_loss=pos.entry_price,
                reason=f"price moved {_BREAKEVEN_ATR_MULTIPLE}×ATR; moving SL to breakeven",
            )

        # Trailing stop for positions already past partial_1
        if pos.partial_1_done:
            trail_distance = atr * (0.5 if pos.partial_2_done else 1.0)
            new_sl = (
                current_price - trail_distance
                if is_long
                else current_price + trail_distance
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

        pos = self._positions.get(position_id)
        if pos is None:
            logger.warning("close_position_not_found", position_id=str(position_id))
            return False

        close_qty = round(pos.quantity * (partial_pct / 100.0), 2)
        if close_qty <= 0:
            close_qty = 0.01

        connection_id = pos.broker_connection_id
        if connection_id is None:
            logger.error("no_broker_connection_for_position", position_id=str(position_id))
            return False

        side = OrderSide.SELL if pos.direction == "long" else OrderSide.BUY
        result = await self._broker_gateway.place_order(
            connection_id=connection_id,
            symbol=pos.symbol,
            side=side.value,
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

        logger.info(
            "position_closed",
            position_id=str(position_id),
            partial_pct=partial_pct,
            close_qty=close_qty,
            reason=reason,
        )

        if partial_pct >= 100.0:
            self._positions.pop(position_id, None)
            order = self._active_orders.pop(position_id, None)
            if order:
                order.status = OrderStatus.FILLED
                self._order_history.append(order)
        else:
            pos.quantity = round(pos.quantity - close_qty, 2)

        return True

    async def emergency_close_all(self, reason: str) -> dict[str, Any]:
        logger.critical("emergency_close_all", reason=reason, positions=len(self._positions))
        results: dict[str, Any] = {"reason": reason, "closed": [], "failed": []}

        for position_id in list(self._positions.keys()):
            success = await self.close_position(position_id, reason=reason, partial_pct=100.0)
            key = str(position_id)
            if success:
                results["closed"].append(key)
            else:
                results["failed"].append(key)

        return results

    def _calculate_position_size(
        self,
        symbol: str,
        account_balance: float,
        risk_pct: float,
        stop_loss_pips: float,
        pip_value: float,
    ) -> float:
        """
        Fixed-fractional position sizing.

        Returns lot count (standard lots) to risk exactly risk_pct% of
        account_balance given stop_loss_pips and pip_value per lot.
        """
        if account_balance <= 0 or risk_pct <= 0 or stop_loss_pips <= 0 or pip_value <= 0:
            logger.warning(
                "position_size_invalid_inputs",
                symbol=symbol,
                account_balance=account_balance,
                risk_pct=risk_pct,
                stop_loss_pips=stop_loss_pips,
                pip_value=pip_value,
            )
            return 0.01

        risk_amount = account_balance * (risk_pct / 100.0)
        lots = risk_amount / (stop_loss_pips * pip_value)
        return max(round(lots, 2), 0.01)

    # ─── Pre-trade checklist ─────────────────────────────────────────────────

    async def _run_pre_trade_checklist(
        self,
        signal: TradeSignal,
        broker_connection_id: UUID,
    ) -> str | None:
        """
        Run all pre-trade checks in priority order.

        Returns a rejection reason string if any check fails, else None.
        """

        # 1. Strategy validation
        strategy = self._strategy_engine.get_strategy(signal.strategy)
        if strategy is not None:
            validation = strategy.validate_signal(None, signal)
            if not validation.is_valid:
                return f"Strategy validation: {'; '.join(validation.errors)}"

        # 2. Session check
        if not self._allow_off_hours:
            now_hour = datetime.utcnow().hour
            if _OFF_HOURS_START_UTC <= now_hour or now_hour < _OFF_HOURS_END_UTC:
                return (
                    f"Off-hours trading blocked (UTC hour {now_hour}); "
                    f"set allow_off_hours=True to override"
                )

        # 3. Spread check
        spread_pips = signal.parameters.metadata.get("current_spread_pips")
        if spread_pips is not None and spread_pips > self._max_spread_pips:
            return (
                f"Spread {spread_pips:.1f} pips exceeds maximum {self._max_spread_pips:.1f} pips"
            )

        # 4. News filter
        news_rejection = self._check_news_blackout()
        if news_rejection:
            return news_rejection

        # 5. Correlation check (simple symbol-family grouping)
        correlated_count = self._count_correlated_positions(signal.symbol)
        if correlated_count >= _MAX_CORRELATED_POSITIONS:
            return (
                f"Too many correlated positions ({correlated_count}); "
                f"max is {_MAX_CORRELATED_POSITIONS}"
            )

        # 6. AI confidence threshold
        if signal.confidence < _MIN_AI_CONFIDENCE:
            return (
                f"AI confidence {signal.confidence:.2f} below threshold {_MIN_AI_CONFIDENCE:.2f}"
            )

        return None

    def _check_news_blackout(self) -> str | None:
        now = datetime.utcnow()
        window = timedelta(minutes=_NEWS_BLACKOUT_MINUTES)
        for event_time in self._news_events:
            if abs((now - event_time).total_seconds()) <= window.total_seconds():
                return (
                    f"News blackout active; high-impact event at {event_time.isoformat()} UTC"
                )
        return None

    def _count_correlated_positions(self, symbol: str) -> int:
        """
        Count open positions in the same currency group as symbol.

        Groups are determined by the base or quote currency appearing in
        the symbol string (e.g. EUR appears in EURUSD, EURGBP, EURJPY).
        """
        if len(symbol) < 6:
            return 0
        base = symbol[:3].upper()
        quote = symbol[3:6].upper()
        count = 0
        for pos in self._positions.values():
            s = pos.symbol.upper()
            if len(s) >= 6 and (s[:3] in (base, quote) or s[3:6] in (base, quote)):
                count += 1
        return count

    def add_news_event(self, event_time: datetime) -> None:
        """Register a high-impact news event for the blackout filter."""
        self._news_events.append(event_time)

    def clear_news_events(self) -> None:
        self._news_events.clear()

    # ─── Compatibility surface for legacy callers ─────────────────────────────

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
        self._pending_orders[order.order_id] = order
        logger.info(
            "order_created",
            order_id=str(order.order_id),
            symbol=symbol,
            side=side.value,
            type=order_type.value,
            quantity=quantity,
        )
        return order

    async def submit_order(self, order: Order) -> OrderResult:
        validation = self._validate_order(order)
        if not validation["valid"]:
            order.status = OrderStatus.REJECTED
            order.metadata["rejection_reason"] = validation["reason"]
            return OrderResult(
                success=False,
                order=order,
                message=validation["reason"],
                error_code="VALIDATION_FAILED",
            )
        self._pending_orders.pop(order.order_id, None)
        self._active_orders[order.order_id] = order
        order.status = OrderStatus.NEW
        order.updated_at = datetime.utcnow()
        logger.info("order_submitted", order_id=str(order.order_id), symbol=order.symbol)
        return OrderResult(success=True, order=order, message="Order submitted successfully")

    async def cancel_order(self, order_id: UUID) -> OrderResult:
        order = self._active_orders.get(order_id) or self._pending_orders.get(order_id)
        if not order:
            return OrderResult(
                success=False,
                order=Order(order_id=order_id),
                message="Order not found",
                error_code="NOT_FOUND",
            )
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.utcnow()
        self._pending_orders.pop(order_id, None)
        self._active_orders.pop(order_id, None)
        self._order_history.append(order)
        logger.info("order_cancelled", order_id=str(order_id))
        return OrderResult(success=True, order=order, message="Order cancelled")

    async def modify_order(
        self,
        order_id: UUID,
        quantity: float | None = None,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        order = self._active_orders.get(order_id) or self._pending_orders.get(order_id)
        if not order:
            return OrderResult(
                success=False,
                order=Order(order_id=order_id),
                message="Order not found",
                error_code="NOT_FOUND",
            )
        if quantity is not None:
            order.quantity = quantity
        if price is not None:
            order.price = price
        if stop_loss is not None:
            order.stop_loss = stop_loss
        if take_profit is not None:
            order.take_profit = take_profit
        order.updated_at = datetime.utcnow()
        logger.info("order_modified", order_id=str(order_id))
        return OrderResult(success=True, order=order, message="Order modified")

    async def on_fill(self, order_id: UUID, fill: Fill) -> None:
        order = self._active_orders.get(order_id)
        if not order:
            logger.warning("fill_received_unknown_order", order_id=str(order_id))
            return
        order.filled_quantity += fill.quantity
        order.filled_price = fill.price
        order.commission += fill.commission
        if order.filled_quantity >= order.quantity:
            order.status = OrderStatus.FILLED
            self._active_orders.pop(order_id, None)
            self._order_history.append(order)
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        order.updated_at = datetime.utcnow()
        logger.info(
            "order_filled",
            order_id=str(order_id),
            filled_qty=fill.quantity,
            fill_price=fill.price,
            status=order.status.value,
        )

    def get_order(self, order_id: UUID) -> Order | None:
        return (
            self._active_orders.get(order_id)
            or self._pending_orders.get(order_id)
            or next((o for o in self._order_history if o.order_id == order_id), None)
        )

    def get_active_orders(self, broker_account_id: UUID | None = None) -> list[Order]:
        orders = list(self._active_orders.values())
        if broker_account_id:
            orders = [o for o in orders if o.broker_account_id == broker_account_id]
        return orders

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
            return {"valid": False, "reason": "Both price and stop price required for stop-limit orders"}
        return {"valid": True, "reason": ""}
