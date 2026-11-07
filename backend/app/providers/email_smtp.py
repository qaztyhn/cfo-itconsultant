"""EmailProvider qua SMTP: Mailpit (local), Brevo/Resend free (staging). Không gửi email thật ngoài
cấu hình staging (09 mục 13).

Owner: Dev 2 (luồng B) — M7.
"""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage


class EmailDeliveryError(RuntimeError):
    """Sanitized transport failure; retry policy belongs to outbox."""


class SmtpEmailProvider:
    """SMTP transport only; caller must enforce shadow mode/consent/dedupe/outbox."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        sender: str,
        app_env: str = "local",
        username: str | None = None,
        password: str | None = None,
        starttls: bool = False,
        timeout_seconds: float = 10,
    ) -> None:
        if app_env != "staging" and host not in {
            "mailpit",
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("Non-staging SMTP must target a local inbox")
        if not 0 < timeout_seconds < float("inf") or not 0 < port < 65536:
            raise ValueError("Invalid SMTP connection limits")
        if username and not starttls:
            raise ValueError("Authenticated SMTP requires STARTTLS")
        self._host, self._port, self._sender = host, port, sender
        self._username, self._password = username, password
        self._tls, self._timeout = starttls, timeout_seconds

    async def send(self, *, recipient: str, subject: str, text: str, html: str | None = None) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = (
            self._sender,
            recipient,
            subject,
        )
        message.set_content(text)
        if html is not None:
            message.add_alternative(html, subtype="html")
        await asyncio.to_thread(self._send, message)

    def _send(self, message: EmailMessage) -> None:
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._tls:
                    smtp.starttls(context=ssl.create_default_context())
                if self._username:
                    smtp.login(self._username, self._password or "")
                refused = smtp.send_message(message)
                if refused:
                    raise EmailDeliveryError("SMTP delivery failed")
        except (smtplib.SMTPException, OSError):
            raise EmailDeliveryError("SMTP delivery failed") from None
