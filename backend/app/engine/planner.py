"""Hàm vào chính của engine: plan_order() (04 mục 6.1–6.2).

Bước 0 tiền kiểm: vượt xe lớn nhất mọi kho → manual NEEDS_MULTI_VEHICLE; nhóm cần vehicle_requirement
mà không xe nào đủ (kể cả tải) → manual NO_CAPABLE_VEHICLE. Rồi bước 1 → 2a..2f → gate → xếp hạng →
giải thích. Không ứng viên → infeasible + earliest_feasible_date (bỏ cận trên, quét ≤ 14 ngày) +
gợi ý chuyển kho nếu mọi kho thiếu hàng. Hiệu năng < 2 giây/đơn.

Owner: Dev 1 (luồng A).
"""

from app.engine.types import EngineConfig, OrderCtx, PlanningResult, RankWeights, WarehouseCtx


def plan_order(
    order: OrderCtx, warehouses: list[WarehouseCtx], cfg: EngineConfig, weights: RankWeights | None = None
) -> PlanningResult:
    """Lập kế hoạch một đơn. Hàm thuần. TODO(#M4-planner)."""
    raise NotImplementedError
