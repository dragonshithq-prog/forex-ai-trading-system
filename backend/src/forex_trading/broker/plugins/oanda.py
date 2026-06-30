"""OANDA broker plugin using oandapyV20."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
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

# ---------------------------------------------------------------------------
# Instrument format helpers
# ---------------------------------------------------------------------------

def _to_oanda_instrument(symbol: str) -> str:
    """Convert EURUSD → EUR_USD."""
    symbol = symbol.upper().replace("_", "").replace("/", "").replace(" ", "")
    if len(symbol) == 6:
        return f"{symbol[:3]}_{symbol[3:]}"
    return symbol


def _from_oanda_instrument(instrument: str) -> str:
    """Convert EUR_USD → EURUSD."""
    return instrument.replace("_", "")


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _with_retry(fn: Any, retries: int = 3, base_delay: float = 1.0) -> Any:
    """Synchronously call *fn* up to *retries* times with exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "oanda_retry",
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(exc),
                )
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# OANDAPlugin
# ---------------------------------------------------------------------------

class OANDAPlugin(BrokerPlugin):
    """OANDA broker plugin backed by oandapyV20."""

    def __init__(self) -> None:
        super().__init__(BrokerType.OANDA)
        self._api: Any = None
        self._account_id: str = ""
        self._stream_thread: threading.Thread | None = None
        self._stream_stop_event: threading.Event = threading.Event()
        self._subscribed_symbols: set[str] = set()
        self._tick_callbacks: list[Any] = []

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self, credentials: BrokerCredentials) -> bool:
        if not credentials.api_key or not credentials.account_id:
            logger.error("oanda_missing_credentials")
            self._status = ConnectionStatus.ERROR
            return False

        try:
            import oandapyV20  # type: ignore[import]
            import oandapyV20.endpoints.accounts as accounts  # type: ignore[import]
        except ImportError:
            logger.error("oandapyV20_not_installed")
            self._status = ConnectionStatus.ERROR
            return False

        self._status = ConnectionStatus.CONNECTING
        self._credentials = credentials
        self._account_id = credentials.account_id
        environment = "practice" if credentials.environment != "live" else "live"

        try:
            self._api = oandapyV20.API(
                access_token=credentials.api_key,
                environment=environment,
            )

            def _verify() -> None:
                req = accounts.AccountSummary(self._account_id)
                self._api.request(req)

            await asyncio.get_event_loop().run_in_executor(None, lambda: _with_retry(_verify))
            self._status = ConnectionStatus.CONNECTED
            logger.info(
                "oanda_connected",
                account_id=self._account_id,
                environment=environment,
            )
            return True
        except Exception as exc:
            self._status = ConnectionStatus.ERROR
            logger.error("oanda_connect_failed", error=str(exc))
            return False

    async def disconnect(self) -> None:
        self._stream_stop_event.set()
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=5)
        self._api = None
        self._status = ConnectionStatus.DISCONNECTED
        logger.info("oanda_disconnected")

    # ------------------------------------------------------------------
    # Market data streaming
    # ------------------------------------------------------------------

    async def subscribe_market_data(self, symbols: list[str]) -> None:
        if self._status != ConnectionStatus.CONNECTED or self._api is None:
            raise RuntimeError("Not connected to OANDA")

        oanda_symbols = [_to_oanda_instrument(s) for s in symbols]
        self._subscribed_symbols.update(symbols)

        self._stream_stop_event.clear()

        def _stream() -> None:
            try:
                import oandapyV20.endpoints.pricing as pricing  # type: ignore[import]
                req = pricing.PricingStream(
                    accountID=self._account_id,
                    params={"instruments": ",".join(oanda_symbols)},
                )
                for msg in self._api.request(req):
                    if self._stream_stop_event.is_set():
                        break
                    if msg.get("type") != "PRICE":
                        continue
                    symbol = _from_oanda_instrument(msg["instrument"])
                    bid = float(msg["bids"][0]["price"])
                    ask = float(msg["asks"][0]["price"])
                    for cb in self._tick_callbacks:
                        try:
                            cb(symbol, bid, ask)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("oanda_tick_callback_error", error=str(exc))
            except Exception as exc:  # noqa: BLE001
                if not self._stream_stop_event.is_set():
                    logger.error("oanda_stream_error", error=str(exc))

        self._stream_thread = threading.Thread(target=_stream, daemon=True, name="oanda-stream")
        self._stream_thread.start()
        logger.info("oanda_stream_started", symbols=oanda_symbols)

    async def unsubscribe_market_data(self, symbols: list[str]) -> None:
        self._stream_stop_event.set()
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=5)
        self._subscribed_symbols -= set(symbols)
        logger.info("oanda_stream_stopped", symbols=symbols)

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_account_info(self) -> AccountInfo:
        if self._api is None:
            raise RuntimeError("Not connected to OANDA")

        import oandapyV20.endpoints.accounts as accounts  # type: ignore[import]

        def _fetch() -> dict:
            req = accounts.AccountDetails(self._account_id)
            return self._api.request(req)

        data = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _with_retry(_fetch)
        )
        acct = data["account"]

        balance = float(acct.get("balance", 0))
        unrealized_pl = float(acct.get("unrealizedPL", 0))
        margin_used = float(acct.get("marginUsed", 0))
        margin_available = float(acct.get("marginAvailable", 0))
        equity = balance + unrealized_pl
        margin_level = (equity / margin_used * 100) if margin_used > 0 else 0.0

        return AccountInfo(
            account_id=self._account_id,
            broker=BrokerType.OANDA,
            balance=balance,
            equity=equity,
            margin=margin_used,
            free_margin=margin_available,
            margin_level=margin_level,
            unrealized_pnl=unrealized_pl,
            currency=acct.get("currency", "USD"),
            leverage=int(acct.get("marginRate", 0.01) and (1 / float(acct.get("marginRate", 0.01)))),
        )

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[BrokerPosition]:
        if self._api is None:
            raise RuntimeError("Not connected to OANDA")

        import oandapyV20.endpoints.positions as positions  # type: ignore[import]

        def _fetch() -> dict:
            req = positions.OpenPositions(self._account_id)
            return self._api.request(req)

        data = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _with_retry(_fetch)
        )

        result: list[BrokerPosition] = []
        for pos in data.get("positions", []):
            symbol = _from_oanda_instrument(pos["instrument"])
            long_units = float(pos["long"]["units"])
            short_units = float(pos["short"]["units"])

            if long_units != 0:
                result.append(
                    BrokerPosition(
                        broker_position_id=f"{symbol}_long",
                        symbol=symbol,
                        side="long",
                        size=abs(long_units),
                        entry_price=float(pos["long"].get("averagePrice", 0) or 0),
                        unrealized_pnl=float(pos["long"].get("unrealizedPL", 0) or 0),
                        swap=float(pos["long"].get("financing", 0) or 0),
                    )
                )
            if short_units != 0:
                result.append(
                    BrokerPosition(
                        broker_position_id=f"{symbol}_short",
                        symbol=symbol,
                        side="short",
                        size=abs(short_units),
                        entry_price=float(pos["short"].get("averagePrice", 0) or 0),
                        unrealized_pnl=float(pos["short"].get("unrealizedPL", 0) or 0),
                        swap=float(pos["short"].get("financing", 0) or 0),
                    )
                )
        return result

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
        if self._api is None:
            raise RuntimeError("Not connected to OANDA")

        import oandapyV20.endpoints.orders as orders  # type: ignore[import]

        units = str(int(quantity)) if side.lower() in ("buy", "long") else str(-int(quantity))
        oanda_type = _map_order_type(order_type)

        order_body: dict[str, Any] = {
            "order": {
                "type": oanda_type,
                "instrument": _to_oanda_instrument(symbol),
                "units": units,
                "timeInForce": "FOK" if oanda_type == "MARKET" else "GTC",
                "positionFill": "DEFAULT",
            }
        }

        if oanda_type in ("LIMIT", "STOP"):
            if price is None:
                raise ValueError("price required for non-market orders")
            order_body["order"]["price"] = str(price)

        if stop_loss is not None:
            order_body["order"]["stopLossOnFill"] = {"price": str(stop_loss)}
        if take_profit is not None:
            order_body["order"]["takeProfitOnFill"] = {"price": str(take_profit)}

        def _place() -> dict:
            req = orders.OrderCreate(self._account_id, data=order_body)
            return self._api.request(req)

        response = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _with_retry(_place)
        )
        logger.info("oanda_order_placed", symbol=symbol, side=side, units=units)
        return response

    async def modify_order(
        self,
        order_id: str,
        quantity: float | None = None,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> bool:
        if self._api is None:
            raise RuntimeError("Not connected to OANDA")

        import oandapyV20.endpoints.orders as orders  # type: ignore[import]

        body: dict[str, Any] = {"order": {}}
        if price is not None:
            body["order"]["price"] = str(price)
        if stop_loss is not None:
            body["order"]["stopLossOnFill"] = {"price": str(stop_loss)}
        if take_profit is not None:
            body["order"]["takeProfitOnFill"] = {"price": str(take_profit)}

        def _modify() -> dict:
            req = orders.OrderReplace(self._account_id, orderID=order_id, data=body)
            return self._api.request(req)

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: _with_retry(_modify)
            )
            return True
        except Exception as exc:
            logger.error("oanda_modify_order_failed", order_id=order_id, error=str(exc))
            return False

    async def cancel_order(self, order_id: str) -> bool:
        if self._api is None:
            raise RuntimeError("Not connected to OANDA")

        import oandapyV20.endpoints.orders as orders  # type: ignore[import]

        def _cancel() -> dict:
            req = orders.OrderCancel(self._account_id, orderID=order_id)
            return self._api.request(req)

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: _with_retry(_cancel)
            )
            return True
        except Exception as exc:
            logger.error("oanda_cancel_order_failed", order_id=order_id, error=str(exc))
            return False

    async def get_order_history(self, since: datetime | None = None) -> list[dict]:
        if self._api is None:
            raise RuntimeError("Not connected to OANDA")

        import oandapyV20.endpoints.transactions as transactions  # type: ignore[import]

        params: dict[str, str] = {}
        if since is not None:
            params["from"] = since.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000000Z")

        def _fetch() -> dict:
            req = transactions.TransactionList(self._account_id, params=params or None)
            return self._api.request(req)

        data = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _with_retry(_fetch)
        )
        return data.get("transactions", [])


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _map_order_type(order_type: str) -> str:
    mapping = {
        "market": "MARKET",
        "limit": "LIMIT",
        "stop": "STOP",
        "stop_limit": "LIMIT",
    }
    return mapping.get(order_type.lower(), "MARKET")
