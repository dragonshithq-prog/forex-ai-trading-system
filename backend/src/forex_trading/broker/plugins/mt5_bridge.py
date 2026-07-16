"""MT5 broker bridge plugin - asyncio TCP client to MT5 EA bridge server."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import structlog

from forex_trading.broker.gateway import (
    AccountInfo,
    BrokerCredentials,
    BrokerPlugin,
    BrokerPosition,
    BrokerType,
    ConnectionStatus,
)

logger = structlog.get_logger()

_HEARTBEAT_INTERVAL = 30.0
_RECONNECT_DELAYS = [1, 2, 4, 8, 16]  # exponential backoff, 5 attempts
_READ_TIMEOUT = 10.0
_CONNECT_TIMEOUT = 5.0


class MT5BridgePlugin(BrokerPlugin):
    """MT5 bridge plugin connecting to an MT5 EA TCP server via JSON protocol."""

    def __init__(self) -> None:
        super().__init__(BrokerType.MT5)
        self._host: str = "127.0.0.1"
        self._port: int = 3001
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._reconnect_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._subscribed_symbols: set[str] = set()
        self._tick_callbacks: list[Any] = []

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, credentials: BrokerCredentials) -> bool:
        self._credentials = credentials
        self._host = credentials.host or "127.0.0.1"
        self._port = credentials.port or 3001
        self._status = ConnectionStatus.CONNECTING

        success = await self._open_connection()
        if success:
            self._start_heartbeat()
        return success

    async def _open_connection(self) -> bool:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=_CONNECT_TIMEOUT,
            )
            self._status = ConnectionStatus.CONNECTED
            logger.info("mt5_bridge_connected", host=self._host, port=self._port)
            return True
        except (OSError, asyncio.TimeoutError) as exc:
            self._status = ConnectionStatus.ERROR
            logger.error("mt5_bridge_connect_failed", host=self._host, port=self._port, error=str(exc))
            return False

    async def disconnect(self) -> None:
        await self._cancel_heartbeat()
        await self._cancel_reconnect()
        await self._close_connection()
        self._status = ConnectionStatus.DISCONNECTED
        logger.info("mt5_bridge_disconnected")

    async def _close_connection(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            self._writer = None
            self._reader = None

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def _start_heartbeat(self) -> None:
        loop = asyncio.get_event_loop()
        self._heartbeat_task = loop.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        while self._status == ConnectionStatus.CONNECTED:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            try:
                resp = await self._send_command({"cmd": "ping"})
                if resp.get("status") != "ok":
                    raise ConnectionError("heartbeat nack")
            except Exception as exc:  # noqa: BLE001
                logger.warning("mt5_heartbeat_failed", error=str(exc))
                if self._status == ConnectionStatus.CONNECTED:
                    asyncio.get_event_loop().create_task(self._auto_reconnect())
                return

    async def _cancel_heartbeat(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _cancel_reconnect(self) -> None:
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Auto-reconnect
    # ------------------------------------------------------------------

    async def _auto_reconnect(self) -> None:
        self._status = ConnectionStatus.CONNECTING
        await self._close_connection()
        await self._cancel_heartbeat()

        for attempt, delay in enumerate(_RECONNECT_DELAYS):
            logger.info("mt5_reconnecting", attempt=attempt + 1, delay=delay)
            await asyncio.sleep(delay)
            if await self._open_connection():
                self._start_heartbeat()
                if self._subscribed_symbols:
                    try:
                        await self.subscribe_market_data(list(self._subscribed_symbols))
                    except Exception:  # noqa: BLE001
                        pass
                return

        self._status = ConnectionStatus.ERROR
        logger.error("mt5_reconnect_exhausted", attempts=len(_RECONNECT_DELAYS))

    # ------------------------------------------------------------------
    # Low-level send/receive
    # ------------------------------------------------------------------

    async def _send_command(self, command: dict) -> dict:
        if self._reader is None or self._writer is None:
            raise ConnectionError("MT5 bridge not connected")

        async with self._lock:
            payload = (json.dumps(command) + "\n").encode()
            self._writer.write(payload)
            await self._writer.drain()

            try:
                line = await asyncio.wait_for(self._reader.readline(), timeout=_READ_TIMEOUT)
            except asyncio.TimeoutError as exc:
                raise TimeoutError("MT5 bridge read timeout") from exc

            if not line:
                raise ConnectionError("MT5 bridge connection closed")

            return json.loads(line.decode().strip())

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def subscribe_market_data(self, symbols: list[str]) -> None:
        self._subscribed_symbols.update(symbols)
        await self._send_command({"cmd": "subscribe", "symbols": symbols})
        logger.info("mt5_subscribed", symbols=symbols)

    async def unsubscribe_market_data(self, symbols: list[str]) -> None:
        self._subscribed_symbols -= set(symbols)
        await self._send_command({"cmd": "unsubscribe", "symbols": symbols})
        logger.info("mt5_unsubscribed", symbols=symbols)

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_account_info(self) -> AccountInfo:
        resp = await self._send_command({"cmd": "account_info"})
        _check_response(resp, "get_account_info")
        d = resp["data"]
        return _parse_account_info(d, BrokerType.MT5)

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[BrokerPosition]:
        resp = await self._send_command({"cmd": "positions"})
        _check_response(resp, "get_positions")
        return [_parse_mt5_position(p) for p in resp.get("data", [])]

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        cmd: dict[str, Any] = {
            "cmd": "place_order",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "order_type": order_type,
        }
        if price is not None:
            cmd["price"] = price
        if stop_loss is not None:
            cmd["stop_loss"] = stop_loss
        if take_profit is not None:
            cmd["take_profit"] = take_profit

        resp = await self._send_command(cmd)
        _check_response(resp, "place_order")
        logger.info("mt5_order_placed", symbol=symbol, side=side)
        return resp.get("data", {})

    async def modify_order(
        self,
        order_id: str,
        quantity: float | None = None,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> bool:
        cmd: dict[str, Any] = {"cmd": "modify_order", "ticket": order_id}
        if quantity is not None:
            cmd["quantity"] = quantity
        if price is not None:
            cmd["price"] = price
        if stop_loss is not None:
            cmd["stop_loss"] = stop_loss
        if take_profit is not None:
            cmd["take_profit"] = take_profit

        try:
            resp = await self._send_command(cmd)
            return resp.get("status") == "ok"
        except Exception as exc:
            logger.error("mt5_modify_order_failed", order_id=order_id, error=str(exc))
            return False

    async def cancel_order(self, order_id: str) -> bool:
        try:
            resp = await self._send_command({"cmd": "cancel_order", "ticket": order_id})
            return resp.get("status") == "ok"
        except Exception as exc:
            logger.error("mt5_cancel_order_failed", order_id=order_id, error=str(exc))
            return False

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "H1",
        count: int = 500,
    ) -> list[dict]:
        try:
            resp = await self._send_command({
                "cmd": "get_ohlcv",
                "symbol": symbol,
                "timeframe": timeframe,
                "count": count,
            })
            return resp.get("data", [])
        except Exception as exc:
            logger.error("mt5_get_ohlcv_failed", symbol=symbol, error=str(exc))
            return []

    async def get_order_history(self, since: datetime | None = None) -> list[dict]:
        cmd: dict[str, Any] = {"cmd": "history"}
        if since is not None:
            cmd["from"] = since.isoformat()
        resp = await self._send_command(cmd)
        _check_response(resp, "get_order_history")
        return resp.get("data", [])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _check_response(resp: dict, context: str) -> None:
    if resp.get("status") not in ("ok", None) and resp.get("error"):
        raise RuntimeError(f"MT bridge error [{context}]: {resp['error']}")


def _parse_account_info(d: dict, broker: BrokerType) -> AccountInfo:
    balance = float(d.get("balance", 0))
    equity = float(d.get("equity", balance))
    margin = float(d.get("margin", 0))
    free_margin = float(d.get("free_margin", equity - margin))
    margin_level = (equity / margin * 100) if margin > 0 else 0.0
    return AccountInfo(
        account_id=str(d.get("login", d.get("account_id", ""))),
        broker=broker,
        balance=balance,
        equity=equity,
        margin=margin,
        free_margin=free_margin,
        margin_level=margin_level,
        unrealized_pnl=float(d.get("profit", 0)),
        currency=str(d.get("currency", "USD")),
        leverage=int(d.get("leverage", 100)),
    )


def _parse_mt5_position(p: dict) -> BrokerPosition:
    side = "long" if int(p.get("type", 0)) == 0 else "short"
    return BrokerPosition(
        broker_position_id=str(p.get("ticket", p.get("id", ""))),
        symbol=str(p.get("symbol", "")),
        side=side,
        size=float(p.get("volume", p.get("size", 0))),
        entry_price=float(p.get("price_open", p.get("entry_price", 0))),
        current_price=float(p.get("price_current", p.get("current_price", 0))),
        unrealized_pnl=float(p.get("profit", 0)),
        stop_loss=_float_or_none(p.get("sl")),
        take_profit=_float_or_none(p.get("tp")),
        swap=float(p.get("swap", 0)),
        commission=float(p.get("commission", 0)),
    )


def _float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f != 0.0 else None
    except (TypeError, ValueError):
        return None
