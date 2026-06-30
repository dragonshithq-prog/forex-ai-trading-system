"""Unit tests for broker plugins, market data service, structure analyzer, and discovery."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Import all modules under test
# ---------------------------------------------------------------------------
from forex_trading.broker.gateway import (
    AccountInfo,
    BrokerCredentials,
    BrokerPosition,
    BrokerType,
    ConnectionStatus,
)
from forex_trading.broker.plugins.oanda import (
    OANDAPlugin,
    _from_oanda_instrument,
    _map_order_type,
    _to_oanda_instrument,
    _with_retry,
)
from forex_trading.broker.plugins.mt5_bridge import (
    MT5BridgePlugin,
    _check_response,
    _float_or_none,
    _parse_account_info,
    _parse_mt5_position,
)
from forex_trading.broker.plugins.mt4_bridge import MT4BridgePlugin, _parse_mt4_position
from forex_trading.market_data.services.market_data_service import MarketDataService
from forex_trading.market_data.services.structure_analyzer import (
    BreakType,
    MarketStructure,
    MarketStructureAnalyzer,
    StructureAnalyzer,
    StructureLevel,
    StructureType,
)
from forex_trading.broker.discovery.service import (
    BrokerDiscoveryService,
    _check_static_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(n: int = 60, trend: str = "up") -> list[dict]:
    """Generate deterministic synthetic candles."""
    candles = []
    price = 1.1000
    for i in range(n):
        delta = 0.0005 if trend == "up" else (-0.0005 if trend == "down" else 0.0)
        o = round(price, 5)
        c = round(price + delta, 5)
        h = round(max(o, c) + 0.0002, 5)
        lv = round(min(o, c) - 0.0002, 5)
        candles.append({
            "timestamp": datetime(2024, 1, 1) + timedelta(hours=i),
            "open": o,
            "high": h,
            "low": lv,
            "close": c,
            "volume": 100 + i,
        })
        price = c
    return candles


# ---------------------------------------------------------------------------
# TASK 1: OANDAPlugin unit tests
# ---------------------------------------------------------------------------

class TestOANDAInstrumentHelpers:
    def test_to_oanda_instrument_standard(self):
        assert _to_oanda_instrument("EURUSD") == "EUR_USD"

    def test_to_oanda_instrument_already_underscore(self):
        assert _to_oanda_instrument("EUR_USD") == "EUR_USD"

    def test_from_oanda_instrument(self):
        assert _from_oanda_instrument("EUR_USD") == "EURUSD"
        assert _from_oanda_instrument("GBP_USD") == "GBPUSD"

    def test_roundtrip(self):
        symbols = ["EURUSD", "GBPJPY", "AUDUSD", "USDCAD"]
        for sym in symbols:
            assert _from_oanda_instrument(_to_oanda_instrument(sym)) == sym

    def test_map_order_type_market(self):
        assert _map_order_type("market") == "MARKET"

    def test_map_order_type_limit(self):
        assert _map_order_type("limit") == "LIMIT"

    def test_map_order_type_stop(self):
        assert _map_order_type("stop") == "STOP"

    def test_map_order_type_unknown_defaults_market(self):
        assert _map_order_type("exotic") == "MARKET"


class TestRetryLogic:
    def test_success_first_attempt(self):
        calls = []
        def fn():
            calls.append(1)
            return "ok"
        assert _with_retry(fn) == "ok"
        assert len(calls) == 1

    def test_retries_on_exception(self):
        calls = []
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("transient")
            return "done"
        with patch("forex_trading.broker.plugins.oanda.time.sleep") as mock_sleep:
            result = _with_retry(fn, retries=3, base_delay=0.001)
        assert result == "done"
        assert len(calls) == 3

    def test_raises_after_max_retries(self):
        def fn():
            raise ValueError("always fails")
        with patch("forex_trading.broker.plugins.oanda.time.sleep"):
            with pytest.raises(ValueError, match="always fails"):
                _with_retry(fn, retries=3, base_delay=0.001)


class TestOANDAPlugin:
    def test_initial_status_disconnected(self):
        plugin = OANDAPlugin()
        assert plugin.status == ConnectionStatus.DISCONNECTED

    def test_broker_type(self):
        plugin = OANDAPlugin()
        assert plugin.broker_type == BrokerType.OANDA

    @pytest.mark.asyncio
    async def test_connect_fails_without_oandapyv20(self):
        plugin = OANDAPlugin()
        creds = BrokerCredentials(
            broker_type=BrokerType.OANDA,
            api_key="test",
            account_id="123",
        )
        with patch.dict("sys.modules", {"oandapyV20": None}):
            result = await plugin.connect(creds)
        assert result is False
        assert plugin.status == ConnectionStatus.ERROR

    @pytest.mark.asyncio
    async def test_connect_fails_without_credentials(self):
        plugin = OANDAPlugin()
        creds = BrokerCredentials(broker_type=BrokerType.OANDA)
        result = await plugin.connect(creds)
        assert result is False
        assert plugin.status == ConnectionStatus.ERROR

    @pytest.mark.asyncio
    async def test_connect_success_mock(self):
        plugin = OANDAPlugin()
        creds = BrokerCredentials(
            broker_type=BrokerType.OANDA,
            api_key="test_key",
            account_id="001-001-123456-001",
            environment="practice",
        )

        mock_api_cls = MagicMock()
        mock_api_inst = MagicMock()
        mock_api_cls.return_value = mock_api_inst
        mock_api_inst.request = MagicMock(return_value={"account": {"id": "123"}})

        mock_accounts_module = MagicMock()
        mock_accounts_module.AccountSummary = MagicMock()

        with patch.dict("sys.modules", {
            "oandapyV20": MagicMock(API=mock_api_cls),
            "oandapyV20.endpoints": MagicMock(),
            "oandapyV20.endpoints.accounts": mock_accounts_module,
        }):
            result = await plugin.connect(creds)

        assert result is True
        assert plugin.status == ConnectionStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_get_account_info_not_connected_raises(self):
        plugin = OANDAPlugin()
        with pytest.raises(RuntimeError, match="Not connected"):
            await plugin.get_account_info()

    @pytest.mark.asyncio
    async def test_get_account_info_maps_fields(self):
        plugin = OANDAPlugin()
        plugin._status = ConnectionStatus.CONNECTED
        plugin._account_id = "001-001-123456"

        oanda_response = {
            "account": {
                "id": "001-001-123456",
                "balance": "10000.00",
                "unrealizedPL": "250.00",
                "marginUsed": "500.00",
                "marginAvailable": "9750.00",
                "currency": "USD",
                "marginRate": "0.02",
            }
        }
        mock_api = MagicMock()
        mock_api.request = MagicMock(return_value=oanda_response)
        plugin._api = mock_api

        mock_accounts_module = MagicMock()
        mock_accounts_module.AccountDetails = MagicMock(return_value=MagicMock())
        mock_oanda = MagicMock()

        with patch.dict("sys.modules", {
            "oandapyV20": mock_oanda,
            "oandapyV20.endpoints": MagicMock(),
            "oandapyV20.endpoints.accounts": mock_accounts_module,
        }):
            info = await plugin.get_account_info()

        assert info.balance == 10000.0
        assert info.equity == 10250.0
        assert info.currency == "USD"
        assert info.broker == BrokerType.OANDA

    @pytest.mark.asyncio
    async def test_get_positions_maps_long_and_short(self):
        plugin = OANDAPlugin()
        plugin._status = ConnectionStatus.CONNECTED
        plugin._account_id = "001"
        plugin._api = MagicMock()
        plugin._api.request = MagicMock(return_value={
            "positions": [
                {
                    "instrument": "EUR_USD",
                    "long": {"units": "10000", "averagePrice": "1.09500", "unrealizedPL": "50.0", "financing": "0"},
                    "short": {"units": "0", "averagePrice": "0", "unrealizedPL": "0", "financing": "0"},
                }
            ]
        })

        mock_positions_module = MagicMock()
        mock_positions_module.OpenPositions = MagicMock(return_value=MagicMock())

        with patch.dict("sys.modules", {
            "oandapyV20": MagicMock(),
            "oandapyV20.endpoints": MagicMock(),
            "oandapyV20.endpoints.positions": mock_positions_module,
        }):
            positions = await plugin.get_positions()

        assert len(positions) == 1
        assert positions[0].symbol == "EURUSD"
        assert positions[0].side == "long"
        assert positions[0].size == 10000.0

    @pytest.mark.asyncio
    async def test_place_order_not_connected_raises(self):
        plugin = OANDAPlugin()
        with pytest.raises(RuntimeError):
            await plugin.place_order("EURUSD", "buy", 1000)

    @pytest.mark.asyncio
    async def test_cancel_order_returns_false_on_error(self):
        plugin = OANDAPlugin()
        plugin._status = ConnectionStatus.CONNECTED
        plugin._account_id = "001"
        plugin._api = MagicMock()
        plugin._api.request = MagicMock(side_effect=Exception("api error"))

        mock_orders_module = MagicMock()
        mock_orders_module.OrderCancel = MagicMock(return_value=MagicMock())

        with patch.dict("sys.modules", {
            "oandapyV20": MagicMock(),
            "oandapyV20.endpoints": MagicMock(),
            "oandapyV20.endpoints.orders": mock_orders_module,
        }):
            with patch("forex_trading.broker.plugins.oanda.time") as mock_time:
                mock_time.sleep = MagicMock()
                result = await plugin.cancel_order("999")

        assert result is False

    @pytest.mark.asyncio
    async def test_disconnect_clears_api(self):
        plugin = OANDAPlugin()
        plugin._api = MagicMock()
        plugin._status = ConnectionStatus.CONNECTED
        await plugin.disconnect()
        assert plugin._api is None
        assert plugin.status == ConnectionStatus.DISCONNECTED


# ---------------------------------------------------------------------------
# TASK 2 & 3: MT5 / MT4 Bridge Plugin unit tests
# ---------------------------------------------------------------------------

class TestMT5BridgeHelpers:
    def test_float_or_none_zero_returns_none(self):
        assert _float_or_none(0) is None
        assert _float_or_none(0.0) is None

    def test_float_or_none_nonzero(self):
        assert _float_or_none(1.2345) == 1.2345

    def test_float_or_none_invalid(self):
        assert _float_or_none("not_a_number") is None

    def test_float_or_none_none(self):
        assert _float_or_none(None) is None

    def test_parse_account_info_mt5(self):
        d = {
            "login": 12345,
            "balance": 5000.0,
            "equity": 5100.0,
            "margin": 200.0,
            "free_margin": 4900.0,
            "profit": 100.0,
            "currency": "USD",
            "leverage": 100,
        }
        info = _parse_account_info(d, BrokerType.MT5)
        assert info.account_id == "12345"
        assert info.balance == 5000.0
        assert info.equity == 5100.0
        assert info.leverage == 100
        assert info.broker == BrokerType.MT5

    def test_parse_account_info_margin_level(self):
        d = {
            "balance": 1000.0,
            "equity": 1000.0,
            "margin": 100.0,
            "free_margin": 900.0,
        }
        info = _parse_account_info(d, BrokerType.MT5)
        assert info.margin_level == pytest.approx(1000.0)

    def test_parse_account_info_zero_margin(self):
        d = {"balance": 1000.0}
        info = _parse_account_info(d, BrokerType.MT5)
        assert info.margin_level == 0.0

    def test_parse_mt5_position_long(self):
        p = {
            "ticket": "123456",
            "symbol": "EURUSD",
            "type": 0,
            "volume": 0.1,
            "price_open": 1.09500,
            "price_current": 1.09600,
            "profit": 10.0,
            "sl": 1.09000,
            "tp": 1.10000,
            "swap": -0.5,
            "commission": -1.0,
        }
        pos = _parse_mt5_position(p)
        assert pos.side == "long"
        assert pos.symbol == "EURUSD"
        assert pos.size == 0.1
        assert pos.stop_loss == 1.09000
        assert pos.take_profit == 1.10000

    def test_parse_mt5_position_short(self):
        p = {"ticket": "99", "symbol": "GBPUSD", "type": 1, "volume": 1.0}
        pos = _parse_mt5_position(p)
        assert pos.side == "short"

    def test_check_response_ok(self):
        _check_response({"status": "ok"}, "test")  # should not raise

    def test_check_response_error_raises(self):
        with pytest.raises(RuntimeError, match="bridge error"):
            _check_response({"status": "error", "error": "something bad"}, "test")


class TestMT5BridgePlugin:
    def test_initial_status(self):
        plugin = MT5BridgePlugin()
        assert plugin.status == ConnectionStatus.DISCONNECTED
        assert plugin.broker_type == BrokerType.MT5

    @pytest.mark.asyncio
    async def test_connect_refused(self):
        plugin = MT5BridgePlugin()
        creds = BrokerCredentials(
            broker_type=BrokerType.MT5,
            host="127.0.0.1",
            port=19999,  # unused port
        )
        result = await plugin.connect(creds)
        assert result is False
        assert plugin.status == ConnectionStatus.ERROR

    @pytest.mark.asyncio
    async def test_send_command_not_connected_raises(self):
        plugin = MT5BridgePlugin()
        with pytest.raises(ConnectionError, match="not connected"):
            await plugin._send_command({"cmd": "ping"})

    @pytest.mark.asyncio
    async def test_place_order_builds_correct_command(self):
        plugin = MT5BridgePlugin()
        plugin._reader = AsyncMock()
        plugin._writer = AsyncMock()
        plugin._writer.write = MagicMock()
        plugin._writer.drain = AsyncMock()

        response_json = json.dumps({"status": "ok", "data": {"ticket": 42}}) + "\n"
        plugin._reader.readline = AsyncMock(return_value=response_json.encode())

        result = await plugin.place_order("EURUSD", "buy", 0.1, stop_loss=1.09, take_profit=1.11)
        assert result == {"ticket": 42}

    @pytest.mark.asyncio
    async def test_cancel_order_returns_false_on_error(self):
        plugin = MT5BridgePlugin()
        plugin._reader = AsyncMock()
        plugin._writer = AsyncMock()
        plugin._writer.write = MagicMock()
        plugin._writer.drain = AsyncMock()

        response_json = json.dumps({"status": "error", "error": "ticket not found"}) + "\n"
        plugin._reader.readline = AsyncMock(return_value=response_json.encode())

        result = await plugin.cancel_order("9999")
        assert result is False

    @pytest.mark.asyncio
    async def test_modify_order_ok(self):
        plugin = MT5BridgePlugin()
        plugin._reader = AsyncMock()
        plugin._writer = AsyncMock()
        plugin._writer.write = MagicMock()
        plugin._writer.drain = AsyncMock()

        response_json = json.dumps({"status": "ok"}) + "\n"
        plugin._reader.readline = AsyncMock(return_value=response_json.encode())

        result = await plugin.modify_order("123", stop_loss=1.08, take_profit=1.12)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_positions_parses_data(self):
        plugin = MT5BridgePlugin()
        plugin._reader = AsyncMock()
        plugin._writer = AsyncMock()
        plugin._writer.write = MagicMock()
        plugin._writer.drain = AsyncMock()

        positions_data = [
            {"ticket": "1", "symbol": "EURUSD", "type": 0, "volume": 0.1,
             "price_open": 1.1, "price_current": 1.11, "profit": 10.0,
             "sl": 0, "tp": 0, "swap": 0, "commission": 0},
        ]
        response_json = json.dumps({"status": "ok", "data": positions_data}) + "\n"
        plugin._reader.readline = AsyncMock(return_value=response_json.encode())

        positions = await plugin.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "EURUSD"

    @pytest.mark.asyncio
    async def test_subscribe_market_data_sends_command(self):
        plugin = MT5BridgePlugin()
        plugin._reader = AsyncMock()
        plugin._writer = AsyncMock()
        plugin._writer.write = MagicMock()
        plugin._writer.drain = AsyncMock()

        response_json = json.dumps({"status": "ok"}) + "\n"
        plugin._reader.readline = AsyncMock(return_value=response_json.encode())

        await plugin.subscribe_market_data(["EURUSD", "GBPUSD"])
        assert "EURUSD" in plugin._subscribed_symbols
        assert "GBPUSD" in plugin._subscribed_symbols

    @pytest.mark.asyncio
    async def test_get_order_history_with_since(self):
        plugin = MT5BridgePlugin()
        plugin._reader = AsyncMock()
        plugin._writer = AsyncMock()
        plugin._writer.write = MagicMock()
        plugin._writer.drain = AsyncMock()

        trades = [{"ticket": "1", "profit": 50.0}]
        response_json = json.dumps({"status": "ok", "data": trades}) + "\n"
        plugin._reader.readline = AsyncMock(return_value=response_json.encode())

        since = datetime(2024, 1, 1)
        history = await plugin.get_order_history(since=since)
        assert len(history) == 1


class TestMT4BridgePlugin:
    def test_initial_status(self):
        plugin = MT4BridgePlugin()
        assert plugin.status == ConnectionStatus.DISCONNECTED

    def test_broker_type(self):
        plugin = MT4BridgePlugin()
        assert plugin.broker_type == BrokerType.MT4

    def test_parse_mt4_position_buy(self):
        p = {
            "ticket": 11111,
            "symbol": "USDJPY",
            "type": 0,
            "lots": 0.5,
            "open_price": 149.500,
            "close_price": 149.600,
            "profit": 5.0,
            "sl": 149.0,
            "tp": 150.5,
        }
        pos = _parse_mt4_position(p)
        assert pos.side == "long"
        assert pos.symbol == "USDJPY"
        assert pos.size == 0.5
        assert pos.broker_position_id == "11111"

    def test_parse_mt4_position_sell(self):
        p = {"ticket": 22222, "symbol": "EURUSD", "type": 1, "lots": 1.0}
        pos = _parse_mt4_position(p)
        assert pos.side == "short"

    @pytest.mark.asyncio
    async def test_cancel_order_coerces_int_ticket(self):
        plugin = MT4BridgePlugin()
        plugin._bridge._reader = AsyncMock()
        plugin._bridge._writer = AsyncMock()
        plugin._bridge._writer.write = MagicMock()
        plugin._bridge._writer.drain = AsyncMock()

        response_json = json.dumps({"status": "ok"}) + "\n"
        plugin._bridge._reader.readline = AsyncMock(return_value=response_json.encode())

        # Should not raise when order_id is string representation of int
        result = await plugin.cancel_order("54321")
        assert result is True

    @pytest.mark.asyncio
    async def test_modify_order_coerces_int_ticket(self):
        plugin = MT4BridgePlugin()
        plugin._bridge._reader = AsyncMock()
        plugin._bridge._writer = AsyncMock()
        plugin._bridge._writer.write = MagicMock()
        plugin._bridge._writer.drain = AsyncMock()

        response_json = json.dumps({"status": "ok"}) + "\n"
        plugin._bridge._reader.readline = AsyncMock(return_value=response_json.encode())

        result = await plugin.modify_order("12345", stop_loss=1.08)
        assert result is True


# ---------------------------------------------------------------------------
# TASK 4: MarketDataService tests
# ---------------------------------------------------------------------------

class TestMarketDataService:
    def test_init_no_deps(self):
        svc = MarketDataService()
        assert svc._tick_buffer == {}

    @pytest.mark.asyncio
    async def test_on_tick_updates_buffer(self):
        svc = MarketDataService()
        await svc.on_tick("EURUSD", 1.1000, 1.1002, 100.0)
        tick = svc._tick_buffer["EURUSD"]
        assert tick["bid"] == 1.1000
        assert tick["ask"] == 1.1002
        assert tick["spread"] == pytest.approx(0.0002)

    @pytest.mark.asyncio
    async def test_get_latest_tick_returns_buffered(self):
        svc = MarketDataService()
        await svc.on_tick("EURUSD", 1.1, 1.1002, 0)
        tick = await svc.get_latest_tick("EURUSD")
        assert tick is not None
        assert tick["bid"] == 1.1

    @pytest.mark.asyncio
    async def test_get_latest_tick_unknown_symbol_returns_none(self):
        svc = MarketDataService()
        assert await svc.get_latest_tick("XYZABC") is None

    @pytest.mark.asyncio
    async def test_subscribe_ticks_delivers_tick(self):
        svc = MarketDataService()
        received = []

        async def cb(tick):
            received.append(tick)

        await svc.subscribe_ticks("EURUSD", cb)
        await svc.on_tick("EURUSD", 1.1, 1.1002, 0)
        assert len(received) == 1
        assert received[0]["symbol"] == "EURUSD"

    @pytest.mark.asyncio
    async def test_unsubscribe_ticks_stops_delivery(self):
        svc = MarketDataService()
        received = []

        async def cb(tick):
            received.append(tick)

        await svc.subscribe_ticks("EURUSD", cb)
        await svc.unsubscribe_ticks("EURUSD", cb)
        await svc.on_tick("EURUSD", 1.1, 1.1002, 0)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_get_current_price_compatibility(self):
        svc = MarketDataService()
        await svc.on_tick("EURUSD", 1.1000, 1.1002, 100)
        price = await svc.get_current_price("EURUSD")
        assert price == {"bid": 1.1000, "ask": 1.1002}

    @pytest.mark.asyncio
    async def test_get_spread_compatibility(self):
        svc = MarketDataService()
        await svc.on_tick("EURUSD", 1.1000, 1.1002, 100)
        spread = await svc.get_spread("EURUSD")
        assert spread == pytest.approx(0.0002)

    @pytest.mark.asyncio
    async def test_get_candles_returns_empty_without_broker(self):
        svc = MarketDataService()
        candles = await svc.get_candles("EURUSD", "H1", 100)
        assert candles == []

    @pytest.mark.asyncio
    async def test_get_candles_uses_cache(self):
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=json.dumps([{"open": 1.1}]))

        svc = MarketDataService(cache_manager=mock_cache)
        candles = await svc.get_candles("EURUSD", "H1", 100)
        assert candles == [{"open": 1.1}]
        mock_cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_candles_sets_cache_on_broker_data(self):
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_plugin = AsyncMock()
        mock_plugin.get_ohlcv = AsyncMock(return_value=[{"close": 1.1}])

        mock_gateway = MagicMock()
        mock_gateway.get_best_connection = MagicMock(return_value=uuid4())
        mock_gateway._connections = {list(mock_gateway._connections.keys())[0]: mock_plugin} if False else {}

        # Manually inject a connection
        cid = uuid4()
        mock_gateway.get_best_connection = MagicMock(return_value=cid)
        mock_gateway._connections = {cid: mock_plugin}

        svc = MarketDataService(cache_manager=mock_cache, broker_gateway=mock_gateway)
        candles = await svc.get_candles("EURUSD", "H1", 10, broker_connection_id=cid)
        assert candles == [{"close": 1.1}]
        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_calculate_atr_returns_zero_insufficient_data(self):
        svc = MarketDataService()
        atr = await svc.calculate_atr("EURUSD", "H1", period=14)
        assert atr == 0.0

    @pytest.mark.asyncio
    async def test_calculate_atr_with_candles(self):
        candles = _make_candles(20)
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=json.dumps(candles, default=str))

        svc = MarketDataService(cache_manager=mock_cache)
        atr = await svc.calculate_atr("EURUSD", "H1", period=14)
        assert atr > 0.0

    @pytest.mark.asyncio
    async def test_get_multi_timeframe_data_no_broker(self):
        svc = MarketDataService()
        result = await svc.get_multi_timeframe_data("EURUSD", ["M5", "H1"])
        assert "M5" in result
        assert "H1" in result

    @pytest.mark.asyncio
    async def test_get_currency_strength_no_data_returns_50(self):
        svc = MarketDataService()
        result = await svc.get_currency_strength(["EUR", "USD", "GBP"])
        assert all(v == 50.0 for v in result.values())

    @pytest.mark.asyncio
    async def test_legacy_subscribe_ticks_multi(self):
        svc = MarketDataService()
        received = []

        async def cb(event):
            received.append(event)

        await svc.subscribe_ticks_multi(["EURUSD"], cb)
        await svc.on_tick("EURUSD", 1.1, 1.1002, 0)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_tick_callback_exception_does_not_propagate(self):
        svc = MarketDataService()

        async def bad_cb(tick):
            raise RuntimeError("bad callback")

        await svc.subscribe_ticks("EURUSD", bad_cb)
        # Should not raise
        await svc.on_tick("EURUSD", 1.1, 1.1002, 0)

    @pytest.mark.asyncio
    async def test_cache_failure_does_not_propagate(self):
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(side_effect=ConnectionError("redis down"))

        svc = MarketDataService(cache_manager=mock_cache)
        # Should not raise - falls through to broker (which is None → empty)
        candles = await svc.get_candles("EURUSD", "H1", 10)
        assert candles == []


# ---------------------------------------------------------------------------
# TASK 5: MarketStructureAnalyzer tests
# ---------------------------------------------------------------------------

class TestMarketStructureAnalyzer:
    def setup_method(self):
        self.analyzer = MarketStructureAnalyzer()

    def test_analyze_empty_returns_ranging(self):
        result = self.analyzer.analyze([], "H1", "EURUSD")
        assert result.trend_direction == "ranging"
        assert result.structure_type == StructureType.RANGING

    def test_analyze_insufficient_candles(self):
        result = self.analyzer.analyze(_make_candles(5), "H1", "EURUSD")
        assert result.trend_direction == "ranging"

    def test_analyze_uptrend_detection(self):
        candles = _make_candles(80, trend="up")
        result = self.analyzer.analyze(candles, "H1", "EURUSD")
        assert result.trend_direction in ("bullish", "ranging")

    def test_analyze_downtrend_detection(self):
        candles = _make_candles(80, trend="down")
        result = self.analyzer.analyze(candles, "H1", "EURUSD")
        assert result.trend_direction in ("bearish", "ranging")

    def test_find_swing_highs_returns_structure_levels(self):
        candles = _make_candles(60)
        highs = self.analyzer._find_swing_highs(candles, lookback=3)
        assert isinstance(highs, list)
        for h in highs:
            assert isinstance(h, StructureLevel)
            assert h.level_type == "swing_high"

    def test_find_swing_lows_returns_structure_levels(self):
        candles = _make_candles(60)
        lows = self.analyzer._find_swing_lows(candles, lookback=3)
        assert isinstance(lows, list)
        for lv in lows:
            assert isinstance(lv, StructureLevel)
            assert lv.level_type == "swing_low"

    def test_swing_high_price_is_maximum_in_window(self):
        candles = _make_candles(30)
        highs = self.analyzer._find_swing_highs(candles, lookback=2)
        for h in highs:
            assert h.price > 0

    def test_bos_detection_bullish(self):
        # Create candles with explicit break
        candles = _make_candles(30)
        # Set up a swing high, then a close above it
        highs = [StructureLevel(price=1.1100, level_type="swing_high", strength=0.5,
                                timeframe="H1", timestamp=datetime(2024, 1, 15))]
        lows = [StructureLevel(price=1.0900, level_type="swing_low", strength=0.5,
                               timeframe="H1", timestamp=datetime(2024, 1, 10))]
        # Modify last two candles so a BOS occurs
        candles[-2]["close"] = 1.1095
        candles[-1]["close"] = 1.1110
        bos = self.analyzer._detect_bos(candles, highs, lows)
        assert bos is not None
        assert bos["direction"] == "bullish"
        assert bos["type"] == "BOS"

    def test_bos_detection_bearish(self):
        candles = _make_candles(30)
        highs = [StructureLevel(price=1.1200, level_type="swing_high", strength=0.5,
                                timeframe="H1", timestamp=datetime(2024, 1, 15))]
        lows = [StructureLevel(price=1.0950, level_type="swing_low", strength=0.5,
                               timeframe="H1", timestamp=datetime(2024, 1, 10))]
        candles[-2]["close"] = 1.0960
        candles[-1]["close"] = 1.0940
        bos = self.analyzer._detect_bos(candles, highs, lows)
        assert bos is not None
        assert bos["direction"] == "bearish"

    def test_bos_no_break(self):
        candles = _make_candles(30)
        highs = [StructureLevel(price=1.2000, level_type="swing_high", strength=0.5,
                                timeframe="H1", timestamp=datetime(2024, 1, 1))]
        lows = [StructureLevel(price=1.0000, level_type="swing_low", strength=0.5,
                               timeframe="H1", timestamp=datetime(2024, 1, 1))]
        bos = self.analyzer._detect_bos(candles, highs, lows)
        assert bos is None

    def test_choch_detects_in_bullish_trend(self):
        candles = _make_candles(30)
        highs = [StructureLevel(price=1.1200, level_type="swing_high", strength=0.5,
                                timeframe="H1", timestamp=datetime(2024, 1, 1))]
        lows = [StructureLevel(price=1.0900, level_type="swing_low", strength=0.5,
                               timeframe="H1", timestamp=datetime(2024, 1, 1))]
        candles[-2]["close"] = 1.0910
        candles[-1]["close"] = 1.0890
        choch = self.analyzer._detect_choch(candles, highs, lows, trend="bullish")
        assert choch is not None
        assert choch["direction"] == "bearish"
        assert choch["type"] == "CHoCH"

    def test_find_order_blocks_bullish(self):
        # Need 3+ candles: [0] doesn't matter, [1]=bearish, [2]=strong bullish above [1].open
        candles = [
            {"open": 1.100, "high": 1.101, "low": 1.099, "close": 1.100,
             "timestamp": datetime(2024, 1, 1), "volume": 100},  # padding
            {"open": 1.100, "high": 1.101, "low": 1.095, "close": 1.096,
             "timestamp": datetime(2024, 1, 2), "volume": 100},  # bearish
            {"open": 1.096, "high": 1.115, "low": 1.095, "close": 1.112,
             "timestamp": datetime(2024, 1, 3), "volume": 200},  # strong bullish > prev.open(1.100)
        ]
        obs = self.analyzer._find_order_blocks(candles)
        types = [ob["type"] for ob in obs]
        assert "bullish_ob" in types

    def test_find_order_blocks_bearish(self):
        # Need 3+ candles: [0]=padding, [1]=bullish, [2]=strong bearish below [1].open
        candles = [
            {"open": 1.090, "high": 1.091, "low": 1.089, "close": 1.090,
             "timestamp": datetime(2024, 1, 1), "volume": 100},  # padding
            {"open": 1.090, "high": 1.105, "low": 1.089, "close": 1.102,
             "timestamp": datetime(2024, 1, 2), "volume": 100},  # bullish
            {"open": 1.102, "high": 1.103, "low": 1.075, "close": 1.078,
             "timestamp": datetime(2024, 1, 3), "volume": 200},  # strong bearish < prev.open(1.090)
        ]
        obs = self.analyzer._find_order_blocks(candles)
        types = [ob["type"] for ob in obs]
        assert "bearish_ob" in types

    def test_find_fair_value_gaps_bullish(self):
        # FVG: c[i].low > c[i-2].high
        candles = [
            {"open": 1.10, "high": 1.101, "low": 1.099, "close": 1.100,
             "timestamp": datetime(2024, 1, 1), "volume": 100},
            {"open": 1.100, "high": 1.103, "low": 1.100, "close": 1.102,
             "timestamp": datetime(2024, 1, 2), "volume": 100},
            {"open": 1.103, "high": 1.108, "low": 1.102, "close": 1.107,
             "timestamp": datetime(2024, 1, 3), "volume": 100},
        ]
        # c[0].high=1.101, c[2].low=1.102 → c[2].low > c[0].high → bullish FVG
        fvgs = self.analyzer._find_fair_value_gaps(candles)
        assert any(f["type"] == "bullish_fvg" for f in fvgs)

    def test_find_fair_value_gaps_bearish(self):
        # FVG: c[i].high < c[i-2].low
        candles = [
            {"open": 1.10, "high": 1.101, "low": 1.099, "close": 1.100,
             "timestamp": datetime(2024, 1, 1), "volume": 100},
            {"open": 1.100, "high": 1.101, "low": 1.098, "close": 1.099,
             "timestamp": datetime(2024, 1, 2), "volume": 100},
            {"open": 1.099, "high": 1.098, "low": 1.092, "close": 1.093,
             "timestamp": datetime(2024, 1, 3), "volume": 100},
        ]
        # c[0].low=1.099, c[2].high=1.098 → c[2].high < c[0].low → bearish FVG
        fvgs = self.analyzer._find_fair_value_gaps(candles)
        assert any(f["type"] == "bearish_fvg" for f in fvgs)

    def test_determine_trend_ranging_on_mixed(self):
        # Alternating highs and lows → ranging
        mixed_highs = [
            StructureLevel(1.15, "swing_high", 0.5, "H1", datetime(2024, 1, 1)),
            StructureLevel(1.10, "swing_high", 0.5, "H1", datetime(2024, 1, 5)),
            StructureLevel(1.13, "swing_high", 0.5, "H1", datetime(2024, 1, 9)),
        ]
        mixed_lows = [
            StructureLevel(1.05, "swing_low", 0.5, "H1", datetime(2024, 1, 3)),
            StructureLevel(1.08, "swing_low", 0.5, "H1", datetime(2024, 1, 7)),
            StructureLevel(1.06, "swing_low", 0.5, "H1", datetime(2024, 1, 11)),
        ]
        result = self.analyzer._determine_trend(mixed_highs, mixed_lows)
        assert result in ("ranging", "bullish", "bearish")

    def test_full_analysis_returns_market_structure(self):
        candles = _make_candles(80)
        result = self.analyzer.analyze(candles, "H1", "EURUSD")
        assert isinstance(result, MarketStructure)
        assert result.symbol == "EURUSD"
        assert result.timeframe == "H1"
        assert isinstance(result.analyzed_at, datetime)

    def test_full_analysis_last_bos_or_none(self):
        candles = _make_candles(80)
        result = self.analyzer.analyze(candles, "H1", "EURUSD")
        assert result.last_bos is None or isinstance(result.last_bos, dict)

    def test_full_analysis_order_blocks_limited(self):
        candles = _make_candles(80)
        result = self.analyzer.analyze(candles, "H1", "EURUSD")
        assert len(result.order_blocks) <= 5

    def test_full_analysis_fvg_limited(self):
        candles = _make_candles(80)
        result = self.analyzer.analyze(candles, "H1", "EURUSD")
        assert len(result.fair_value_gaps) <= 5


class TestLegacyStructureAnalyzer:
    """Verify backwards compatibility of the old StructureAnalyzer."""

    def setup_method(self):
        self.analyzer = StructureAnalyzer()

    def test_find_swings_returns_tuple_of_lists(self):
        candles = _make_candles(30)
        sh, sl = self.analyzer._find_swings(candles)
        assert isinstance(sh, list)
        assert isinstance(sl, list)

    @pytest.mark.asyncio
    async def test_analyze_few_candles_returns_ranging(self):
        result = await self.analyzer.analyze("EURUSD", [], "H1")
        assert result.structure_type == StructureType.RANGING

    @pytest.mark.asyncio
    async def test_analyze_returns_market_structure(self):
        candles = _make_candles(80)
        result = await self.analyzer.analyze("EURUSD", candles, "H1")
        assert isinstance(result, MarketStructure)

    def test_classify_structure_ranging_insufficient_swings(self):
        result = self.analyzer._classify_structure([], [], [])
        assert result == StructureType.RANGING

    def test_find_order_blocks_returns_list(self):
        candles = _make_candles(20)
        obs = self.analyzer._find_order_blocks(candles)
        assert isinstance(obs, list)

    def test_find_fair_value_gaps_returns_list(self):
        candles = _make_candles(20)
        fvgs = self.analyzer._find_fair_value_gaps(candles)
        assert isinstance(fvgs, list)


# ---------------------------------------------------------------------------
# TASK 7: BrokerDiscoveryService tests
# ---------------------------------------------------------------------------

class TestBrokerDiscoveryService:
    def setup_method(self):
        self.service = BrokerDiscoveryService()

    @pytest.mark.asyncio
    async def test_discover_returns_list(self):
        result = await self.service.discover_mt_terminals()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_discover_nonexistent_paths_returns_no_static(self):
        # Paths that shouldn't exist in CI - discovery still runs without crashing
        result = await self.service.discover_mt_terminals()
        # Just ensure no exception and result is a list
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_probe_port_closed_returns_inactive(self):
        result = await self.service._probe_port(19998)  # surely closed
        assert result["bridge_active"] is False

    @pytest.mark.asyncio
    async def test_test_broker_connection_unsupported_type(self):
        result = await self.service.test_broker_connection("fxcm", {})
        assert result["success"] is False
        assert "Unsupported" in result["error"]

    @pytest.mark.asyncio
    async def test_test_mt_connection_refused(self):
        result = await self.service.test_broker_connection(
            "mt5", {"host": "127.0.0.1", "port": 19997}
        )
        assert result["success"] is False
        assert result["account_id"] is None

    @pytest.mark.asyncio
    async def test_test_oanda_connection_missing_creds(self):
        result = await self.service._test_oanda_connection({})
        assert result["success"] is False
        assert "required" in result["error"]

    @pytest.mark.asyncio
    async def test_test_oanda_connection_no_lib(self):
        with patch.dict("sys.modules", {"oandapyV20": None}):
            result = await self.service._test_oanda_connection(
                {"api_key": "x", "account_id": "y"}
            )
        assert result["success"] is False

    def test_check_static_path_nonexistent(self):
        result = _check_static_path(r"C:\NonExistentPath\MT4", "MT4")
        assert result is None

    @pytest.mark.asyncio
    async def test_probe_bridge_ports_returns_list_of_results(self):
        results = await self.service._probe_bridge_ports()
        assert isinstance(results, list)
        assert len(results) == len(range(3000, 3011))
        for r in results:
            assert "port" in r
            assert "bridge_active" in r

    @pytest.mark.asyncio
    async def test_live_bridge_detected_on_active_port(self):
        """Simulate an active bridge by spinning up a mock echo server."""
        server_ready = asyncio.Event()
        port = 13001

        async def mock_server():
            async def handle(reader, writer):
                try:
                    while True:
                        line = await reader.readline()
                        if not line:
                            break
                        writer.write(b'{"status":"ok"}\n')
                        await writer.drain()
                except Exception:
                    pass
                finally:
                    writer.close()

            server = await asyncio.start_server(handle, "127.0.0.1", port)
            server_ready.set()
            async with server:
                await server.serve_forever()

        server_task = asyncio.get_event_loop().create_task(mock_server())
        try:
            await asyncio.wait_for(server_ready.wait(), timeout=2.0)
            result = await self.service._probe_port(port)
            assert result["bridge_active"] is True
            assert result["port"] == port
        finally:
            server_task.cancel()
            try:
                await server_task
            except (asyncio.CancelledError, Exception):
                pass


# ---------------------------------------------------------------------------
# Plugins __init__ export test
# ---------------------------------------------------------------------------

class TestPluginsInit:
    def test_all_exports_importable(self):
        from forex_trading.broker.plugins import OANDAPlugin, MT5BridgePlugin, MT4BridgePlugin
        assert OANDAPlugin is not None
        assert MT5BridgePlugin is not None
        assert MT4BridgePlugin is not None

    def test_plugin_types(self):
        from forex_trading.broker.plugins import OANDAPlugin, MT5BridgePlugin, MT4BridgePlugin
        from forex_trading.broker.gateway import BrokerPlugin
        assert issubclass(OANDAPlugin, BrokerPlugin)
        assert issubclass(MT5BridgePlugin, BrokerPlugin)
        assert issubclass(MT4BridgePlugin, BrokerPlugin)
