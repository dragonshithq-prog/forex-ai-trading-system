"""Notification Manager - multi-channel notification dispatcher."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from forex_trading.config import get_settings
from forex_trading.notifications.channels.base import BaseNotificationChannel
from forex_trading.notifications.domain.models import NotificationMessage, NotificationPriority

if TYPE_CHECKING:
    from forex_trading.risk.engine import RiskAlert

logger = structlog.get_logger()
settings = get_settings()


class NotificationManager:
    """
    Multi-channel notification dispatcher.

    Dispatches messages to all enabled channels concurrently and returns
    a per-channel success map. Includes rate limiting (per-channel bucket)
    and priority-based channel filtering.
    """

    _RATE_LIMIT_WINDOW_SECONDS = 60
    _RATE_LIMITS_BY_PRIORITY: dict[NotificationPriority, int] = {
        NotificationPriority.LOW: 5,
        NotificationPriority.MEDIUM: 10,
        NotificationPriority.HIGH: 20,
        NotificationPriority.CRITICAL: 100,  # effectively unlimited
    }

    def __init__(self) -> None:
        self._channels: list[BaseNotificationChannel] = []
        self._rate_buckets: dict[str, list[datetime]] = {}
        self._setup_channels()

    def _setup_channels(self) -> None:
        """Configure channels from settings. Channels with missing credentials are skipped."""
        from forex_trading.notifications.channels.slack import SlackChannel
        from forex_trading.notifications.channels.telegram import TelegramChannel
        from forex_trading.notifications.channels.email import EmailChannel

        if settings.SLACK_WEBHOOK_URL:
            try:
                self.register_channel(SlackChannel(webhook_url=settings.SLACK_WEBHOOK_URL))
            except Exception as exc:
                logger.warning("slack_channel_setup_failed", error=str(exc))

        if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
            try:
                self.register_channel(
                    TelegramChannel(
                        bot_token=settings.TELEGRAM_BOT_TOKEN,
                        chat_id=settings.TELEGRAM_CHAT_ID,
                    )
                )
            except Exception as exc:
                logger.warning("telegram_channel_setup_failed", error=str(exc))

        if (
            settings.EMAIL_SMTP_HOST
            and settings.EMAIL_FROM
        ):
            try:
                self.register_channel(
                    EmailChannel(
                        smtp_host=settings.EMAIL_SMTP_HOST,
                        smtp_port=settings.EMAIL_SMTP_PORT,
                        from_address=settings.EMAIL_FROM,
                        to_addresses=[settings.EMAIL_FROM],
                    )
                )
            except Exception as exc:
                logger.warning("email_channel_setup_failed", error=str(exc))

    def register_channel(self, channel: BaseNotificationChannel) -> None:
        """Register a notification channel."""
        self._channels.append(channel)
        logger.info("notification_channel_registered", channel=channel.channel_name)

    async def notify(
        self,
        message: NotificationMessage,
        channels: list[str] | None = None,
    ) -> dict[str, bool]:
        """
        Dispatch a notification to all (or specified) enabled channels concurrently.

        Args:
            message: The notification to send.
            channels: Optional list of channel names to target. None = all registered.

        Returns:
            Mapping of channel_name -> success bool.
        """
        targets = [
            ch for ch in self._channels
            if channels is None or ch.channel_name in channels
        ]

        if not targets:
            logger.warning("notify_no_channels", title=message.title)
            return {}

        results: dict[str, bool] = {}

        async def _send_one(ch: BaseNotificationChannel) -> tuple[str, bool]:
            if self._is_rate_limited(ch.channel_name, message.priority):
                logger.warning("notification_rate_limited", channel=ch.channel_name)
                return ch.channel_name, False
            try:
                ok = await ch.send(message)
            except Exception as exc:
                logger.error(
                    "notification_channel_exception",
                    channel=ch.channel_name,
                    error=str(exc),
                )
                ok = False
            self._record_send(ch.channel_name)
            return ch.channel_name, ok

        coros = [_send_one(ch) for ch in targets]
        outcomes = await asyncio.gather(*coros, return_exceptions=False)

        for name, ok in outcomes:
            results[name] = ok

        logger.info(
            "notification_dispatched",
            title=message.title,
            priority=message.priority.value,
            results=results,
        )
        return results

    async def notify_trade_executed(self, trade_details: dict) -> None:
        symbol = trade_details.get("symbol", "N/A")
        direction = trade_details.get("direction", "N/A")
        price = trade_details.get("entry_price", 0.0)
        size = trade_details.get("size", 0.0)
        pnl = trade_details.get("pnl")

        pnl_str = f"  |  P&L: {pnl:+.2f}" if pnl is not None else ""
        message = NotificationMessage(
            title=f"Trade Executed: {symbol} {direction.upper()}",
            body=(
                f"Symbol: {symbol}\n"
                f"Direction: {direction.upper()}\n"
                f"Entry price: {price}\n"
                f"Size: {size} lots{pnl_str}"
            ),
            priority=NotificationPriority.HIGH,
            category="trade_executed",
            data=trade_details,
        )
        await self.notify(message)

    async def notify_risk_alert(self, alert: "RiskAlert") -> None:
        from forex_trading.risk.engine import RiskLevel

        priority = (
            NotificationPriority.CRITICAL
            if alert.level == RiskLevel.CRITICAL
            else NotificationPriority.HIGH
        )
        message = NotificationMessage(
            title=f"Risk Alert [{alert.level.value.upper()}]: {alert.category}",
            body=(
                f"{alert.message}\n"
                f"Current value: {alert.current_value:.4f}\n"
                f"Threshold: {alert.threshold_value:.4f}"
            ),
            priority=priority,
            category="risk_alert",
            data={
                "level": alert.level.value,
                "category": alert.category,
                "current_value": alert.current_value,
                "threshold_value": alert.threshold_value,
            },
        )
        await self.notify(message)

    async def notify_signal_generated(self, signal: dict) -> None:
        symbol = signal.get("symbol", "N/A")
        direction = signal.get("direction", "N/A")
        confidence = signal.get("confidence", 0.0)
        message = NotificationMessage(
            title=f"Signal: {symbol} {direction.upper()} ({confidence:.0%})",
            body=(
                f"Symbol: {symbol}\n"
                f"Direction: {direction.upper()}\n"
                f"Confidence: {confidence:.1%}\n"
                f"Entry: {signal.get('entry_price', 'N/A')}\n"
                f"SL: {signal.get('stop_loss', 'N/A')}  |  TP: {signal.get('take_profit', 'N/A')}"
            ),
            priority=NotificationPriority.MEDIUM,
            category="signal",
            data=signal,
        )
        await self.notify(message)

    async def notify_circuit_breaker(self, reason: str) -> None:
        message = NotificationMessage(
            title="CIRCUIT BREAKER ACTIVATED",
            body=(
                f"Trading has been halted automatically.\n\n"
                f"Reason: {reason}\n\n"
                f"All new orders are blocked until the circuit breaker is reset."
            ),
            priority=NotificationPriority.CRITICAL,
            category="system",
            data={"reason": reason},
        )
        await self.notify(message)

    async def notify_error(self, error: str, context: dict) -> None:
        context_str = "\n".join(f"  {k}: {v}" for k, v in context.items())
        message = NotificationMessage(
            title="System Error",
            body=f"Error: {error}\n\nContext:\n{context_str}",
            priority=NotificationPriority.HIGH,
            category="system",
            data={"error": error, "context": context},
        )
        await self.notify(message)

    def _is_rate_limited(self, channel_name: str, priority: NotificationPriority) -> bool:
        bucket = self._rate_buckets.get(channel_name, [])
        cutoff = datetime.utcnow() - timedelta(seconds=self._RATE_LIMIT_WINDOW_SECONDS)
        recent = [ts for ts in bucket if ts > cutoff]
        self._rate_buckets[channel_name] = recent
        limit = self._RATE_LIMITS_BY_PRIORITY.get(priority, 10)
        return len(recent) >= limit

    def _record_send(self, channel_name: str) -> None:
        if channel_name not in self._rate_buckets:
            self._rate_buckets[channel_name] = []
        self._rate_buckets[channel_name].append(datetime.utcnow())

    def channel_count(self) -> int:
        return len(self._channels)
