"""Email notification channel using aiosmtplib."""

import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog

from forex_trading.notifications.channels.base import BaseNotificationChannel
from forex_trading.notifications.domain.models import NotificationMessage, NotificationPriority

logger = structlog.get_logger()

_PRIORITY_SUBJECT_PREFIX = {
    NotificationPriority.LOW: "[INFO]",
    NotificationPriority.MEDIUM: "[NOTICE]",
    NotificationPriority.HIGH: "[WARNING]",
    NotificationPriority.CRITICAL: "[CRITICAL]",
}

_PRIORITY_BG_COLOR = {
    NotificationPriority.LOW: "#d4edda",
    NotificationPriority.MEDIUM: "#fff3cd",
    NotificationPriority.HIGH: "#ffe0b2",
    NotificationPriority.CRITICAL: "#f8d7da",
}


class EmailChannel(BaseNotificationChannel):
    """Delivers notifications via async SMTP using aiosmtplib."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        from_address: str,
        to_addresses: list[str],
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout: float = 15.0,
    ) -> None:
        if not smtp_host:
            raise ValueError("smtp_host must not be empty")
        if not from_address:
            raise ValueError("from_address must not be empty")
        if not to_addresses:
            raise ValueError("to_addresses must not be empty")
        self._host = smtp_host
        self._port = smtp_port
        self._from = from_address
        self._to = to_addresses
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._timeout = timeout

    @property
    def channel_name(self) -> str:
        return "email"

    async def send(self, message: NotificationMessage) -> bool:
        prefix = _PRIORITY_SUBJECT_PREFIX.get(message.priority, "[NOTICE]")
        subject = f"{prefix} Forex Trading - {message.title}"

        mime_message = self._build_mime(message, subject)

        try:
            smtp = aiosmtplib.SMTP(
                hostname=self._host,
                port=self._port,
                use_tls=self._use_tls,
                timeout=self._timeout,
            )
            await smtp.connect()
            if self._username and self._password:
                await smtp.login(self._username, self._password)
            await smtp.send_message(mime_message)
            await smtp.quit()
            logger.info("email_notification_sent", title=message.title, recipients=len(self._to))
            return True
        except (aiosmtplib.SMTPException, asyncio.TimeoutError, OSError) as exc:
            logger.error("email_notification_failed", title=message.title, error=str(exc))
            return False

    def _build_mime(self, message: NotificationMessage, subject: str) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = ", ".join(self._to)

        bg_color = _PRIORITY_BG_COLOR.get(message.priority, "#fff3cd")
        ts_str = message.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        text_part = MIMEText(
            f"{message.title}\n\n{message.body}\n\nCategory: {message.category}\n"
            f"Priority: {message.priority.value.upper()}\nTime: {ts_str}",
            "plain",
        )
        html_part = MIMEText(
            f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;margin:0;padding:20px;">
<div style="max-width:600px;margin:auto;border:1px solid #dee2e6;border-radius:6px;overflow:hidden;">
  <div style="background:{bg_color};padding:16px 20px;">
    <h2 style="margin:0;font-size:18px;">{message.title}</h2>
  </div>
  <div style="padding:20px;">
    <p style="white-space:pre-wrap;">{message.body}</p>
    <hr style="border:none;border-top:1px solid #dee2e6;"/>
    <small style="color:#6c757d;">
      Category: <strong>{message.category}</strong> &nbsp;|&nbsp;
      Priority: <strong>{message.priority.value.upper()}</strong> &nbsp;|&nbsp;
      {ts_str}
    </small>
  </div>
</div>
</body></html>""",
            "html",
        )
        msg.attach(text_part)
        msg.attach(html_part)
        return msg
