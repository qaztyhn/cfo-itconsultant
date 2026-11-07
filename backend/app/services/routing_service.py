"""US-INT-05 AC1 / FR-DEL-02: prepare warehouse/site pairs outside the pure engine.

This use case only populates route_matrix. It does not route an order to CFO,
check planning eligibility, create holds, or approve a plan. Caller owns transaction.
Request callers must authorize access to the order before invoking this internal helper.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ops import CustomerOrder
from app.domain.models.ref import Location
from app.providers.route_cache import ensure_route
from app.providers.routing_ors import OrsRoutingProvider, RouteEstimate


async def prepare_order_routes(
    session: AsyncSession, order_id: int, provider: OrsRoutingProvider, *, now: datetime
) -> dict[int, RouteEstimate]:
    if order_id <= 0 or now.tzinfo is None:
        raise ValueError("Order ID and timezone-aware preparation time are required")
    order = (
        await session.execute(
            select(CustomerOrder.market_id, CustomerOrder.delivery_lat, CustomerOrder.delivery_lon).where(
                CustomerOrder.id == order_id
            )
        )
    ).one_or_none()
    if order is None:
        raise ValueError("Order unavailable")
    warehouses = (
        await session.scalars(
            select(Location.id)
            .where(
                Location.market_id == order.market_id,
                Location.type == "warehouse",
                Location.is_active.is_(True),
            )
            .order_by(Location.id)
        )
    ).all()
    routes = {}
    for warehouse_id in warehouses:
        routes[warehouse_id] = await ensure_route(
            session, warehouse_id, order.delivery_lat, order.delivery_lon, provider, now=now
        )
    return routes
