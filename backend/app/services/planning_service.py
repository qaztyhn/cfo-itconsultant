"""Lập kế hoạch (04 mục 7.1; US-PLN-01..08).

Nạp ngữ cảnh theo kho và chân trời 14 ngày → EngineConfig/OrderCtx/WarehouseCtx → engine.plan_order →
trong MỘT transaction: planning_run (+input_snapshot), fulfilment_plan, giữ chỗ (gọi ReservationService có
advisory lock), đơn PLANNED/NO_FEASIBLE_DATE/MANUAL_PLANNING, PLAN_PROPOSED + RESERVATION_HELD. Chạy lại
bắt buộc lý do (CRITERIA_CHANGED_RERUN), giữ chỗ cũ released.

Owner: Dev 1 (A) — M4.
"""


async def plan(order_id: int, actor: object | None, params: dict[str, object] | None = None) -> int:
    """TODO(#planning-plan)."""
    raise NotImplementedError


async def get_run(run_id: int) -> dict[str, object]:
    """TODO(#planning-get_run)."""
    raise NotImplementedError
