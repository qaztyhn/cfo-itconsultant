"""Lập kế hoạch (04 mục 7.1; US-PLN-01..08).

Nạp ngữ cảnh theo kho và chân trời 14 ngày → EngineConfig/OrderCtx/WarehouseCtx → engine.plan_order →
trong MỘT transaction: planning_run (+input_snapshot), fulfilment_plan + plan_vehicle, giữ chỗ
(ReservationService, KHÔNG khóa, cho phép vượt), đơn PLANNED/NO_FEASIBLE_DATE, PLAN_PROPOSED +
RESERVATION_HELD. Chạy lại bắt buộc lý do (CRITERIA_CHANGED_RERUN), giữ chỗ cũ released. suggest_replan():
4 tín hiệu (source_change, plan_invalidated, vehicle_issue, delivery_failed) →
planning_run(kind='replan_suggestion'), cộng lại tài nguyên của kế hoạch cũ của chính đơn vào ngữ cảnh,
KHÔNG giữ chỗ, alert REPLAN_SUGGESTED (06 mục 6.6; US-APR-04).

Owner: Dev 1 (A) — M4.
"""


async def plan(order_id: int, actor: object | None, params: dict[str, object] | None = None) -> int:
    """TODO(#planning-plan)."""
    raise NotImplementedError


async def suggest_replan(order_id: int, trigger: str) -> int | None:
    """TODO(#planning-suggest_replan)."""
    raise NotImplementedError


async def get_run(run_id: int) -> dict[str, object]:
    """TODO(#planning-get_run)."""
    raise NotImplementedError
