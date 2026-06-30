"""WebSocket notification channel - broadcasts to connected clients."""

import asyncio
import json
from dataclasses import asdict
from typing import Any

import structlog

from forex_trading.notifications.channels.base import BaseNotificationChannel
from forex_trading.notifications.domain.models import NotificationMessage

logger = structlog.get_logger()


class WebSocketNotificationChannel(BaseNotificationChannel):
    """
    Pushes notifications to all currently connected WebSocket clients.

    Clients register themselves by calling `add_connection`. The channel
    fans out to every registered writer coroutine and removes stale ones
    on failure.
    """

    def __init__(self) -> None:
        # Each item is a coroutine/callable that accepts a JSON string payload
        self._connections: list[Any] = []
        self._lock = asyncio.Lock()

    @property
    def channel_name(self) -> str:
        return "websocket"

    def add_connection(self, send_fn: Any) -> None:
        """Register a WebSocket send function (async callable accepting str)."""
        self._connections.append(send_fn)
        logger.debug("websocket_client_added", total=len(self._connections))

    def remove_connection(self, send_fn: Any) -> None:
        """Unregister a WebSocket send function."""
        try:
            self._connections.remove(send_fn)
        except ValueError:
            pass
        logger.debug("websocket_client_removed", total=len(self._connections))

    async def send(self, message: NotificationMessage) -> bool:
        if not self._connections:
            logger.debug("websocket_no_clients", title=message.title)
            return True

        payload = json.dumps(
            {
                "type": "notification",
                "title": message.title,
                "body": message.body,
                "priority": message.priority.value,
                "category": message.category,
                "data": message.data,
                "timestamp": message.timestamp.isoformat(),
            }
        )

        stale: list[Any] = []
        sent = 0

        async with self._lock:
            for send_fn in list(self._connections):
                try:
                    await send_fn(payload)
                    sent += 1
                except Exception as exc:
                    logger.warning("websocket_send_error", error=str(exc))
                    stale.append(send_fn)

            for fn in stale:
                try:
                    self._connections.remove(fn)
                except ValueError:
                    pass

        logger.info(
            "websocket_notification_sent",
            title=message.title,
            sent=sent,
            stale_removed=len(stale),
        )
        return sent > 0 or len(self._connections) == 0

    def connection_count(self) -> int:
        return len(self._connections)
