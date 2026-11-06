"""Lập kế hoạch và duyệt (06 mục 6). Chỉ dispatcher ghi.

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M4/M5.
"""

from fastapi import APIRouter

router = APIRouter(tags=["planning"])


@router.post("/orders/{order_id}/plan")
async def run_plan(order_id: int) -> dict[str, object]:
    """POST /orders/{order_id}/plan — Chạy engine; chạy lại cần reason; BLOCKED → 409 SKU_UNMAPPED."""
    raise NotImplementedError


@router.get("/orders/{order_id}/planning-runs")
async def list_runs(order_id: int) -> dict[str, object]:
    """GET /orders/{order_id}/planning-runs — Lịch sử lần chạy."""
    raise NotImplementedError


@router.get("/planning-runs/{run_id}")
async def get_run(run_id: int) -> dict[str, object]:
    """GET /planning-runs/{run_id} — PlanningRun gồm rejected_candidates, stock_matrix, dates_searched."""
    raise NotImplementedError


@router.post("/planning-runs/{run_id}/extend")
async def extend_hold(run_id: int) -> dict[str, object]:
    """POST /planning-runs/{run_id}/extend — +15 phút, tối đa 2 lần → 409 HOLD_EXTENSION_LIMIT."""
    raise NotImplementedError


@router.post("/planning-runs/{run_id}/keep-current")
async def keep_current(run_id: int) -> dict[str, object]:
    """POST /planning-runs/{run_id}/keep-current — Giữ kế hoạch hiện tại khi có gợi ý lập lại; lý do bắt
    buộc (06 mục 6.6)."""
    raise NotImplementedError


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: int) -> dict[str, object]:
    """GET /plans/{plan_id} — Chi tiết một phương án."""
    raise NotImplementedError


@router.post("/plans/{plan_id}/approve")
async def approve_plan(plan_id: int) -> dict[str, object]:
    """POST /plans/{plan_id}/approve — Idempotency-Key bắt buộc (06 mục 6.3)."""
    raise NotImplementedError


@router.post("/orders/{order_id}/manual-plan")
async def manual_plan(order_id: int) -> dict[str, object]:
    """POST /orders/{order_id}/manual-plan — Idempotency-Key; từ PLANNED/NO_FEASIBLE_DATE; một hoặc nhiều
    xe; gate vẫn chạy."""
    raise NotImplementedError


@router.post("/orders/{order_id}/date-negotiations")
async def create_date_negotiation(order_id: int) -> dict[str, object]:
    """POST /orders/{order_id}/date-negotiations — agreed/declined/unreachable."""
    raise NotImplementedError


@router.get("/orders/{order_id}/date-negotiations")
async def list_date_negotiations(order_id: int) -> dict[str, object]:
    """GET /orders/{order_id}/date-negotiations — Lịch sử thương lượng ngày."""
    raise NotImplementedError


@router.get("/orders/{order_id}/transfer-suggestions")
async def transfer_suggestions(order_id: int) -> dict[str, object]:
    """GET /orders/{order_id}/transfer-suggestions — Gợi ý chuyển kho."""
    raise NotImplementedError
