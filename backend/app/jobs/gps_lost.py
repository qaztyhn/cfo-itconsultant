"""US-GPS-03 AC1: GPS loss alerts without exposing coordinates or driver details."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import MarketConfig
from app.core.db import get_sessionmaker
from app.core.logging import log_event
from app.domain.models.ops import DeliveryTrip, VehiclePosition
from app.domain.models.ref import Location, Market
from app.services.alert_service import raise_alert


async def check_lost(session: AsyncSession, *, now: datetime) -> int:
    if now.tzinfo is None:
        raise ValueError("GPS check time must have a timezone")
    latest = (
        select(func.max(VehiclePosition.recorded_at))
        .where(VehiclePosition.trip_id == DeliveryTrip.id)
        .scalar_subquery()
    )
    result = await session.execute(
        select(DeliveryTrip, Market, latest)
        .join(Location, Location.id == DeliveryTrip.warehouse_id)
        .join(Market, Market.id == Location.market_id)
        .where(DeliveryTrip.status == "on_road", Market.gps_enabled.is_(True))
    )
    created = 0
    for trip, market, last_position in result:
        lost_min = MarketConfig.model_validate(market.config).gps.lost_min
        if lost_min <= 0:
            raise ValueError("GPS loss threshold must be positive")
        last_signal = last_position or trip.depart_actual_at
        if last_signal is not None and last_signal < now - timedelta(minutes=lost_min):
            alert_id = await raise_alert(
                session,
                market_id=market.id,
                type_="GPS_LOST",
                level="warning",
                message="Trip GPS signal overdue.",
                dedupe_key=f"GPS_LOST:trip:{trip.id}",
                target_roles=["dispatcher"],
            )
            created += int(alert_id is not None)
    return created


async def run() -> int:
    async with get_sessionmaker()() as session, session.begin():
        count = await check_lost(session, now=clock.now())
    log_event("scheduler", "gps_lost_check", rows_processed=count)
    return count
