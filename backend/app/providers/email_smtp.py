"""EmailProvider qua SMTP: Mailpit (local), Brevo/Resend free (staging). Không gửi email thật ngoài
cấu hình staging (09 mục 13).

DEC-NOTIFY-001: ở staging (SMTP bên ngoài), người nhận chỉ được thuộc các miền thử nghiệm trong
`allowed_recipient_domains` (mặc định `test`); địa chỉ khác bị từ chối TRƯỚC khi mở kết nối SMTP. Không gửi
email cho khách thật khi chưa có chống trùng/đối soát.

Owner: Dev 2 (luồng B) — M7.
"""

import asyncio
import smtplib
import ssl
from collections.abc import Iterable
from email.message import EmailMessage
from email.utils import getaddresses


class EmailDeliveryError(RuntimeError):
    """Sanitized transport failure; retry policy belongs to outbox."""


class EmailRecipientNotAllowed(EmailDeliveryError):
    """Recipient outside the test domains allowed for this environment; never retried."""


LOCAL_HOSTS = frozenset({"mailpit", "localhost", "127.0.0.1", "::1"})


def normalize_domains(domains: Iterable[str]) -> frozenset[str]:
    """`"test, cfo.demo"` items → {"test", "cfo.demo"}; lowercase, no leading dot/@."""
    return frozenset(d.strip().lower().lstrip("@.") for d in domains if d.strip().lstrip("@."))


def recipient_allowed(recipient: str, domains: frozenset[str]) -> bool:
    """Exactly one plain address whose domain equals or is a subdomain of an allowed domain."""
    if any(c in recipient for c in "\r\n,;"):
        return False
    parsed = getaddresses([recipient])
    if len(parsed) != 1:
        return False
    address = parsed[0][1]
    if address.count("@") != 1:
        return False
    local, domain = address.rsplit("@", 1)
    domain = domain.lower().rstrip(".")
    if not local or not domain:
        return False
    return any(domain == d or domain.endswith("." + d) for d in domains)


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
        allowed_recipient_domains: Iterable[str] = ("test",),
    ) -> None:
        if app_env != "staging" and host not in LOCAL_HOSTS:
            raise ValueError("Non-staging SMTP must target a local inbox")
        # Mailpit/localhost keeps every message in a local inbox; any other host can reach real people.
        self._allowed: frozenset[str] | None = None
        if host not in LOCAL_HOSTS:
            self._allowed = normalize_domains(allowed_recipient_domains)
            if not self._allowed:
                raise ValueError("External SMTP requires allowed test recipient domains")
        if not 0 < timeout_seconds < float("inf") or not 0 < port < 65536:
            raise ValueError("Invalid SMTP connection limits")
        if username and not starttls:
            raise ValueError("Authenticated SMTP requires STARTTLS")
        self._host, self._port, self._sender = host, port, sender
        self._username, self._password = username, password
        self._tls, self._timeout = starttls, timeout_seconds

    async def send(self, *, recipient: str, subject: str, text: str, html: str | None = None) -> None:
        if self._allowed is not None and not recipient_allowed(recipient, self._allowed):
            raise EmailRecipientNotAllowed("Recipient not allowed in this environment")
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
