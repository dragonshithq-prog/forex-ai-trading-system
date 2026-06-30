"""Unit tests for Notification System."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from forex_trading.notifications.domain.models import NotificationMessage, NotificationPriority
from forex_trading.notifications.channels.base import BaseNotificationChannel
from forex_trading.notifications.channels.websocket_channel import WebSocketNotificationChannel
from forex_trading.notifications.channels.slack import SlackChannel, _PRIORITY_COLORS
from forex_trading.notifications.channels.telegram import TelegramChannel, _escape_md
from forex_trading.notifications.channels.email import EmailChannel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_message(
    title: str = "Test",
    body: str = "Test body",
    priority: NotificationPriority = NotificationPriority.MEDIUM,
    category: str = "system",
) -> NotificationMessage:
    return NotificationMessage(
        title=title,
        body=body,
        priority=priority,
        category=category,
        data={"key": "value"},
        timestamp=datetime(2024, 6, 1, 12, 0, 0),
    )


# ---------------------------------------------------------------------------
# NotificationMessage
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNotificationMessage:
    def test_default_timestamp_is_utcnow(self):
        before = datetime.utcnow()
        msg = NotificationMessage(
            title="T", body="B",
            priority=NotificationPriority.LOW,
            category="system",
        )
        after = datetime.utcnow()
        assert before <= msg.timestamp <= after

    def test_data_default_factory(self):
        m1 = NotificationMessage("T", "B", NotificationPriority.LOW, "system")
        m2 = NotificationMessage("T", "B", NotificationPriority.LOW, "system")
        m1.data["x"] = 1
        assert "x" not in m2.data

    def test_priority_enum_values(self):
        assert NotificationPriority.CRITICAL.value == "critical"
        assert NotificationPriority.LOW.value == "low"


# ---------------------------------------------------------------------------
# WebSocketNotificationChannel
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestWebSocketChannel:
    async def test_no_connections_returns_true(self):
        ch = WebSocketNotificationChannel()
        result = await ch.send(_make_message())
        assert result is True

    async def test_sends_json_to_connection(self):
        ch = WebSocketNotificationChannel()
        received = []

        async def mock_send(payload: str):
            received.append(json.loads(payload))

        ch.add_connection(mock_send)
        msg = _make_message(title="Alert", body="Something happened")
        await ch.send(msg)

        assert len(received) == 1
        assert received[0]["title"] == "Alert"
        assert received[0]["body"] == "Something happened"
        assert received[0]["type"] == "notification"

    async def test_stale_connection_removed(self):
        ch = WebSocketNotificationChannel()
        call_count = 0

        async def failing_send(payload):
            raise ConnectionResetError("client gone")

        ch.add_connection(failing_send)
        assert ch.connection_count() == 1

        await ch.send(_make_message())
        assert ch.connection_count() == 0

    async def test_multiple_connections_all_receive(self):
        ch = WebSocketNotificationChannel()
        received = [[], []]

        async def s1(p):
            received[0].append(p)

        async def s2(p):
            received[1].append(p)

        ch.add_connection(s1)
        ch.add_connection(s2)

        await ch.send(_make_message())
        assert len(received[0]) == 1
        assert len(received[1]) == 1

    async def test_add_remove_connection(self):
        ch = WebSocketNotificationChannel()

        async def fn(p):
            pass

        ch.add_connection(fn)
        assert ch.connection_count() == 1
        ch.remove_connection(fn)
        assert ch.connection_count() == 0

    async def test_channel_name(self):
        ch = WebSocketNotificationChannel()
        assert ch.channel_name == "websocket"

    async def test_payload_contains_priority(self):
        ch = WebSocketNotificationChannel()
        captured = []

        async def capture(payload):
            captured.append(json.loads(payload))

        ch.add_connection(capture)
        msg = _make_message(priority=NotificationPriority.CRITICAL)
        await ch.send(msg)
        assert captured[0]["priority"] == "critical"

    async def test_payload_contains_category(self):
        ch = WebSocketNotificationChannel()
        captured = []

        async def capture(payload):
            captured.append(json.loads(payload))

        ch.add_connection(capture)
        msg = _make_message(category="risk_alert")
        await ch.send(msg)
        assert captured[0]["category"] == "risk_alert"


# ---------------------------------------------------------------------------
# SlackChannel
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSlackChannelInit:
    def test_empty_webhook_raises(self):
        with pytest.raises(ValueError, match="webhook_url"):
            SlackChannel(webhook_url="")

    def test_channel_name(self):
        ch = SlackChannel(webhook_url="https://hooks.slack.com/services/test")
        assert ch.channel_name == "slack"

    def test_priority_colors_defined(self):
        assert NotificationPriority.CRITICAL in _PRIORITY_COLORS
        assert NotificationPriority.LOW in _PRIORITY_COLORS


@pytest.mark.unit
@pytest.mark.asyncio
class TestSlackChannelSend:
    async def test_success_returns_true(self):
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("forex_trading.notifications.channels.slack.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            ch = SlackChannel(webhook_url="https://hooks.slack.com/test")
            result = await ch.send(_make_message(priority=NotificationPriority.HIGH))

        assert result is True

    async def test_http_error_returns_false(self):
        import httpx
        with patch("forex_trading.notifications.channels.slack.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "bad request"
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=mock_response)
            )
            mock_client_cls.return_value = mock_client

            ch = SlackChannel(webhook_url="https://hooks.slack.com/test")
            result = await ch.send(_make_message())

        assert result is False

    async def test_network_error_returns_false(self):
        with patch("forex_trading.notifications.channels.slack.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=ConnectionError("network error"))
            mock_client_cls.return_value = mock_client

            ch = SlackChannel(webhook_url="https://hooks.slack.com/test")
            result = await ch.send(_make_message())

        assert result is False


# ---------------------------------------------------------------------------
# TelegramChannel
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTelegramChannelInit:
    def test_empty_token_raises(self):
        with pytest.raises(ValueError, match="bot_token"):
            TelegramChannel(bot_token="", chat_id="123")

    def test_empty_chat_id_raises(self):
        with pytest.raises(ValueError, match="chat_id"):
            TelegramChannel(bot_token="token123", chat_id="")

    def test_channel_name(self):
        ch = TelegramChannel(bot_token="abc", chat_id="123")
        assert ch.channel_name == "telegram"

    def test_api_url_format(self):
        ch = TelegramChannel(bot_token="mytoken", chat_id="123")
        assert "mytoken" in ch._api_url


@pytest.mark.unit
class TestEscapeMarkdown:
    def test_escapes_special_chars(self):
        result = _escape_md("Hello [world]!")
        assert r"\[" in result
        assert r"\!" in result

    def test_plain_text_unchanged(self):
        result = _escape_md("hello world")
        assert result == "hello world"


@pytest.mark.unit
@pytest.mark.asyncio
class TestTelegramChannelSend:
    async def test_success_returns_true(self):
        with patch("forex_trading.notifications.channels.telegram.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value={"ok": True, "result": {}})
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            ch = TelegramChannel(bot_token="token", chat_id="123")
            result = await ch.send(_make_message())

        assert result is True

    async def test_telegram_error_returns_false(self):
        with patch("forex_trading.notifications.channels.telegram.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value={"ok": False, "description": "Forbidden"})
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            ch = TelegramChannel(bot_token="token", chat_id="123")
            result = await ch.send(_make_message())

        assert result is False

    async def test_network_error_returns_false(self):
        with patch("forex_trading.notifications.channels.telegram.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=OSError("network failure"))
            mock_client_cls.return_value = mock_client

            ch = TelegramChannel(bot_token="token", chat_id="123")
            result = await ch.send(_make_message())

        assert result is False


# ---------------------------------------------------------------------------
# EmailChannel
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEmailChannelInit:
    def test_empty_host_raises(self):
        with pytest.raises(ValueError, match="smtp_host"):
            EmailChannel(smtp_host="", smtp_port=587, from_address="a@b.com", to_addresses=["c@d.com"])

    def test_empty_from_raises(self):
        with pytest.raises(ValueError, match="from_address"):
            EmailChannel(smtp_host="smtp.example.com", smtp_port=587, from_address="", to_addresses=["c@d.com"])

    def test_empty_to_raises(self):
        with pytest.raises(ValueError, match="to_addresses"):
            EmailChannel(smtp_host="smtp.example.com", smtp_port=587, from_address="a@b.com", to_addresses=[])

    def test_channel_name(self):
        ch = EmailChannel("host", 587, "a@b.com", ["c@d.com"])
        assert ch.channel_name == "email"


@pytest.mark.unit
@pytest.mark.asyncio
class TestEmailChannelSend:
    async def test_success_returns_true(self):
        with patch("forex_trading.notifications.channels.email.aiosmtplib.SMTP") as mock_smtp_cls:
            mock_smtp = AsyncMock()
            mock_smtp.connect = AsyncMock()
            mock_smtp.login = AsyncMock()
            mock_smtp.send_message = AsyncMock()
            mock_smtp.quit = AsyncMock()
            mock_smtp_cls.return_value = mock_smtp

            ch = EmailChannel(
                smtp_host="smtp.example.com",
                smtp_port=587,
                from_address="bot@example.com",
                to_addresses=["trader@example.com"],
                username="user",
                password="pass",
            )
            result = await ch.send(_make_message())

        assert result is True

    async def test_smtp_error_returns_false(self):
        import aiosmtplib
        with patch("forex_trading.notifications.channels.email.aiosmtplib.SMTP") as mock_smtp_cls:
            mock_smtp = AsyncMock()
            mock_smtp.connect = AsyncMock(side_effect=aiosmtplib.SMTPConnectError("Connection refused"))
            mock_smtp_cls.return_value = mock_smtp

            ch = EmailChannel("smtp.example.com", 587, "a@b.com", ["c@d.com"])
            result = await ch.send(_make_message())

        assert result is False

    def test_mime_build_contains_title(self):
        ch = EmailChannel("smtp.example.com", 587, "a@b.com", ["c@d.com"])
        msg = _make_message(title="Critical Alert")
        mime = ch._build_mime(msg, "[CRITICAL] Critical Alert")
        assert mime["Subject"] == "[CRITICAL] Critical Alert"


# ---------------------------------------------------------------------------
# NotificationManager
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestNotificationManager:
    def _make_manager_no_channels(self):
        """Create a manager with no real channels configured."""
        with patch("forex_trading.notifications.manager.get_settings") as mock_settings:
            settings = MagicMock()
            settings.SLACK_WEBHOOK_URL = None
            settings.TELEGRAM_BOT_TOKEN = None
            settings.TELEGRAM_CHAT_ID = None
            settings.EMAIL_SMTP_HOST = None
            settings.EMAIL_FROM = None
            mock_settings.return_value = settings

            from forex_trading.notifications.manager import NotificationManager
            return NotificationManager()

    async def test_notify_no_channels_returns_empty(self):
        mgr = self._make_manager_no_channels()
        result = await mgr.notify(_make_message())
        assert result == {}

    async def test_register_channel_increases_count(self):
        mgr = self._make_manager_no_channels()
        ws_ch = WebSocketNotificationChannel()
        mgr.register_channel(ws_ch)
        assert mgr.channel_count() == 1

    async def test_notify_dispatches_to_registered_channel(self):
        mgr = self._make_manager_no_channels()
        received = []

        async def mock_send(payload):
            received.append(payload)

        ws_ch = WebSocketNotificationChannel()
        ws_ch.add_connection(mock_send)
        mgr.register_channel(ws_ch)

        await mgr.notify(_make_message(title="Test dispatch"))
        assert len(received) == 1

    async def test_channel_filter_targets_specific(self):
        mgr = self._make_manager_no_channels()

        # Add two channels
        ws1 = WebSocketNotificationChannel()
        ws1._channel_name = "ws_primary"

        class _NamedWS(WebSocketNotificationChannel):
            @property
            def channel_name(self):
                return "ws_secondary"

        ws2 = _NamedWS()
        ws2_received = []

        async def fn2(p):
            ws2_received.append(p)

        ws2.add_connection(fn2)
        ws1_received = []

        async def fn1(p):
            ws1_received.append(p)

        ws1.add_connection(fn1)

        mgr.register_channel(ws1)
        mgr.register_channel(ws2)

        # Only target ws_secondary
        await mgr.notify(_make_message(), channels=["ws_secondary"])
        assert len(ws2_received) == 1
        assert len(ws1_received) == 0

    async def test_rate_limiting_blocks_excess(self):
        mgr = self._make_manager_no_channels()
        ws_ch = WebSocketNotificationChannel()
        received = []

        async def fn(p):
            received.append(p)

        ws_ch.add_connection(fn)
        mgr.register_channel(ws_ch)

        # Exhaust the LOW priority rate limit (5 per minute)
        msg = _make_message(priority=NotificationPriority.LOW)
        for _ in range(5):
            await mgr.notify(msg)
        # 6th should be rate-limited
        result = await mgr.notify(msg)
        assert result.get("websocket") is False

    async def test_critical_priority_high_rate_limit(self):
        mgr = self._make_manager_no_channels()
        ws_ch = WebSocketNotificationChannel()
        received = []

        async def fn(p):
            received.append(p)

        ws_ch.add_connection(fn)
        mgr.register_channel(ws_ch)

        msg = _make_message(priority=NotificationPriority.CRITICAL)
        # Send 50 critical messages - all should go through
        for _ in range(50):
            result = await mgr.notify(msg)
            assert result.get("websocket") is True

    async def test_notify_trade_executed(self):
        mgr = self._make_manager_no_channels()
        ws_ch = WebSocketNotificationChannel()
        received = []

        async def fn(p):
            received.append(json.loads(p))

        ws_ch.add_connection(fn)
        mgr.register_channel(ws_ch)

        await mgr.notify_trade_executed({
            "symbol": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "size": 0.1,
            "pnl": 50.0,
        })

        assert len(received) == 1
        assert "EURUSD" in received[0]["title"]
        assert received[0]["category"] == "trade_executed"

    async def test_notify_circuit_breaker(self):
        mgr = self._make_manager_no_channels()
        ws_ch = WebSocketNotificationChannel()
        received = []

        async def fn(p):
            received.append(json.loads(p))

        ws_ch.add_connection(fn)
        mgr.register_channel(ws_ch)

        await mgr.notify_circuit_breaker("Daily drawdown exceeded 3%")
        assert len(received) == 1
        assert received[0]["priority"] == "critical"
        assert "CIRCUIT BREAKER" in received[0]["title"]

    async def test_notify_error(self):
        mgr = self._make_manager_no_channels()
        ws_ch = WebSocketNotificationChannel()
        received = []

        async def fn(p):
            received.append(json.loads(p))

        ws_ch.add_connection(fn)
        mgr.register_channel(ws_ch)

        await mgr.notify_error("DB connection failed", {"host": "localhost", "port": 5432})
        assert len(received) == 1
        assert received[0]["category"] == "system"

    async def test_channel_exception_does_not_crash(self):
        """A channel that raises should not crash the manager."""
        mgr = self._make_manager_no_channels()

        class _BrokenChannel(BaseNotificationChannel):
            @property
            def channel_name(self):
                return "broken"

            async def send(self, message):
                raise RuntimeError("broken always fails")

        mgr.register_channel(_BrokenChannel())

        result = await mgr.notify(_make_message())
        assert result.get("broken") is False  # failure captured, no crash
