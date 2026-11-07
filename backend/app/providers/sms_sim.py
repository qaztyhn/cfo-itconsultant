"""SmsProvider mô phỏng: chỉ lưu vào hộp thư mô phỏng, không gửi ra mạng (FR-NOT-01).

Owner: Dev 2 (luồng B) — M7.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SimulatedSms:
    recipient: str = field(repr=False)
    body: str = field(repr=False)
    note: str = "sms_sim · not sent to a network"


class SimulatedSmsProvider:
    """In-memory demo inbox; no network or disk writes. Outbox remains the durable record."""

    def __init__(self) -> None:
        self.messages: list[SimulatedSms] = []

    async def send(self, *, recipient: str, body: str) -> SimulatedSms:
        message = SimulatedSms(recipient, body)
        self.messages.append(message)
        return message
