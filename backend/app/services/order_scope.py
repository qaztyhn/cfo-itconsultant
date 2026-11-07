"""Điều kiện phạm vi đơn theo vai trò dùng chung (06 v1.4 mục 5.2).

Owner: Dev 1 (A) — M2.
"""

from collections.abc import Iterable

from sqlalchemy import ColumnElement, or_, select

from app.domain.models.ops import CustomerOrder, DeliveryTrip, TripStop
from app.domain.models.plan import FulfilmentPlan

LIVE_PLAN_STATUSES = ("proposed", "approved", "manual")


def warehouse_orders(location_ids: Iterable[int]) -> ColumnElement[bool]:
    """Đơn có kế hoạch chưa superseded từ các kho này, hoặc có chuyến xuất từ các kho này."""
    locations = sorted(set(location_ids))
    has_plan = (
        select(FulfilmentPlan.id)
        .where(
            FulfilmentPlan.order_id == CustomerOrder.id,
            FulfilmentPlan.status.in_(LIVE_PLAN_STATUSES),
            FulfilmentPlan.warehouse_id.in_(locations),
        )
        .exists()
    )
    has_trip = (
        select(TripStop.id)
        .join(DeliveryTrip, DeliveryTrip.id == TripStop.trip_id)
        .where(TripStop.order_id == CustomerOrder.id, DeliveryTrip.warehouse_id.in_(locations))
        .exists()
    )
    return or_(has_plan, has_trip)
