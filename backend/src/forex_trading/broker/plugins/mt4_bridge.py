"""MT4 broker bridge plugin - asyncio TCP client to MT4 EA bridge server.

MT4 differences vs MT5:
- All positions are identified by integer ticket numbers (hedging mode only).
- No netting; every order open creates a distinct position ticket.
- ``type`` field: 0 = BUY, 1 = SELL.
"""

from __future__ import annotations

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
from forex_trading.broker.plugins.mt5_bridge import (
    MT5BridgePlugin,
    _check_response,
    _float_or_none,
    _parse_account_info,
)

logger = structlog.get_logger()


class MT4BridgePlugin(BrokerPlugin):
    """MT4 bridge plugin - ticket-based hedging mode, same JSON protocol as MT5."""

    def __init__(self) -> None:
        super().__init__(BrokerType.MT4)
        # Delegate all TCP mechanics to the MT5 plugin internals (same protocol)
        self._bridge = MT5BridgePlugin()
        # Expose the same asyncio structures through the delegate
        self._host: str = "127.0.0.1"
        self._port: int = 3000

    # ------------------------------------------------------------------
    # Proxy property so BrokerGateway status checks still work
    # ------------------------------------------------------------------

    @property
    def status(self) -> ConnectionStatus:
        return self._bridge.status

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, credentials: BrokerCredentials) -> bool:
        self._credentials = credentials
        self._host = credentials.host or "127.0.0.1"
        self._port = credentials.port or 3000
        # Patch host/port into a copy of credentials so the delegate uses MT4 port
        from dataclasses import replace
        creds_mt4 = replace(credentials, host=self._host, port=self._port)
        result = await self._bridge.connect(creds_mt4)
        if result:
            self._status = ConnectionStatus.CONNECTED
        return result

    async def disconnect(self) -> None:
        await self._bridge.disconnect()
        self._status = ConnectionStatus.DISCONNECTED

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def subscribe_market_data(self, symbols: list[str]) -> None:
        await self._bridge.subscribe_market_data(symbols)

    async def unsubscribe_market_data(self, symbols: list[str]) -> None:
        await self._bridge.unsubscribe_market_data(symbols)

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_account_info(self) -> AccountInfo:
        resp = await self._bridge._send_command({"cmd": "account_info"})
        _check_response(resp, "get_account_info")
        return _parse_account_info(resp["data"], BrokerType.MT4)

    # ------------------------------------------------------------------
    # Positions  (MT4: ticket is integer, all positions are hedging)
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[BrokerPosition]:
        resp = await self._bridge._send_command({"cmd": "positions"})
        _check_response(resp, "get_positions")
        return [_parse_mt4_position(p) for p in resp.get("data", [])]

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

        resp = await self._bridge._send_command(cmd)
        _check_response(resp, "place_order")
        logger.info("mt4_order_placed", symbol=symbol, side=side)
        return resp.get("data", {})

    async def modify_order(
        self,
        order_id: str,
        quantity: float | None = None,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> bool:
        # MT4 tickets are integers; coerce string representation
        cmd: dict[str, Any] = {"cmd": "modify_order", "ticket": int(order_id)}
        if price is not None:
            cmd["price"] = price
        if stop_loss is not None:
            cmd["stop_loss"] = stop_loss
        if take_profit is not None:
            cmd["take_profit"] = take_profit

        try:
            resp = await self._bridge._send_command(cmd)
            return resp.get("status") == "ok"
        except Exception as exc:
            logger.error("mt4_modify_order_failed", order_id=order_id, error=str(exc))
            return False

    async def cancel_order(self, order_id: str) -> bool:
        try:
            resp = await self._bridge._send_command(
                {"cmd": "cancel_order", "ticket": int(order_id)}
            )
            return resp.get("status") == "ok"
        except Exception as exc:
            logger.error("mt4_cancel_order_failed", order_id=order_id, error=str(exc))
            return False

    async def get_order_history(self, since: datetime | None = None) -> list[dict]:
        cmd: dict[str, Any] = {"cmd": "history"}
        if since is not None:
            cmd["from"] = since.isoformat()
        resp = await self._bridge._send_command(cmd)
        _check_response(resp, "get_order_history")
        return resp.get("data", [])


# ---------------------------------------------------------------------------
# MT4-specific position parser
# ---------------------------------------------------------------------------

def _parse_mt4_position(p: dict) -> BrokerPosition:
    """Map MT4 trade fields to BrokerPosition.

    MT4 ``type``: 0=BUY, 1=SELL, 2=BUY_LIMIT, 3=SELL_LIMIT, 4=BUY_STOP, 5=SELL_STOP.
    Only types 0/1 are open positions.
    """
    trade_type = int(p.get("type", 0))
    side = "long" if trade_type == 0 else "short"
    ticket = str(p.get("ticket", p.get("id", "")))

    return BrokerPosition(
        broker_position_id=ticket,
        symbol=str(p.get("symbol", "")),
        side=side,
        size=float(p.get("lots", p.get("volume", p.get("size", 0)))),
        entry_price=float(p.get("open_price", p.get("price_open", p.get("entry_price", 0)))),
        current_price=float(p.get("close_price", p.get("price_current", p.get("current_price", 0)))),
        unrealized_pnl=float(p.get("profit", 0)),
        stop_loss=_float_or_none(p.get("sl")),
        take_profit=_float_or_none(p.get("tp")),
        swap=float(p.get("swap", 0)),
        commission=float(p.get("commission", 0)),
    )
