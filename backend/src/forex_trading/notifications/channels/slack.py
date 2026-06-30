"""Slack notification channel using Block Kit."""

import structlog

import httpx

from forex_trading.notifications.channels.base import BaseNotificationChannel
from forex_trading.notifications.domain.models import NotificationMessage, NotificationPriority

logger = structlog.get_logger()

_PRIORITY_COLORS = {
    NotificationPriority.LOW: "#36a64f",
    NotificationPriority.MEDIUM: "#ffcc00",
    NotificationPriority.HIGH: "#ff9900",
    NotificationPriority.CRITICAL: "#ff0000",
}

_PRIORITY_EMOJIS = {
    NotificationPriority.LOW: ":white_check_mark:",
    NotificationPriority.MEDIUM: ":information_source:",
    NotificationPriority.HIGH: ":warning:",
    NotificationPriority.CRITICAL: ":rotating_light:",
}


class SlackChannel(BaseNotificationChannel):
    """Delivers notifications to Slack via Incoming Webhooks using Block Kit."""

    def __init__(self, webhook_url: str, timeout: float = 10.0) -> None:
        if not webhook_url:
            raise ValueError("webhook_url must not be empty")
        self._webhook_url = webhook_url
        self._timeout = timeout

    @property
    def channel_name(self) -> str:
        return "slack"

    async def send(self, message: NotificationMessage) -> bool:
        color = _PRIORITY_COLORS.get(message.priority, "#36a64f")
        emoji = _PRIORITY_EMOJIS.get(message.priority, ":bell:")
        ts_str = message.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"{emoji}  {message.title}",
                                "emoji": True,
                            },
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": message.body},
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": (
                                        f"*Category:* {message.category}  |  "
                                        f"*Priority:* {message.priority.value.upper()}  |  "
                                        f"*Time:* {ts_str}"
                                    ),
                                }
                            ],
                        },
                    ],
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._webhook_url, json=payload)
                response.raise_for_status()
                logger.info("slack_notification_sent", title=message.title, status=response.status_code)
                return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                "slack_notification_failed",
                title=message.title,
                status=exc.response.status_code,
                detail=exc.response.text[:200],
            )
            return False
        except Exception as exc:
            logger.error("slack_notification_error", title=message.title, error=str(exc))
            return False
