"""Telegram notification channel using Bot API."""

import structlog

import httpx

from forex_trading.notifications.channels.base import BaseNotificationChannel
from forex_trading.notifications.domain.models import NotificationMessage, NotificationPriority

logger = structlog.get_logger()

_PRIORITY_PREFIX = {
    NotificationPriority.LOW: "ℹ️",
    NotificationPriority.MEDIUM: "🔔",
    NotificationPriority.HIGH: "⚠️",
    NotificationPriority.CRITICAL: "🚨",
}

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramChannel(BaseNotificationChannel):
    """Delivers notifications via Telegram Bot API with Markdown formatting."""

    def __init__(self, bot_token: str, chat_id: str, timeout: float = 10.0) -> None:
        if not bot_token:
            raise ValueError("bot_token must not be empty")
        if not chat_id:
            raise ValueError("chat_id must not be empty")
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timeout = timeout
        self._api_url = _TELEGRAM_API.format(token=bot_token)

    @property
    def channel_name(self) -> str:
        return "telegram"

    async def send(self, message: NotificationMessage) -> bool:
        prefix = _PRIORITY_PREFIX.get(message.priority, "🔔")
        ts_str = message.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        text = (
            f"{prefix} *{_escape_md(message.title)}*\n\n"
            f"{_escape_md(message.body)}\n\n"
            f"_Category: {_escape_md(message.category)} | "
            f"Priority: {message.priority.value.upper()} | "
            f"{ts_str}_"
        )

        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._api_url, json=payload)
                data = response.json()
                if not data.get("ok"):
                    logger.error(
                        "telegram_notification_failed",
                        title=message.title,
                        telegram_error=data.get("description", "unknown"),
                    )
                    return False
                logger.info("telegram_notification_sent", title=message.title)
                return True
        except Exception as exc:
            logger.error("telegram_notification_error", title=message.title, error=str(exc))
            return False


def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in text)
