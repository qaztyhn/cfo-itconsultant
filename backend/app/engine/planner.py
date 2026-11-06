"""Hàm vào chính của engine: plan_order() (04 mục 6.1–6.2).

v1.2: không còn bước "manual"; đơn lớn được chia cho nhiều xe ở bước 2d. Bước 1 → 2a..2f → gate →
xếp hạng (ít xe trước) → giải thích. Không ứng viên → infeasible + earliest_feasible_date (bỏ cận trên,
quét ≤ 14 ngày) + gợi ý chuyển kho nếu mọi kho thiếu hàng; thiếu loại xe/kín xe → failed_check "truck".
Cùng hàm dùng cho lần chạy replan_suggestion (service đã cộng lại tài nguyên của kế hoạch cũ).
Hiệu năng < 2 giây/đơn.

Owner: Dev 1 (luồng A).
"""

from app.engine.types import EngineConfig, OrderCtx, PlanningResult, RankWeights, WarehouseCtx


def plan_order(
    order: OrderCtx, warehouses: list[WarehouseCtx], cfg: EngineConfig, weights: RankWeights | None = None
) -> PlanningResult:
    """Lập kế hoạch một đơn. Hàm thuần. TODO(#M4-planner)."""
    raise NotImplementedError
