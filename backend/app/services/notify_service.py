"""Thông báo khách (FR-NOT-01..04; US-NOT-01..03).

4 mẫu tự động (CONFIRMED, DISPATCHED, DELIVERED, FAILED) → queued; DELAY chỉ draft, dispatcher
send/discard (lý do bắt buộc). dedupe_key gồm plan_id/trip_stop; shadow_mode → suppressed; giờ yên lặng
21–07 trừ DELAY; thử lại 3 lần. Nội dung chỉ trạng thái + ETA, không GPS/tọa độ/tên tài xế (09 mục 10).

Owner: Dev 2 (B) — M7.
"""


async def enqueue(order_id: int, template: str, plan_id: int | None = None) -> int | None:
    """TODO(#notify-enqueue)."""
    raise NotImplementedError


async def create_delay_draft(order_id: int, eta_window: dict[str, str]) -> int | None:
    """TODO(#notify-create_delay_draft)."""
    raise NotImplementedError


async def send_draft(
    notification_id: int, actor: object, payload: dict[str, object], idempotency_key: str
) -> None:
    """TODO(#notify-send_draft)."""
    raise NotImplementedError


async def discard_draft(notification_id: int, actor: object, reason_text: str) -> None:
    """TODO(#notify-discard_draft)."""
    raise NotImplementedError


async def process_outbox() -> int:
    """TODO(#notify-process_outbox)."""
    raise NotImplementedError
