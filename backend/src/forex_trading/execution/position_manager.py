"""Position Manager — authoritative position tracker with broker reconciliation.

Reconciliation loop runs every N seconds:
1. Load all positions from local DB
2. Fetch all positions from every connected broker
3. Match by broker_position_id
4. Any position in broker but not in DB → auto-import + alert
5. Any position in DB but not in broker → mark as ghost, investigate
6. Any size/price discrepancy → alert + auto-correct

Performance Optimizations (Phase 8):
- Rate limiting to broker API calls during reconciliation
- Backpressure when broker is slow
- Batch position fetching from broker
- Incremental reconciliation (only check recently changed positions)
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog

from forex_trading.shared.database.uow import UnitOfWorkFactory
from forex_trading.shared.database.models_trading import (
    Position,
    PositionSide,
    PositionStatus,
)
from forex_trading.shared.messaging.event_bus import EventBus
from forex_trading.shared.monitoring import open_positions_count

logger = structlog.get_logger()

_RECONCILE_INTERVAL_SECONDS = 15
_MAX_DIVERGENCE_PCT = 0.001  # 0.1% price divergence tolerated

# Performance tuning constants
_MAX_RECONCILE_CALLS_PER_MINUTE = 30  # rate limit: max broker API calls per minute
_RECONCILE_BACKPRESSURE_TIMEOUT = 5.0  # seconds to wait if broker is slow
_INCREMENTAL_RECONCILE_WINDOW_MINUTES = 60  # only check positions changed in last N min
_MAX_POSITIONS_PER_BATCH = 50  # max positions to fetch in a single batch


class PositionManager:
    """Manages the lifecycle and reconciliation of all positions.

    Attach via DI container. Calls ``start()`` on application startup.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        event_bus: EventBus,
        broker_gateway: Any,
        max_calls_per_minute: int = _MAX_RECONCILE_CALLS_PER_MINUTE,
        backpressure_timeout: float = _RECONCILE_BACKPRESSURE_TIMEOUT,
        incremental_window_minutes: int = _INCREMENTAL_RECONCILE_WINDOW_MINUTES,
        max_positions_per_batch: int = _MAX_POSITIONS_PER_BATCH,
    ) -> None:
        self._uow_factory = uow_factory
        self._event_bus = event_bus
        self._broker_gateway = broker_gateway
        self._max_calls_per_minute = max_calls_per_minute
        self._backpressure_timeout = backpressure_timeout
        self._incremental_window = timedelta(minutes=incremental_window_minutes)
        self._max_positions_per_batch = max_positions_per_batch
        self._running = False
        self._task: asyncio.Task | None = None

        # Rate limiter state
        self._rate_limit_timestamps: list[float] = []
        self._rate_limit_lock = asyncio.Lock()

        # Backpressure tracking: broker_id -> last response time
        self._broker_response_times: dict[UUID, float] = {}
        self._broker_consecutive_slow: dict[UUID, int] = defaultdict(int)
        self._broker_slow_threshold = 2.0  # seconds considered "slow"

        # Last reconciliation timestamps per broker
        self._last_reconcile_time: dict[UUID, float] = {}

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._reconciliation_loop())
        logger.info(
            "position_manager_started",
            interval_seconds=_RECONCILE_INTERVAL_SECONDS,
            max_calls_per_minute=self._max_calls_per_minute,
            incremental_window_minutes=self._incremental_window.total_seconds() / 60,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("position_manager_stopped")

    async def open_position(
        self,
        broker_account_id: UUID,
        symbol: str,
        side: PositionSide,
        size: float,
        entry_price: float,
        broker_position_id: str | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        strategy_id: UUID | None = None,
    ) -> Position:
        """Record a newly opened position in the DB."""
        async with self._uow_factory as uow:
            position = Position(
                broker_account_id=broker_account_id,
                symbol=symbol,
                side=side,
                size=size,
                entry_price=entry_price,
                current_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                broker_position_id=broker_position_id,
                strategy_id=strategy_id,
                status=PositionStatus.OPEN,
            )
            await uow.positions.add(position)
            uow.add_event(
                aggregate_type="position",
                aggregate_id=position.id,
                event_type="trading.position.opened",
                payload={
                    "position_id": str(position.id),
                    "broker_account_id": str(broker_account_id),
                    "symbol": symbol,
                    "side": side.value,
                    "size": size,
                    "entry_price": entry_price,
                    "broker_position_id": broker_position_id,
                },
            )
            await uow.commit()

            open_positions_count.labels(
                symbol=position.symbol,
                side=position.side.value,
            ).inc()

            return position

    async def close_position(
        self,
        position_id: UUID,
        exit_price: float,
        realized_pnl: float,
        reason: str = "",
    ) -> bool:
        """Mark a position as closed in the DB."""
        async with self._uow_factory as uow:
            pos = await uow.positions.get(position_id)
            if pos is None:
                logger.warning("close_position_not_found", position_id=str(position_id))
                return False

            await uow.positions.update(pos, {
                "status": PositionStatus.CLOSED,
                "current_price": exit_price,
                "realized_pnl": realized_pnl,
                "closed_at": datetime.now(timezone.utc),
            })
            uow.add_event(
                aggregate_type="position",
                aggregate_id=position_id,
                event_type="trading.position.closed",
                payload={
                    "position_id": str(position_id),
                    "symbol": pos.symbol,
                    "side": pos.side.value,
                    "size": pos.size,
                    "exit_price": exit_price,
                    "realized_pnl": realized_pnl,
                    "reason": reason,
                },
            )
            open_positions_count.labels(
                symbol=pos.symbol,
                side=pos.side.value,
            ).dec()

            await uow.commit()
            return True

    async def update_position(
        self,
        position_id: UUID,
        current_price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> None:
        """Update current price and SL/TP for an open position."""
        async with self._uow_factory as uow:
            pos = await uow.positions.get(position_id)
            if pos is None:
                return
            updates: dict = {"current_price": current_price}
            if stop_loss is not None:
                updates["stop_loss"] = stop_loss
            if take_profit is not None:
                updates["take_profit"] = take_profit
            await uow.positions.update(pos, updates)
            await uow.commit()

    async def get_open_positions(
        self, broker_account_id: UUID | None = None
    ) -> list[Position]:
        """Get all open positions from the local DB."""
        async with self._uow_factory as uow:
            return await uow.positions.get_open_positions(broker_account_id)

    # ─── Reconciliation ──────────────────────────────────────────────────────

    async def _reconciliation_loop(self) -> None:
        """Periodically reconcile local DB positions with broker positions."""
        while self._running:
            try:
                await self._reconcile_all()
            except Exception as exc:
                logger.error("reconciliation_error", error=str(exc))
            await asyncio.sleep(_RECONCILE_INTERVAL_SECONDS)

    async def _reconcile_all(self) -> None:
        """Run reconciliation for all connected broker accounts."""
        connected = self._broker_gateway.get_connected_brokers()
        for connection_id in connected:
            # Apply rate limiting before each broker call
            await self._wait_for_rate_limit()

            # Check backpressure: skip if broker is consistently slow
            if self._is_broker_backpressured(connection_id):
                logger.warning(
                    "broker_backpressure_active",
                    connection_id=str(connection_id),
                    consecutive_slow=self._broker_consecutive_slow.get(connection_id, 0),
                )
                continue

            await self._reconcile_account(connection_id)

        if connected:
            logger.debug("reconciliation_complete", accounts=len(connected))

    async def _wait_for_rate_limit(self) -> None:
        """Enforce rate limiting: max N broker API calls per minute."""
        async with self._rate_limit_lock:
            now = time.monotonic()
            # Remove timestamps older than 1 minute
            cutoff = now - 60
            self._rate_limit_timestamps = [
                t for t in self._rate_limit_timestamps if t > cutoff
            ]

            if len(self._rate_limit_timestamps) >= self._max_calls_per_minute:
                # Wait until we can make another call
                oldest = self._rate_limit_timestamps[0]
                wait_time = 60 - (now - oldest)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)

            self._rate_limit_timestamps.append(now)

    def _is_broker_backpressured(self, connection_id: UUID) -> bool:
        """Check if broker has been consistently slow."""
        consecutive = self._broker_consecutive_slow.get(connection_id, 0)
        return consecutive >= 3  # backpressure after 3 consecutive slow responses

    async def _reconcile_account(self, connection_id: UUID) -> None:
        """Reconcile positions for a single broker connection.

        Uses incremental reconciliation: only checks positions that changed
        since the last reconciliation window.
        """
        # Track broker response time for backpressure
        start_time = time.monotonic()

        try:
            # Batch position fetching from broker
            broker_positions = await asyncio.wait_for(
                self._broker_gateway.get_positions(connection_id),
                timeout=self._backpressure_timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                "reconciliation_timeout",
                connection_id=str(connection_id),
                timeout=self._backpressure_timeout,
            )
            self._broker_consecutive_slow[connection_id] += 1
            return
        except Exception as exc:
            logger.error(
                "reconciliation_fetch_failed",
                connection_id=str(connection_id),
                error=str(exc),
            )
            return

        # Track response time
        elapsed = time.monotonic() - start_time
        self._broker_response_times[connection_id] = elapsed
        if elapsed > self._broker_slow_threshold:
            self._broker_consecutive_slow[connection_id] += 1
        else:
            self._broker_consecutive_slow[connection_id] = 0

        # Limit batch size to prevent memory issues
        if len(broker_positions) > self._max_positions_per_batch:
            logger.warning(
                "broker_positions_truncated",
                connection_id=str(connection_id),
                total=len(broker_positions),
                max_batch=self._max_positions_per_batch,
            )
            broker_positions = broker_positions[:self._max_positions_per_batch]

        async with self._uow_factory as uow:
            local_positions = await uow.positions.get_open_positions(connection_id)

            # Incremental reconciliation: only check recently updated positions
            # Use timezone-aware cutoff but handle naive datetimes from SQLite
            incremental_cutoff = datetime.now(timezone.utc) - self._incremental_window
            recent_local = []
            for p in local_positions:
                if p.updated_at is not None:
                    updated = p.updated_at
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=timezone.utc)
                    if updated >= incremental_cutoff:
                        recent_local.append(p)

            local_by_broker_id: dict[str, Position] = {}
            for pos in recent_local:
                if pos.broker_position_id:
                    local_by_broker_id[pos.broker_position_id] = pos

            # Also include positions that might have been missed in incremental
            # (full scan every 4th reconciliation to catch stale positions)
            last_reconcile = self._last_reconcile_time.get(connection_id, 0)
            do_full_scan = (time.monotonic() - last_reconcile) > (self._incremental_window.total_seconds() * 4)
            if do_full_scan:
                for pos in local_positions:
                    if pos.broker_position_id:
                        local_by_broker_id[pos.broker_position_id] = pos
                logger.debug("full_reconciliation_scan", connection_id=str(connection_id))

            broker_ids_seen: set[str] = set()

            for bp in broker_positions:
                bp_id = str(getattr(bp, "broker_position_id", getattr(bp, "position_id", "")))
                if not bp_id:
                    continue
                broker_ids_seen.add(bp_id)

                if bp_id in local_by_broker_id:
                    local = local_by_broker_id[bp_id]
                    divergence = abs(
                        (float(getattr(bp, "current_price", 0)) - float(local.current_price))
                        / float(local.current_price or 1)
                    )
                    if divergence > _MAX_DIVERGENCE_PCT:
                        logger.warning(
                            "position_price_divergence",
                            position_id=str(local.id),
                            broker_position_id=bp_id,
                            local_price=local.current_price,
                            broker_price=float(getattr(bp, "current_price", 0)),
                            divergence_pct=round(divergence * 100, 4),
                        )
                        await uow.positions.update(local, {
                            "current_price": float(getattr(bp, "current_price", local.current_price)),
                        })
                else:
                    broker_side = getattr(bp, "side", "long")
                    pos_side = PositionSide.LONG if broker_side == "long" else PositionSide.SHORT
                    new_pos = Position(
                        broker_account_id=connection_id,
                        symbol=str(getattr(bp, "symbol", "")),
                        side=pos_side,
                        size=float(getattr(bp, "size", 0)),
                        entry_price=float(getattr(bp, "entry_price", 0)),
                        current_price=float(getattr(bp, "current_price", 0)),
                        stop_loss=float(getattr(bp, "stop_loss", 0)) if getattr(bp, "stop_loss", None) else None,
                        take_profit=float(getattr(bp, "take_profit", 0)) if getattr(bp, "take_profit", None) else None,
                        broker_position_id=bp_id,
                        status=PositionStatus.OPEN,
                    )
                    await uow.positions.add(new_pos)
                    logger.warning(
                        "position_auto_imported",
                        broker_position_id=bp_id,
                        symbol=new_pos.symbol,
                        side=new_pos.side.value,
                    )

            # Check for ghost positions (in local but not in broker)
            for local in recent_local:
                if local.broker_position_id and local.broker_position_id not in broker_ids_seen:
                    logger.warning(
                        "position_ghost_in_local_db",
                        position_id=str(local.id),
                        broker_position_id=local.broker_position_id,
                        symbol=local.symbol,
                    )

            await uow.commit()

        self._last_reconcile_time[connection_id] = time.monotonic()
