"""Doanh thu chỉ đọc (05 mục 8; 06 mục 14.1; US-REV-01).

Chỉ tiền hàng (total_amount = Σ line_total); không phí giao/đóng gói/nhân công/giá vốn/lợi nhuận.
recognised = đơn DELIVERED theo delivered_at ở múi giờ market (audit.v_revenue_daily); booked =
APPROVED…DISPATCHED theo committed_date (audit.v_revenue_pending). Hai góc nhìn store/warehouse, mỗi truy
vấn GROUP BY một chiều, không cộng với nhau; đơn không có cửa hàng → 'Unassigned store'.
resolve_revenue_scope: admin hoặc revenue_all → all; nếu không, location có owner_employee_id =
user.employee_id; rỗng → 403; ngoài phạm vi → 404; view không khớp loại nơi → 422. share_of_market_pct chỉ
cho Business owner/admin. Business owner không nhận customer_name. Export CSV (UTF-8 BOM) ghi decision_log
REVENUE_EXPORTED. Không PII trong log/file xuất của Business owner.

Owner: Dev 1 (A) — M8.
"""


async def resolve_revenue_scope(user: object) -> tuple[bool, list[int]]:
    """TODO(#revenue-resolve_revenue_scope)."""
    raise NotImplementedError


async def summary(user: object, params: dict[str, object]) -> dict[str, object]:
    """TODO(#revenue-summary)."""
    raise NotImplementedError


async def daily(user: object, params: dict[str, object]) -> dict[str, object]:
    """TODO(#revenue-daily)."""
    raise NotImplementedError


async def by_location(user: object, params: dict[str, object]) -> dict[str, object]:
    """TODO(#revenue-by_location)."""
    raise NotImplementedError


async def orders(user: object, params: dict[str, object]) -> dict[str, object]:
    """TODO(#revenue-orders)."""
    raise NotImplementedError


async def export_csv(user: object, params: dict[str, object]) -> bytes:
    """TODO(#revenue-export_csv)."""
    raise NotImplementedError
