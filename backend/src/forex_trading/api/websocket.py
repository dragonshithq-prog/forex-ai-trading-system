"""WebSocket endpoints for real-time data - pub/sub ConnectionManager."""

import asyncio
import json
import uuid
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import structlog

from forex_trading.core.security import security_manager

logger = structlog.get_logger()

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """
    Manages WebSocket connections with a pub/sub model.

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

    async def connect(self, websocket: WebSocket, user_id: str) -> str:
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        self._connections[connection_id] = websocket
        self._conn_user[connection_id] = user_id
        self._user_conns[user_id].add(connection_id)
        logger.info("ws_connected", connection_id=connection_id, user_id=user_id)
        return connection_id

    async def disconnect(self, connection_id: str) -> None:
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
        logger.info("ws_disconnected", connection_id=connection_id, user_id=user_id)

    async def subscribe(self, connection_id: str, channel: str, params: dict) -> None:
        if channel == "ticks":
            symbols: list[str] = [s.upper() for s in params.get("symbols", [])]
            if not symbols:
                return
            existing: set[str] = self._conn_params[connection_id].get("ticks_symbols", set())
            existing.update(symbols)
            self._conn_params[connection_id]["ticks_symbols"] = existing
        self._channel_subs[channel].add(connection_id)
        self._conn_channels[connection_id].add(channel)
        logger.debug("ws_subscribed", connection_id=connection_id, channel=channel, params=params)

    async def unsubscribe(self, connection_id: str, channel: str, params: dict) -> None:
        if channel == "ticks":
            symbols: list[str] = [s.upper() for s in params.get("symbols", [])]
            existing: set[str] = self._conn_params[connection_id].get("ticks_symbols", set())
            existing -= set(symbols)
            if not existing:
                self._channel_subs[channel].discard(connection_id)
                self._conn_channels[connection_id].discard(channel)
            self._conn_params[connection_id]["ticks_symbols"] = existing
        else:
            self._channel_subs[channel].discard(connection_id)
            self._conn_channels[connection_id].discard(channel)

    async def broadcast_to_channel(self, channel: str, message: dict) -> None:
        dead: list[str] = []
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
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(message)
            except Exception as exc:
                logger.warning("ws_send_failed", connection_id=conn_id, error=str(exc))
                dead.append(conn_id)

        for conn_id in dead:
            await self.disconnect(conn_id)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        for conn_id in list(self._user_conns.get(user_id, set())):
            await self.send_to_connection(conn_id, message)

    async def send_to_connection(self, connection_id: str, message: dict) -> None:
        websocket = self._connections.get(connection_id)
        if websocket is None:
            return
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(message)
        except Exception as exc:
            logger.warning("ws_send_failed", connection_id=connection_id, error=str(exc))
            await self.disconnect(connection_id)

    @property
    def active_connection_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


def _validate_ws_token(token: str) -> str | None:
    payload = security_manager.decode_token(token)
    return payload.sub if payload else None


async def _handle_client_message(
    connection_id: str,
    raw: str,
    websocket: WebSocket,
) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
        return

    action = msg.get("action")
    channel = msg.get("channel", "")
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
    else:
        await websocket.send_json({"type": "error", "detail": f"Unknown action '{action}'"})


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
# ---------------------------------------------------------------------------

@router.websocket("/ws/market/{symbol}")
async def market_data_websocket(websocket: WebSocket, symbol: str) -> None:
    connection_id = await manager.connect(websocket, user_id="anonymous")
    await manager.subscribe(connection_id, "ticks", {"symbols": [symbol]})
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": f"market:{symbol.upper()}",
            "message": f"Connected to {symbol.upper()} market data",
        })
        while True:
            raw = await websocket.receive_text()
            await _handle_client_message(connection_id, raw, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(connection_id)


@router.websocket("/ws/orders/{account_id}")
async def orders_websocket(websocket: WebSocket, account_id: str) -> None:
    connection_id = await manager.connect(websocket, user_id=account_id)
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
async def positions_websocket(websocket: WebSocket, account_id: str) -> None:
    connection_id = await manager.connect(websocket, user_id=account_id)
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
async def signals_websocket(websocket: WebSocket) -> None:
    connection_id = await manager.connect(websocket, user_id="anonymous")
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
async def alerts_websocket(websocket: WebSocket) -> None:
    connection_id = await manager.connect(websocket, user_id="anonymous")
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
async def dashboard_websocket(websocket: WebSocket) -> None:
    connection_id = await manager.connect(websocket, user_id="anonymous")
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
