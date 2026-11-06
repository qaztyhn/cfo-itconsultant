"""Sự kiện thực thi (06 mục 8.1; BR-EXE-01..03; US-WH-04/05, US-EXE-01..04).

Sự kiện bất biến, đúng thứ tự (ILLEGAL_TRANSITION), Idempotency-Key, occurred_at ≤ now+5' và không trước
sự kiện trước. START_PREP/PREP_RESUMED bắt buộc crew_size; PREP_PAUSED không đổi trạng thái; GOODS_READY
tính actual_labour_hours (engine.actuals). LOADED/DISPATCHED/DELIVERED/FAILED theo từng xe (trip_id);
trạng thái đơn tổng hợp (LOADED khi mọi xe, DISPATCHED ở xe đầu, DELIVERED khi mọi xe, FAILED khi có xe
thất bại). Mỗi trip_stop một POD. VEHICLE_ISSUE và FAILED gọi PlanningService.suggest_replan.
SHORTAGE/BREAKAGE/VEHICLE_ISSUE → alert EXCEPTION. Sau mỗi sự kiện gọi RiskService.recalculate. Chuyển
trạng thái chỉ qua domain.transitions.

Owner: Dev 1 (A) — M6.
"""


async def record_event(
    order_id: int,
    actor: object,
    event_type: str,
    occurred_at: object,
    payload: dict[str, object],
    idempotency_key: str,
) -> dict[str, object]:
    """TODO(#execution-record_event)."""
    raise NotImplementedError


async def driver_trips(actor: object, day: object) -> list[dict[str, object]]:
    """TODO(#execution-driver_trips)."""
    raise NotImplementedError


async def prep_queue(warehouse_id: int, day: object, actor: object) -> dict[str, object]:
    """TODO(#execution-prep_queue)."""
    raise NotImplementedError
