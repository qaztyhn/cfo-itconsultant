"""Chuyển trạng thái đơn — điểm DUY NHẤT được đổi customer_order.status (09 bất biến 12).

transition(session, order, to_status, actor, reason) tra ops.order_transition; DB trigger
trg_check_transition là lớp bảo vệ thứ hai. Khi rời APPROVED/FAILED/PLANNED về SUBMITTED hoặc
sang CANCELLED, gọi close_active_plan() trong cùng transaction (09 bất biến 21, 05 mục 6).

Owner: Dev 1 (luồng A) — M0 (bảng), M5 (đóng kế hoạch).
"""

from app.domain.enums import OrderStatus as S

# Bản sao bảng seed ops.order_transition (05 mục 6) — dùng cho kiểm tra sớm và test.
ALLOWED: dict[tuple[S, S], tuple[bool, tuple[str, ...]]] = {
    (S.SUBMITTED, S.PLANNED): (False, ("system",)),
    (S.SUBMITTED, S.BLOCKED_UNMAPPED_SKU): (False, ("system",)),
    (S.SUBMITTED, S.NO_FEASIBLE_DATE): (False, ("system",)),
    (S.SUBMITTED, S.MANUAL_PLANNING): (False, ("system",)),
    (S.BLOCKED_UNMAPPED_SKU, S.SUBMITTED): (False, ("system",)),
    (S.MANUAL_PLANNING, S.HANDLED_EXTERNALLY): (True, ("dispatcher",)),
    (S.PLANNED, S.APPROVED): (False, ("dispatcher",)),
    (S.PLANNED, S.SUBMITTED): (True, ("dispatcher",)),
    (S.NO_FEASIBLE_DATE, S.SUBMITTED): (True, ("dispatcher",)),
    (S.NO_FEASIBLE_DATE, S.CANCELLED): (True, ("dispatcher",)),
    (S.MANUAL_PLANNING, S.CANCELLED): (True, ("dispatcher",)),
    (S.PLANNED, S.CANCELLED): (True, ("dispatcher",)),
    (S.MANUAL_PLANNING, S.APPROVED): (True, ("dispatcher",)),
    (S.APPROVED, S.PREPARING): (False, ("warehouse",)),
    (S.APPROVED, S.SUBMITTED): (True, ("dispatcher",)),
    (S.PREPARING, S.GOODS_READY): (False, ("warehouse",)),
    (S.GOODS_READY, S.LOADED): (False, ("warehouse",)),
    (S.LOADED, S.DISPATCHED): (False, ("driver",)),
    (S.DISPATCHED, S.DELIVERED): (False, ("driver",)),
    (S.DISPATCHED, S.FAILED): (True, ("driver",)),
    (S.FAILED, S.SUBMITTED): (True, ("dispatcher",)),
    (S.APPROVED, S.CANCELLED): (True, ("dispatcher",)),
    (S.PREPARING, S.CANCELLED): (True, ("dispatcher",)),
    (S.GOODS_READY, S.CANCELLED): (True, ("dispatcher",)),
    (S.LOADED, S.CANCELLED): (True, ("dispatcher",)),
}

CLOSES_ACTIVE_PLAN: frozenset[tuple[S, S]] = frozenset(
    {
        (S.APPROVED, S.SUBMITTED),
        (S.FAILED, S.SUBMITTED),
        (S.PLANNED, S.SUBMITTED),
        (S.APPROVED, S.CANCELLED),
        (S.PREPARING, S.CANCELLED),
        (S.GOODS_READY, S.CANCELLED),
        (S.LOADED, S.CANCELLED),
        (S.PLANNED, S.CANCELLED),
    }
)


def is_allowed(from_status: S, to_status: S) -> bool:
    """True nếu cặp chuyển có trong bảng."""
    return (from_status, to_status) in ALLOWED


async def transition(
    session: object, order_id: int, to_status: S, actor_role: str, reason_text: str | None = None
) -> None:
    """Đổi trạng thái đơn; thiếu lý do khi bắt buộc → REASON_REQUIRED; sai → ILLEGAL_TRANSITION.

    Nếu cặp thuộc CLOSES_ACTIVE_PLAN thì gọi close_active_plan() trước khi UPDATE.
    TODO(#M5-lifecycle).
    """
    raise NotImplementedError


async def close_active_plan(session: object, order_id: int) -> None:
    """Đóng kế hoạch cũ (05 mục 6): plan → superseded, giữ chỗ → released, trip_stop/trip → cancelled,
    xóa approved_plan_id/committed_date/promise_*. Cùng transaction với transition(). TODO(#M5-lifecycle).
    """
    raise NotImplementedError
