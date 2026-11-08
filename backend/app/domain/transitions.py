"""Chuyển trạng thái đơn — điểm DUY NHẤT được đổi customer_order.status (09 bất biến 12).

transition(session, order, to_status, actor, reason) tra ops.order_transition; DB trigger
trg_check_transition là lớp bảo vệ thứ hai. Khi rời APPROVED/FAILED/PLANNED về SUBMITTED, sang
CANCELLED, hoặc khi duyệt phương án gợi ý lập lại (… → APPROVED), gọi close_active_plan() trong
cùng transaction (09 bất biến 21, 05 mục 6). v1.2: không còn MANUAL_PLANNING/HANDLED_EXTERNALLY.

Owner: Dev 1 (luồng A) — M0 (bảng), M2 (transition), M5 (đóng kế hoạch).
"""

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import DomainError
from app.domain.enums import OrderStatus as S
from app.domain.models.ops import CustomerOrder, DeliveryTrip, OrderTransition, TripStop
from app.domain.models.plan import (
    FulfilmentPlan,
    PlanningRun,
    PrepReservation,
    StockReservation,
    VehicleReservation,
)

SYSTEM_ROLE = "system"  # ASM-002: allowed_roles rỗng trong ops.order_transition = chỉ hệ thống

# Bản sao bảng seed ops.order_transition (05 mục 6) — dùng cho kiểm tra sớm và test.
ALLOWED: dict[tuple[S, S], tuple[bool, tuple[str, ...]]] = {
    (S.SUBMITTED, S.PLANNED): (False, ("system",)),
    (S.SUBMITTED, S.BLOCKED_UNMAPPED_SKU): (False, ("system",)),
    (S.SUBMITTED, S.NO_FEASIBLE_DATE): (False, ("system",)),
    (S.BLOCKED_UNMAPPED_SKU, S.SUBMITTED): (False, ("system",)),
    (S.PLANNED, S.APPROVED): (False, ("dispatcher",)),
    (S.NO_FEASIBLE_DATE, S.APPROVED): (True, ("dispatcher",)),  # kế hoạch tay
    (S.PLANNED, S.SUBMITTED): (True, ("dispatcher",)),
    (S.NO_FEASIBLE_DATE, S.SUBMITTED): (True, ("dispatcher",)),
    (S.NO_FEASIBLE_DATE, S.CANCELLED): (True, ("dispatcher",)),
    (S.PLANNED, S.CANCELLED): (True, ("dispatcher",)),
    (S.APPROVED, S.PREPARING): (False, ("warehouse",)),
    (S.APPROVED, S.SUBMITTED): (True, ("dispatcher",)),
    (S.PREPARING, S.GOODS_READY): (False, ("warehouse",)),
    (S.GOODS_READY, S.LOADED): (False, ("warehouse",)),
    (S.LOADED, S.DISPATCHED): (False, ("driver",)),
    (S.DISPATCHED, S.DELIVERED): (False, ("driver",)),
    (S.DISPATCHED, S.FAILED): (True, ("driver",)),
    (S.FAILED, S.SUBMITTED): (True, ("dispatcher",)),
    # v1.2: duyệt phương án gợi ý lập lại (đóng kế hoạch cũ, commit kế hoạch mới)
    (S.FAILED, S.APPROVED): (True, ("dispatcher",)),
    (S.PREPARING, S.APPROVED): (True, ("dispatcher",)),
    (S.GOODS_READY, S.APPROVED): (True, ("dispatcher",)),
    (S.LOADED, S.APPROVED): (True, ("dispatcher",)),
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
        (S.FAILED, S.APPROVED),
        (S.PREPARING, S.APPROVED),
        (S.GOODS_READY, S.APPROVED),
        (S.LOADED, S.APPROVED),
    }
)


def is_allowed(from_status: S, to_status: S) -> bool:
    """True nếu cặp chuyển có trong bảng."""
    return (from_status, to_status) in ALLOWED


