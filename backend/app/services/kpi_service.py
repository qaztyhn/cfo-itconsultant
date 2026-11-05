"""KPI và doanh thu (05 mục 8; US-KPI-01/02).

8 KPI + 2 chẩn đoán + external_handoff_count, ngày theo múi giờ market, so baseline. revenue(): Σ
line_total đơn DELIVERED, theo kho/cửa hàng, một tiền tệ; chỉ owner nơi đó, admin, viewer có
can_view_revenue (khác → 403).

Owner: Dev 1 (A) — M8.
"""


async def summary(
    user: object, date_from: object, date_to: object, location_id: int | None = None
) -> dict[str, object]:
    """TODO(#kpi-summary)."""
    raise NotImplementedError


async def daily(user: object, metric: str, date_from: object, date_to: object) -> list[dict[str, object]]:
    """TODO(#kpi-daily)."""
    raise NotImplementedError


async def revenue(user: object, location_id: int, date_from: object, date_to: object) -> dict[str, object]:
    """TODO(#kpi-revenue)."""
    raise NotImplementedError


async def diagnostics(user: object) -> dict[str, object]:
    """TODO(#kpi-diagnostics)."""
    raise NotImplementedError
