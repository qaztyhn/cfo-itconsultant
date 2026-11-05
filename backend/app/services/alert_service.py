"""Cảnh báo (US-RSK-03).

raise_alert dùng dedupe_key; chỉ chặn trùng khi alert còn mở (ux_alert_open_dedupe). list theo phạm vi,
critical trước; ack ghi acknowledged_by/at.

Owner: Dev 1 (A) — M7.
"""


async def raise_alert(
    market_id: int, type_: str, level: str, message: str, dedupe_key: str, order_id: int | None = None
) -> int | None:
    """TODO(#alert-raise_alert)."""
    raise NotImplementedError


async def ack(alert_id: int, actor: object) -> None:
    """TODO(#alert-ack)."""
    raise NotImplementedError
