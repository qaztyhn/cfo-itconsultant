"""Doanh thu chỉ đọc (06 mục 14.1). Phạm vi theo resolve_revenue_scope; 403/404/422.

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M8.
"""

from fastapi import APIRouter

router = APIRouter(tags=["revenue"])


@router.get("/revenue/summary")
async def revenue_summary() -> dict[str, object]:
    """GET /revenue/summary — Thẻ số liệu của kỳ (share_of_market_pct chỉ Business owner/admin)."""
    raise NotImplementedError


@router.get("/revenue/daily")
async def revenue_daily() -> dict[str, object]:
    """GET /revenue/daily — Chuỗi theo ngày: recognised, booked."""
    raise NotImplementedError


@router.get("/revenue/by-location")
async def revenue_by_location() -> dict[str, object]:
    """GET /revenue/by-location — Bảng theo cửa hàng hoặc kho; 'Unassigned store'."""
    raise NotImplementedError


@router.get("/revenue/orders")
async def revenue_orders() -> dict[str, object]:
    """GET /revenue/orders — Đơn của một nơi (location_id bắt buộc); Business owner không có customer_name."""
    raise NotImplementedError


@router.get("/revenue/export.csv")
async def revenue_export_csv() -> dict[str, object]:
    """GET /revenue/export.csv — Owner, Business owner, admin; ghi REVENUE_EXPORTED."""
    raise NotImplementedError
