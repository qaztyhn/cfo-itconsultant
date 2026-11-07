import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.providers.email_smtp import EmailDeliveryError, SmtpEmailProvider
from app.providers.sms_sim import SimulatedSmsProvider


async def test_local_mail_transport_builds_text_and_html_without_logging() -> None:
    with patch("app.providers.email_smtp.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        provider = SmtpEmailProvider("mailpit", 1025, sender="demo@cfo.test")
        await provider.send(
            recipient="test@cfo.test",
            subject="Status",
            text="Confirmed",
            html="<p>Confirmed</p>",
        )
        message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        assert message["To"] == "test@cfo.test"
        assert message.is_multipart()
        smtp.return_value.__enter__.return_value.login.assert_not_called()


async def test_transport_failure_is_sanitized() -> None:
    with patch(
        "app.providers.email_smtp.smtplib.SMTP",
        side_effect=smtplib.SMTPException("private"),
    ):
        with pytest.raises(EmailDeliveryError, match="SMTP delivery failed") as error:
            await SmtpEmailProvider("mailpit", 1025, sender="demo@cfo.test").send(
                recipient="test@cfo.test", subject="Status", text="Body"
            )
        assert "private" not in str(error.value)


def test_remote_smtp_and_unencrypted_login_are_not_enabled_by_default() -> None:
    with pytest.raises(ValueError):
        SmtpEmailProvider("remote.test", 25, sender="demo@cfo.test")
    with pytest.raises(ValueError):
        SmtpEmailProvider("mailpit", 25, sender="demo@cfo.test", username="user")


async def test_header_injection_is_rejected_before_any_connection() -> None:
    with patch("app.providers.email_smtp.smtplib.SMTP") as smtp:
        with pytest.raises(ValueError):
            await SmtpEmailProvider("mailpit", 1025, sender="demo@cfo.test").send(
                recipient="test@cfo.test", subject="Status\nBcc: attacker@cfo.test", text="Body"
            )
        smtp.assert_not_called()


async def test_sms_stays_in_memory_and_repr_contains_no_personal_data() -> None:
    provider = SimulatedSmsProvider()
    with patch("socket.create_connection", MagicMock(side_effect=AssertionError("No network"))):
        message = await provider.send(recipient="synthetic-number", body="synthetic-private-body")
    assert provider.messages == [message]
    assert message.body == "synthetic-private-body"
    assert "synthetic" not in repr(message)
