"""SmsProvider mô phỏng: chỉ lưu vào hộp thư mô phỏng, không gửi ra mạng (FR-NOT-01).

Owner: Dev 2 (luồng B) — M7.
"""


class SimulatedSmsProvider:
    """Ghi nhận SMS, trạng thái 'sent' với ghi chú 'sms_sim · not sent to a network'. TODO(#M7-notify)."""