async def transition(
    session: AsyncSession,
    order_id: int,
    to_status: S,
    actor_role: str,
    reason_text: str | None = None,
    *,
    expired_hold_run_id: int | None = None,
    sales_approved_plan_id: int | None = None,
) -> "Transitioned":
    """Đổi trạng thái đơn trong transaction của caller; trả trạng thái cũ và kế hoạch đã đóng (nếu có).

    Tra ops.order_transition (nguồn sự thật; trigger trg_check_transition là lớp thứ hai):
    cặp không có → 409 ILLEGAL_TRANSITION; vai trò không được phép → 403 FORBIDDEN (allowed_roles rỗng = chỉ
    "system", ASM-002); cần lý do mà thiếu → 422 REASON_REQUIRED. Cặp thuộc CLOSES_ACTIVE_PLAN gọi
    close_active_plan() trước khi UPDATE và trả kết quả trong Transitioned.closed. Không ghi decision_log:
    caller ghi mã hành động của use case (ORDER_REPLAN, ORDER_CANCELLED, MAPPING_CONFIRMED…) trong cùng
    transaction (09 bất biến 14).
    Không commit.
    """
    current = await session.scalar(
        select(CustomerOrder.status).where(CustomerOrder.id == order_id).with_for_update()
    )
    if current is None:
        raise DomainError("NOT_FOUND", "Order not found.")
    from_status = S(current)
    rule = await session.scalar(
        select(OrderTransition).where(
            OrderTransition.from_status == from_status.value, OrderTransition.to_status == S(to_status).value
        )
    )
    if rule is None:
        raise DomainError(
            "ILLEGAL_TRANSITION",
            "Transition is not allowed.",
            {"from_status": from_status.value, "to_status": S(to_status).value},
        )
    allowed = set(rule.allowed_roles) or {SYSTEM_ROLE}
    # DEC-HOLD-001: narrowly authorize an automatic PLANNED → SUBMITTED transition.
    # It is NOT a general grant of dispatcher privileges to system jobs.
    timeout_reset = (
        actor_role == SYSTEM_ROLE
        and from_status == S.PLANNED
        and to_status == S.SUBMITTED
        and reason_text == "hold_expired"
        and expired_hold_run_id is not None
        and await _eligible_expired_hold(session, order_id, expired_hold_run_id)
    )
    # Q14: Sales may confirm only after ApprovalService has marked a plan
    # approved and linked it to this order in the same locked transaction.
    # This DOES NOT allow Sales to select plans or change order dates.
    sales_confirm = False
    if (
        actor_role == "sales"
        and from_status == S.PLANNED
        and to_status == S.APPROVED
        and sales_approved_plan_id is not None
    ):
        approved = await session.scalar(
            select(FulfilmentPlan.id)
            .join(CustomerOrder, CustomerOrder.id == FulfilmentPlan.order_id)
            .where(
                FulfilmentPlan.id == sales_approved_plan_id,
                FulfilmentPlan.order_id == order_id,
                FulfilmentPlan.rank == 1,
                FulfilmentPlan.status == "approved",
                FulfilmentPlan.vehicle_count == 1,
                CustomerOrder.approved_plan_id == sales_approved_plan_id,
                CustomerOrder.committed_date == FulfilmentPlan.target_date,
            )
        )
        sales_confirm = approved is not None
    if actor_role not in allowed and not timeout_reset and not sales_confirm:
        raise DomainError("FORBIDDEN", "Role may not perform this transition.")
    if rule.requires_reason and not (reason_text and reason_text.strip()):
        raise DomainError("REASON_REQUIRED", "This transition requires a reason.")
    closed = None
    if (from_status, S(to_status)) in CLOSES_ACTIVE_PLAN:
        closed = await close_active_plan(session, order_id)
    await session.execute(
        update(CustomerOrder).where(CustomerOrder.id == order_id).values(status=S(to_status).value)
    )
    return Transitioned(from_status, closed)


async def _eligible_expired_hold(session: AsyncSession, order_id: int, run_id: int) -> bool:
    """Only the latest expired, unapproved run may reset its order (DEC-HOLD-001).

    Caller holds the order row lock in transition(); never reset a newer plan.
    """
    order = await session.get(CustomerOrder, order_id)
    if order is None or order.status != S.PLANNED.value or order.approved_plan_id is not None:
        return False
    latest = await session.scalar(
        select(PlanningRun)
        .where(PlanningRun.order_id == order_id)
        .order_by(PlanningRun.run_no.desc(), PlanningRun.id.desc())
        .limit(1)
    )
    if (
        latest is None
        or latest.id != run_id
        or latest.kind == "replan_suggestion"
        or latest.hold_expires_at is None
        or latest.hold_expires_at > clock.now()
    ):
        return False
    approved = await session.scalar(
        select(FulfilmentPlan.id)
        .where(FulfilmentPlan.order_id == order_id, FulfilmentPlan.status.in_(("approved", "manual")))
        .limit(1)
    )
    if approved is not None:
        return False
    for model in (StockReservation, PrepReservation, VehicleReservation):
        active = await session.scalar(
            select(model.id)
            .where(model.order_id == order_id, model.status.in_(("held", "committed")))
            .limit(1)
        )
        if active is not None:
            return False
    return True


