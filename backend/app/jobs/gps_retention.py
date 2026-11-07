"""US-GPS-03 AC2: expire positions by trip end, using each market's retention.

Trips that ended (completed/cancelled) with `ended_at` set expire by trip end. A finished trip without
`ended_at` (e.g. cancelled before departure or a data gap) must not keep GPS forever: its positions expire by
their own `recorded_at`, so no point older than the retention period survives.
"""

from datetime import datetime, timedelta

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import MarketConfig
from app.core.db import get_sessionmaker
from app.core.logging import log_event
from app.domain.models.ops import DeliveryTrip, VehiclePosition
from app.domain.models.ref import Location, Market


async def purge_positions(session: AsyncSession, *, now: datetime) -> int:
    if now.tzinfo is None:
        raise ValueError("Retention time must have a timezone")
    count = 0
    for market in (await session.scalars(select(Market))).all():
        days = MarketConfig.model_validate(market.config).gps.retention_days
        if days <= 0:
            raise ValueError("GPS retention must be positive")
        cutoff = now - timedelta(days=days)
        finished = (
            select(DeliveryTrip.id)
            .join(Location, Location.id == DeliveryTrip.warehouse_id)
            .where(Location.market_id == market.id, DeliveryTrip.status.in_(("completed", "cancelled")))
        )
        ended_long_ago = finished.where(DeliveryTrip.ended_at < cutoff)
        no_end_time = finished.where(DeliveryTrip.ended_at.is_(None))
        deleted = await session.scalars(
            delete(VehiclePosition)
            .where(
                or_(
                    VehiclePosition.trip_id.in_(ended_long_ago),
                    and_(VehiclePosition.trip_id.in_(no_end_time), VehiclePosition.recorded_at < cutoff),
                )
            )
            .returning(VehiclePosition.id)
        )
        count += len(deleted.all())
    return count


async def run() -> int:
    async with get_sessionmaker()() as session, session.begin():
        count = await purge_positions(session, now=clock.now())
    log_event("scheduler", "gps_retention", rows_processed=count)
    return count
