"""Log kỹ thuật JSONL (04 mục 10, 09 mục 10).

Trường: ts, level, service (api|engine|integration|scheduler|notify), correlation_id, order_id,
market, event, duration_ms, extra. File logs/<service>/<YYYY-MM-DD>.jsonl (local), stdout (online).
KHÔNG PII: không tên, điện thoại, email, địa chỉ khách (09 bất biến 16; US-LOG-01 AC3).
Engine KHÔNG ghi log (09 bất biến 6).

Owner: Dev 1 (luồng A) — M0.
"""

PII_KEYS = frozenset(
    {
        "name",
        "phone",
        "email",
        "address",
        "contact_name",
        "contact_phone",
        "contact_email",
        "delivery_address",
        "recipient_name",
    }
)


def log_event(service: str, event: str, **fields: object) -> None:
    """Ghi một dòng JSONL; tự loại khóa thuộc PII_KEYS. TODO(#M0-logging)."""
    raise NotImplementedError