async def reset_expired_hold_order(session: AsyncSession, order_id: int, run_id: int) -> bool:
    """Trusted timeout-only transition; runs inside expiry's existing transaction.

    The normal dispatcher PLANNED → SUBMITTED transition remains unchanged.
    """
    if not await _eligible_expired_hold(session, order_id, run_id):
        return False
    await transition(
        session,
        order_id,
        S.SUBMITTED,
        SYSTEM_ROLE,
        "hold_expired",
        expired_hold_run_id=run_id,
    )
    return True


@dataclass(frozen=True)
class ClosedPlan:
    """Kết quả đóng kế hoạch cũ: `before` để caller đưa vào decision_log.before (05 mục 6 bước 4–5)."""

    before: dict[str, object]
    superseded_plan_ids: tuple[int, ...]
    released: dict[str, int]
    cancelled_trip_ids: tuple[int, ...]


@dataclass(frozen=True)
class Transitioned:
    from_status: S
    closed: ClosedPlan | None = None


_RESERVATIONS = (("stock", StockReservation), ("prep", PrepReservation), ("vehicle", VehicleReservation))


async def close_active_plan(session: AsyncSession, order_id: int) -> ClosedPlan:
    """Đóng kế hoạch cũ của đơn theo 05 mục 6 (09 bất biến 21), trong transaction của caller.

    1. Kế hoạch `approved`/`manual`/`proposed` → `superseded` (kế hoạch tay nhận ra nhờ manual_reason_code).
    2. Giữ chỗ `held`/`committed` (hàng, giờ công, xe) → `released`; `consumed` giữ nguyên (sau FAILED).
    3. `trip_stop` còn `pending` → `cancelled`; `delivery_trip` của đơn chưa `completed` → `cancelled`.
    4. Xóa approved_plan_id, committed_date, promise_start, promise_end; giá trị cũ trả trong `before`.
    Bước 5 (decision_log ORDER_REPLAN / ORDER_CANCELLED / CRITERIA_CHANGED_RERUN) do use case ghi kèm
    `before` lấy từ Transitioned.closed.
    Không commit. Không gọi trực tiếp khi đổi trạng thái: transition() gọi hàm này cho CLOSES_ACTIVE_PLAN.
    """
    order = (
        await session.execute(
            select(
                CustomerOrder.approved_plan_id,
                CustomerOrder.committed_date,
                CustomerOrder.promise_start,
                CustomerOrder.promise_end,
            ).where(CustomerOrder.id == order_id)
        )
    ).one()
    before: dict[str, object] = {
        "approved_plan_id": order.approved_plan_id,
        "committed_date": order.committed_date.isoformat() if order.committed_date else None,
        "promise_start": order.promise_start.isoformat() if order.promise_start else None,
        "promise_end": order.promise_end.isoformat() if order.promise_end else None,
    }
    superseded = (
        await session.scalars(
            update(FulfilmentPlan)
            .where(
                FulfilmentPlan.order_id == order_id,
                FulfilmentPlan.status.in_(("approved", "manual", "proposed")),
            )
            .values(status="superseded")
            .returning(FulfilmentPlan.id)
            .execution_options(synchronize_session=False)
        )
    ).all()
    released: dict[str, int] = {}
    for name, model in _RESERVATIONS:
        ids = (
            await session.scalars(
                update(model)
                .where(model.order_id == order_id, model.status.in_(("held", "committed")))
                .values(status="released")
                .returning(model.id)
                .execution_options(synchronize_session=False)
            )
        ).all()
        released[name] = len(ids)
    await session.execute(
        update(TripStop)
        .where(TripStop.order_id == order_id, TripStop.status == "pending")
        .values(status="cancelled")
        .execution_options(synchronize_session=False)
    )
    cancelled_trips = (
        await session.scalars(
            update(DeliveryTrip)
            .where(
                DeliveryTrip.id.in_(select(TripStop.trip_id).where(TripStop.order_id == order_id)),
                DeliveryTrip.status.not_in(("completed", "cancelled")),
            )
            .values(status="cancelled")
            .returning(DeliveryTrip.id)
            .execution_options(synchronize_session=False)
        )
    ).all()
    await session.execute(
        update(CustomerOrder)
        .where(CustomerOrder.id == order_id)
        .values(approved_plan_id=None, committed_date=None, promise_start=None, promise_end=None)
    )
    return ClosedPlan(
        before=before | {"superseded_plan_ids": sorted(superseded)},
        superseded_plan_ids=tuple(sorted(superseded)),
        released=released,
        cancelled_trip_ids=tuple(sorted(cancelled_trips)),
    )
