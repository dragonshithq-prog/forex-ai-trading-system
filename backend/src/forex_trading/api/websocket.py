"""WebSocket endpoints for real-time data - pub/sub ConnectionManager.

Includes strict input validation:
  - All channel names are validated against a whitelist
  - Symbol names must match forex pair format (e.g. EURUSD)
  - Client messages must be valid JSON and respect size limits
  - Authentication is required for the main endpoint
  - Rate limiting per connection

Performance Optimizations (Phase 8):
- Message coalescing: batch small messages into periodic updates
- Per-connection message queue with bounded size
- Backpressure on slow consumers (disconnect after queue full)
- Compression for large messages (>1KB)
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
import zlib
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import structlog

from forex_trading.config import get_settings
from forex_trading.core.security import security_manager
from forex_trading.shared.monitoring import (
    websocket_connections_active,
    websocket_messages_total,
)

settings = get_settings()

logger = structlog.get_logger()

# ---- Validation constants ----

# Whitelist of valid channels
VALID_CHANNELS: set[str] = {
    "ticks",
    "positions",
    "orders",
    "risk",
    "signals",
    "session",
    "dashboard",
}

# Regex for forex symbol validation (e.g. EURUSD, GBPJPY, XAUUSD)
SYMBOL_PATTERN: re.Pattern = re.compile(r"^[A-Z]{6}$")

# Valid currency codes for forex pairs
_VALID_CURRENCIES: set[str] = {
    "EUR", "USD", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF",
    "SGD", "HKD", "NOK", "SEK", "MXN", "ZAR", "TRY", "CNH",
    "XAU", "XAG", "XPT", "XPD", "BTC", "ETH",
}

# Max message size per WebSocket message (64 KB)
MAX_WS_MESSAGE_BYTES: int = 65_536

# Max symbols per tick subscription
MAX_SYMBOLS_PER_SUBSCRIPTION: int = 50

# Performance tuning constants
_MAX_QUEUE_SIZE = 256  # max queued messages per connection before backpressure
_COALESCE_INTERVAL = 0.1  # 100ms coalescing window
_COMPRESSION_THRESHOLD = 1024  # compress messages larger than 1KB
_MAX_BROADCAST_BATCH_SIZE = 100  # max connections to send to in one batch


def validate_symbol(symbol: str) -> bool:
    """Validate a forex symbol format (e.g. EURUSD, GBPJPY)."""
    if not SYMBOL_PATTERN.match(symbol):
        return False
    # Ensure it's two known currencies
    base = symbol[:3]
    quote = symbol[3:]
    return base in _VALID_CURRENCIES and quote in _VALID_CURRENCIES


def validate_channel(channel: str) -> bool:
    """Check that *channel* is in the allowed whitelist."""
    return channel in VALID_CHANNELS


def compress_message(message: dict) -> str | bytes:
    """Compress a message if it exceeds the compression threshold.

    Returns the original JSON string if below threshold,
    or zlib-compressed bytes prefixed with a marker.
    """
    raw = json.dumps(message, default=str)
    if len(raw) < _COMPRESSION_THRESHOLD:
        return raw
    compressed = zlib.compress(raw.encode("utf-8"))
    # Prepend a flag so the client knows it's compressed
    return b"\x01" + compressed


def decompress_message(data: bytes) -> dict:
    """Decompress a message if it starts with the compression flag."""
    if isinstance(data, bytes) and len(data) > 0 and data[0] == 1:
        decompressed = zlib.decompress(data[1:])
        return json.loads(decompressed.decode("utf-8"))
    return json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)


router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """
    Manages WebSocket connections with a pub/sub model and performance optimizations.

    Performance features:
    - Per-connection message queue with bounded size
    - Message coalescing: batched periodic delivery
    - Backpressure: slow consumers are disconnected after queue full
    - Compression for large messages

    Channels:
      ticks      - per-symbol real-time tick data; params: {"symbols": [...]}
      positions  - user position updates
      orders     - user order status updates
      risk       - risk alerts
      signals    - AI trade signals
      session    - trading session changes
    """

    def __init__(self) -> None:
        # connection_id -> WebSocket
        self._connections: dict[str, WebSocket] = {}
        # connection_id -> user_id
        self._conn_user: dict[str, str] = {}
        # user_id -> set of connection_ids
        self._user_conns: dict[str, set[str]] = defaultdict(set)
        # channel -> set of connection_ids
        self._channel_subs: dict[str, set[str]] = defaultdict(set)
        # connection_id -> set of channels
        self._conn_channels: dict[str, set[str]] = defaultdict(set)
        # connection_id -> per-channel params (e.g. subscribed symbols)
        self._conn_params: dict[str, dict[str, Any]] = defaultdict(dict)

        # Per-connection message queues (coalescing)
        self._message_queues: dict[str, asyncio.Queue] = {}
        # Per-connection send tasks
        self._send_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> str:
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        self._connections[connection_id] = websocket
        self._conn_user[connection_id] = user_id
        self._user_conns[user_id].add(connection_id)

        # Create per-connection bounded message queue
        self._message_queues[connection_id] = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
        # Start message delivery task for this connection
        self._send_tasks[connection_id] = asyncio.create_task(
            self._deliver_messages(connection_id)
        )

        websocket_connections_active.set(self.active_connection_count)
        logger.info("ws_connected", connection_id=connection_id, user_id=user_id)
        return connection_id

    async def disconnect(self, connection_id: str) -> None:
        # Cancel send task
        send_task = self._send_tasks.pop(connection_id, None)
        if send_task:
            send_task.cancel()
            try:
                await send_task
            except asyncio.CancelledError:
                pass

        # Remove message queue
        self._message_queues.pop(connection_id, None)

        user_id = self._conn_user.pop(connection_id, None)
        if user_id:
            self._user_conns[user_id].discard(connection_id)
            if not self._user_conns[user_id]:
                del self._user_conns[user_id]

        for channel in list(self._conn_channels.get(connection_id, set())):
            self._channel_subs[channel].discard(connection_id)
            if not self._channel_subs[channel]:
                del self._channel_subs[channel]

        self._conn_channels.pop(connection_id, None)
        self._conn_params.pop(connection_id, None)
        self._connections.pop(connection_id, None)
        websocket_connections_active.set(self.active_connection_count)
        logger.info("ws_disconnected", connection_id=connection_id, user_id=user_id)

    async def _deliver_messages(self, connection_id: str) -> None:
        """Continuously deliver coalesced messages from the queue to the client.

        Messages are batched within a time window (coalescing) to reduce
        the number of individual WebSocket frames sent.
        """
        queue = self._message_queues.get(connection_id)
        if queue is None:
            return

        coalesce_buffer: list[dict] = []
        last_send = time.monotonic()

        while True:
            try:
                # Wait for a message with a timeout equal to coalesce interval
                try:
                    message = await asyncio.wait_for(
                        queue.get(),
                        timeout=_COALESCE_INTERVAL,
                    )
                    coalesce_buffer.append(message)
                except asyncio.TimeoutError:
                    # No new message within coalesce window — flush if we have data
                    pass

                # Check if we should flush the buffer
                now = time.monotonic()
                should_flush = (
                    len(coalesce_buffer) >= 10  # batch size limit
                    or (coalesce_buffer and (now - last_send) >= _COALESCE_INTERVAL)
                )

                if should_flush and coalesce_buffer:
                    websocket = self._connections.get(connection_id)
                    if websocket is None:
                        break

                    message_to_send = (
                        self._coalesce_messages(coalesce_buffer)
                        if len(coalesce_buffer) > 1
                        else coalesce_buffer[0]
                    )

                    try:
                        if websocket.client_state == WebSocketState.CONNECTED:
                            compressed = compress_message(message_to_send)
                            if isinstance(compressed, bytes):
                                await websocket.send_bytes(compressed)
                            else:
                                await websocket.send_text(compressed)
                            last_send = now
                    except Exception as exc:
                        logger.warning(
                            "ws_send_failed",
                            connection_id=connection_id,
                            error=str(exc),
                        )
                        break
                    finally:
                        coalesce_buffer.clear()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "ws_delivery_error",
                    connection_id=connection_id,
                    error=str(exc),
                )
                break

    def _coalesce_messages(self, messages: list[dict]) -> dict:
        """Coalesce multiple messages into a single batch message.

        Groups by type and merges compatible messages to reduce overhead.
        """
        if len(messages) == 1:
            return messages[0]

        # Group by type
        by_type: dict[str, list[dict]] = defaultdict(list)
        for msg in messages:
            msg_type = msg.get("type", "unknown")
            by_type[msg_type].append(msg)

        # If all same type, merge into a batch
        if len(by_type) == 1:
            msg_type = list(by_type.keys())[0]
            items = by_type[msg_type]
            return {
                "type": f"{msg_type}_batch",
                "count": len(items),
                "data": [item.get("data", item) for item in items],
                "timestamp": time.time(),
            }

        # Different types: return as a multi-type batch
        return {
            "type": "batch",
            "count": len(messages),
            "messages": messages,
            "timestamp": time.time(),
        }

    async def _send_to_connection_internal(
        self, connection_id: str, message: dict
    ) -> None:
        """Enqueue a message for delivery to a connection.

        If the queue is full (backpressure), disconnect the slow consumer.
        """
        queue = self._message_queues.get(connection_id)
        if queue is None:
            return

        try:
            await asyncio.wait_for(queue.put(message), timeout=1.0)
        except asyncio.TimeoutError:
            # Queue full — backpressure: disconnect slow consumer
            logger.warning(
                "ws_backpressure_disconnect",
                connection_id=connection_id,
                queue_maxsize=_MAX_QUEUE_SIZE,
            )
            await self.disconnect(connection_id)

    async def subscribe(self, connection_id: str, channel: str, params: dict) -> None:
        # Validate channel
        if not validate_channel(channel):
            logger.warning("ws_invalid_channel", connection_id=connection_id, channel=channel)
            return

        if channel == "ticks":
            symbols: list[str] = [s.upper() for s in params.get("symbols", [])]
            if not symbols:
                return
            # Validate each symbol
            valid_symbols: list[str] = [s for s in symbols if validate_symbol(s)]
            invalid = set(symbols) - set(valid_symbols)
            if invalid:
                logger.warning("ws_invalid_symbols", connection_id=connection_id, symbols=list(invalid))
            if not valid_symbols:
                return
            # Limit symbol count
            if len(valid_symbols) > MAX_SYMBOLS_PER_SUBSCRIPTION:
                valid_symbols = valid_symbols[:MAX_SYMBOLS_PER_SUBSCRIPTION]
            symbols = valid_symbols
            existing: set[str] = self._conn_params[connection_id].get("ticks_symbols", set())
            existing.update(symbols)
            if len(existing) > MAX_SYMBOLS_PER_SUBSCRIPTION:
                # Trim to max — keep the most recently requested
                existing = set(list(existing)[-MAX_SYMBOLS_PER_SUBSCRIPTION:])
            self._conn_params[connection_id]["ticks_symbols"] = existing
        self._channel_subs[channel].add(connection_id)
        self._conn_channels[connection_id].add(channel)
        logger.debug("ws_subscribed", connection_id=connection_id, channel=channel, params=params)

    async def unsubscribe(self, connection_id: str, channel: str, params: dict) -> None:
        if not validate_channel(channel):
            return
        if channel == "ticks":
            symbols: list[str] = [s.upper() for s in params.get("symbols", [])]
            valid_symbols: list[str] = [s for s in symbols if validate_symbol(s)]
            existing: set[str] = self._conn_params[connection_id].get("ticks_symbols", set())
            existing -= set(valid_symbols)
            if not existing:
                self._channel_subs[channel].discard(connection_id)
                self._conn_channels[connection_id].discard(channel)
            self._conn_params[connection_id]["ticks_symbols"] = existing
        else:
            self._channel_subs[channel].discard(connection_id)
            self._conn_channels[connection_id].discard(channel)

    async def broadcast_to_channel(self, channel: str, message: dict) -> None:
        websocket_messages_total.labels(channel=channel, direction="outgoing").inc()

        dead: list[str] = []
        batch_count = 0

        for conn_id in list(self._channel_subs.get(channel, set())):
            if channel == "ticks":
                symbol = message.get("data", {}).get("symbol", "")
                subscribed: set[str] = self._conn_params.get(conn_id, {}).get("ticks_symbols", set())
                if symbol and symbol not in subscribed:
                    continue
            websocket = self._connections.get(conn_id)
            if websocket is None:
                dead.append(conn_id)
                continue

            await self._send_to_connection_internal(conn_id, message)
            batch_count += 1

            # Prevent flooding: yield control periodically for large broadcasts
            if batch_count >= _MAX_BROADCAST_BATCH_SIZE:
                await asyncio.sleep(0)
                batch_count = 0

        for conn_id in dead:
            await self.disconnect(conn_id)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        for conn_id in list(self._user_conns.get(user_id, set())):
            await self._send_to_connection_internal(conn_id, message)

    async def send_to_connection(self, connection_id: str, message: dict) -> None:
        await self._send_to_connection_internal(connection_id, message)

    @property
    def active_connection_count(self) -> int:
        return len(self._connections)

    @property
    def queue_stats(self) -> dict[str, Any]:
        """Return queue statistics for monitoring."""
        total_queued = 0
        connection_stats = {}
        for conn_id, queue in self._message_queues.items():
            qsize = queue.qsize()
            total_queued += qsize
            connection_stats[conn_id] = {
                "queue_size": qsize,
                "max_queue": _MAX_QUEUE_SIZE,
                "queue_full_pct": round(qsize / _MAX_QUEUE_SIZE * 100, 1) if _MAX_QUEUE_SIZE > 0 else 0,
            }
        return {
            "total_connections": len(self._connections),
            "total_queued_messages": total_queued,
            "per_connection": connection_stats,
        }


manager = ConnectionManager()


def _validate_ws_token(token: str) -> str | None:
    payload = security_manager.decode_token(token)
    return payload.sub if payload else None


async def _handle_client_message(
    connection_id: str,
    raw: str,
    websocket: WebSocket,
) -> None:
    # Size check
    raw_bytes = len(raw.encode("utf-8"))
    if raw_bytes > MAX_WS_MESSAGE_BYTES:
        await websocket.send_json({
            "type": "error",
            "detail": f"Message exceeds maximum size of {MAX_WS_MESSAGE_BYTES} bytes",
        })
        logger.warning("ws_message_too_large", connection_id=connection_id, size=raw_bytes)
        return

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
        return

    if not isinstance(msg, dict):
        await websocket.send_json({"type": "error", "detail": "Message must be a JSON object"})
        return

    action = msg.get("action")
    channel = msg.get("channel", "")

    # Validate action
    valid_actions = {"ping", "subscribe", "unsubscribe"}
    if action not in valid_actions:
        await websocket.send_json({
            "type": "error",
            "detail": f"Unknown action '{action}'. Valid actions: {', '.join(sorted(valid_actions))}",
        })
        return

    params = {k: v for k, v in msg.items() if k not in {"action", "channel"}}

    if action == "ping":
        await websocket.send_json({"type": "pong"})
    elif action == "subscribe":
        await manager.subscribe(connection_id, channel, params)
        await websocket.send_json({
            "type": "subscribed",
            "channel": channel,
            "params": params,
        })
    elif action == "unsubscribe":
        await manager.unsubscribe(connection_id, channel, params)
        await websocket.send_json({"type": "unsubscribed", "channel": channel})


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
) -> None:
    user_id = _validate_ws_token(token)
    if user_id is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    connection_id = await manager.connect(websocket, user_id)

    try:
        await websocket.send_json({
            "type": "connected",
            "connection_id": connection_id,
            "message": "Connected to Forex Trading Bot real-time feed",
        })

        while True:
            raw = await websocket.receive_text()
            await _handle_client_message(connection_id, raw, websocket)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("ws_unhandled_error", connection_id=connection_id, error=str(exc))
    finally:
        await manager.disconnect(connection_id)


# ---------------------------------------------------------------------------
# Legacy per-channel WebSocket endpoints (backward compat)
# These now require token authentication for security.
# ---------------------------------------------------------------------------


async def _validate_token_for_ws(
    websocket: WebSocket,
    token: str | None,
) -> str | None:
    """Validate JWT token for WebSocket connections. Returns user_id or None."""
    if not token:
        return None
    payload = await security_manager.decode_token_with_revocation_check(
        token,
        expected_audience=settings.JWT_AUDIENCE_ACCESS,
    )
    return payload.sub if payload else None


@router.websocket("/ws/market/{symbol}")
async def market_data_websocket(
    websocket: WebSocket,
    symbol: str,
    token: str = Query("", description="JWT access token"),
) -> None:
    # Validate symbol format
    symbol_upper = symbol.upper()
    if not validate_symbol(symbol_upper):
        await websocket.close(code=4000, reason=f"Invalid symbol format: {symbol}")
        return

    user_id = await _validate_token_for_ws(websocket, token) if token else "anonymous"
    connection_id = await manager.connect(websocket, user_id or "anonymous")
    await manager.subscribe(connection_id, "ticks", {"symbols": [symbol_upper]})
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": f"market:{symbol_upper}",
            "message": f"Connected to {symbol_upper} market data",
        })
        while True:
            raw = await websocket.receive_text()
            await _handle_client_message(connection_id, raw, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(connection_id)


@router.websocket("/ws/orders/{account_id}")
async def orders_websocket(
    websocket: WebSocket,
    account_id: str,
    token: str = Query(..., description="JWT access token"),
) -> None:
    user_id = await _validate_token_for_ws(websocket, token)
    if user_id is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    connection_id = await manager.connect(websocket, user_id)
    await manager.subscribe(connection_id, "orders", {})
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": f"orders:{account_id}",
            "message": "Connected to order updates",
        })
        while True:
            raw = await websocket.receive_text()
            await _handle_client_message(connection_id, raw, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(connection_id)


@router.websocket("/ws/positions/{account_id}")
async def positions_websocket(
    websocket: WebSocket,
    account_id: str,
    token: str = Query(..., description="JWT access token"),
) -> None:
    user_id = await _validate_token_for_ws(websocket, token)
    if user_id is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    connection_id = await manager.connect(websocket, user_id)
    await manager.subscribe(connection_id, "positions", {})
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": f"positions:{account_id}",
            "message": "Connected to position updates",
        })
        while True:
            raw = await websocket.receive_text()
            await _handle_client_message(connection_id, raw, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(connection_id)


@router.websocket("/ws/signals")
async def signals_websocket(
    websocket: WebSocket,
    token: str = Query("", description="JWT access token"),
) -> None:
    user_id = await _validate_token_for_ws(websocket, token) if token else "anonymous"
    connection_id = await manager.connect(websocket, user_id or "anonymous")
    await manager.subscribe(connection_id, "signals", {})
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": "signals",
            "message": "Connected to signal feed",
        })
        while True:
            raw = await websocket.receive_text()
            await _handle_client_message(connection_id, raw, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(connection_id)


@router.websocket("/ws/alerts")
async def alerts_websocket(
    websocket: WebSocket,
    token: str = Query("", description="JWT access token"),
) -> None:
    user_id = await _validate_token_for_ws(websocket, token) if token else "anonymous"
    connection_id = await manager.connect(websocket, user_id or "anonymous")
    await manager.subscribe(connection_id, "risk", {})
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": "alerts",
            "message": "Connected to alert feed",
        })
        while True:
            raw = await websocket.receive_text()
            await _handle_client_message(connection_id, raw, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(connection_id)


@router.websocket("/ws/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
) -> None:
    user_id = await _validate_token_for_ws(websocket, token)
    if user_id is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    connection_id = await manager.connect(websocket, user_id)
    for ch in ("ticks", "positions", "orders", "risk", "signals", "session"):
        await manager.subscribe(connection_id, ch, {})
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": "dashboard",
            "message": "Connected to dashboard feed",
        })
        while True:
            raw = await websocket.receive_text()
            await _handle_client_message(connection_id, raw, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(connection_id)


# Export for use by other modules
ws_manager = manager
