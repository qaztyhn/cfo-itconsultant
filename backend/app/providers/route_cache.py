"""Precompute missing warehouse/site routes before planning (US-INT-05)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MarketConfig
from app.domain.models.plan import RouteMatrix
from app.domain.models.ref import Location, Market
from app.providers.routing_ors import (
    OrsRoutingProvider,
    RouteEstimate,
    route_with_fallback,
)


async def ensure_route(
    session: AsyncSession,
    warehouse_id: int,
    lat: Decimal,
    lon: Decimal,
    provider: OrsRoutingProvider,
    *,
    now: datetime,
) -> RouteEstimate:
    """Caller owns transaction; unique PK makes concurrent inserts harmless."""
    if now.tzinfo is None:
        raise ValueError("Route time must have a timezone")
    lat, lon = lat.quantize(Decimal("0.00001")), lon.quantize(Decimal("0.00001"))
    warehouse, market = (
        await session.execute(
            select(Location, Market)
            .join(Market, Market.id == Location.market_id)
            .where(Location.id == warehouse_id, Location.type == "warehouse")
        )
    ).one()
    config = MarketConfig.model_validate(market.config)
    cached = await session.get(RouteMatrix, (warehouse_id, lat, lon))
    if cached is not None and (cached.provider == "ors" or config.routing.allow_fallback):
        return RouteEstimate(
            cached.distance_km,
            cached.duration_min,
            "ors" if cached.provider == "ors" else "fallback",
        )
    if warehouse.lat is None or warehouse.lon is None:
        raise ValueError("Warehouse coordinates unavailable")
    result = await route_with_fallback(
        provider,
        float(warehouse.lat),
        float(warehouse.lon),
        float(lat),
        float(lon),
        allow_fallback=config.routing.allow_fallback,
    )
    stmt = insert(RouteMatrix).values(
        warehouse_id=warehouse_id,
        to_lat=lat,
        to_lon=lon,
        distance_km=result.distance_km,
        duration_min=result.duration_min,
        provider=result.provider,
        computed_at=now,
    )
    # A previously cached fallback must be replaced when fallback is disabled.
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["warehouse_id", "to_lat", "to_lon"],
            set_={
                "distance_km": result.distance_km,
                "duration_min": result.duration_min,
                "provider": result.provider,
                "computed_at": now,
            },
            where=RouteMatrix.provider == "fallback",
        )
    )
    stored = (
        await session.execute(
            select(RouteMatrix.distance_km, RouteMatrix.duration_min, RouteMatrix.provider).where(
                RouteMatrix.warehouse_id == warehouse_id, RouteMatrix.to_lat == lat, RouteMatrix.to_lon == lon
            )
        )
    ).one()
    return RouteEstimate(
        stored.distance_km, stored.duration_min, "ors" if stored.provider == "ors" else "fallback"
    )
