"""EmailProvider qua SMTP: Mailpit (local), Brevo/Resend free (staging). Không gửi email thật ngoài
cấu hình staging (09 mục 13).

Owner: Dev 2 (luồng B) — M7.
"""


class SmtpEmailProvider:
    """Gửi email từ outbox. TODO(#M7-notify)."""
