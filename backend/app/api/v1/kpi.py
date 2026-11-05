"""KPI, doanh thu, nhật ký (06 mục 14–15).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M8.
"""

from fastapi import APIRouter

router = APIRouter(tags=["kpi"])


@router.get("/kpi/summary")
async def kpi_summary() -> dict[str, object]:
    """GET /kpi/summary — 8 KPI + baseline."""
    raise NotImplementedError


@router.get("/kpi/daily")
async def kpi_daily() -> dict[str, object]:
    """GET /kpi/daily — Chuỗi theo ngày."""
    raise NotImplementedError


@router.get("/kpi/revenue")
async def kpi_revenue() -> dict[str, object]:
    """GET /kpi/revenue — owner nơi đó, admin, viewer có can_view_revenue; khác 403."""
    raise NotImplementedError


@router.get("/kpi/diagnostics")
async def kpi_diagnostics() -> dict[str, object]:
    """GET /kpi/diagnostics — hard_constraint_violations, latency, external_handoff_count."""
    raise NotImplementedError


@router.put("/kpi/baseline/{metric}")
async def put_baseline(metric: str) -> dict[str, object]:
    """PUT /kpi/baseline/{metric} — admin."""
    raise NotImplementedError


@router.get("/audit/decisions")
async def audit_decisions() -> dict[str, object]:
    """GET /audit/decisions — admin, dispatcher, viewer; chỉ đọc."""
    raise NotImplementedError
