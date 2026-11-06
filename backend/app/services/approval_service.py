"""Duyệt, kế hoạch tay, gợi ý lập lại (04 mục 7; US-APR-01..04).

approve: Idempotency-Key; CHỈ ở đây mới khóa (advisory lock kho → sản phẩm → ngày, rồi mọi xe → mọi tài
xế); kiểm tra lại bằng engine (trừ committed của đơn khác); rank>1 cần lý do (ALT_SELECTED); tight cần xác
nhận; đổi ngày cần date_negotiation agreed; plan approved, khác superseded, giữ chỗ committed/released,
mỗi xe một trip + trip_stop, committed_date/promise, CONFIRMED (dedupe theo plan_id), eta v1,
PLAN_APPROVED. Nếu plan thuộc run replan_suggestion: đóng kế hoạch cũ (close_active_plan) trong cùng
transaction rồi mới commit. Xung đột → 409 RESOURCE_CONFLICT + rollback. manual_plan: từ
PLANNED/NO_FEASIBLE_DATE, một hoặc nhiều xe, gate vẫn chạy. keep_current: giữ kế hoạch cũ khi có gợi ý (lý
do bắt buộc, REPLAN_KEPT). KHÔNG có đường tự duyệt (09 bất biến 1).

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


async def keep_current(run_id: int, actor: object, reason_text: str) -> None:
    """TODO(#approval-keep_current)."""
    raise NotImplementedError


async def record_date_negotiation(order_id: int, actor: object, payload: dict[str, object]) -> int:
    """TODO(#approval-record_date_negotiation)."""
    raise NotImplementedError
