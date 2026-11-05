"""Duyệt, kế hoạch tay, xử lý ngoài CFO (04 mục 7; US-APR-01..04).

approve: Idempotency-Key; khóa theo 04 mục 7 quy tắc 8; kiểm tra lại bằng engine; rank>1 cần lý do
(ALT_SELECTED); tight cần xác nhận; đổi ngày cần date_negotiation agreed; plan approved, khác superseded,
giữ chỗ committed/released, trip + trip_stop, committed_date/promise, CONFIRMED (dedupe theo plan_id), eta
v1, PLAN_APPROVED. Xung đột → 409 RESOURCE_CONFLICT + rollback. manual_plan: gate vẫn chạy;
MANUAL_PLANNING không xe vừa → 422 hint EXTERNAL_HANDOFF. external_handoff: MANUAL_PLANNING →
HANDLED_EXTERNALLY, EXTERNAL_HANDOFF_RECORDED, không thông báo tự động. KHÔNG có đường tự duyệt (09 bất
biến 1).

Owner: Dev 1 (A) — M5.
"""


async def approve(
    plan_id: int, actor: object, payload: dict[str, object], idempotency_key: str
) -> dict[str, object]:
    """TODO(#approval-approve)."""
    raise NotImplementedError


async def manual_plan(
    order_id: int, actor: object, payload: dict[str, object], idempotency_key: str
) -> dict[str, object]:
    """TODO(#approval-manual_plan)."""
    raise NotImplementedError


async def external_handoff(order_id: int, actor: object, payload: dict[str, object]) -> None:
    """TODO(#approval-external_handoff)."""
    raise NotImplementedError


async def record_date_negotiation(order_id: int, actor: object, payload: dict[str, object]) -> int:
    """TODO(#approval-record_date_negotiation)."""
    raise NotImplementedError
