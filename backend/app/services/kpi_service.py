"""KPI vận hành (05 mục 8; US-KPI-01/02).

8 KPI + 2 chẩn đoán, ngày theo múi giờ market, so baseline. Chỉ admin hoặc kpi_scopes chứa 'ops'; Business
owner (revenue_all) nhận 403.

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


async def diagnostics(user: object) -> dict[str, object]:
    """TODO(#kpi-diagnostics)."""
    raise NotImplementedError
