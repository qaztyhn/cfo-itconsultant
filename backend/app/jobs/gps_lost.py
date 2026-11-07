"""US-GPS-03 AC1: GPS loss alerts without exposing coordinates or driver details.

The alert is resolved when the condition ends: a fresh position arrives for the trip, or the trip is no longer
on the road (completed/cancelled) or the market disables GPS. Only the dedupe key (trip id) is used.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import MarketConfig
from app.core.db import get_sessionmaker
from app.core.logging import log_event
from app.domain.models.ops import Alert, DeliveryTrip, VehiclePosition
from app.domain.models.ref import Location, Market
from app.services.alert_service import raise_alert, resolve


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
        if last_signal is not None and last_signal >= now - timedelta(minutes=lost_min):
            await resolve(session, _dedupe(trip.id), now=now)  # tín hiệu đã phục hồi
            continue
        if last_signal is not None:
            alert_id = await raise_alert(
                session,
                market_id=market.id,
                type_="GPS_LOST",
                level="warning",
                message="Trip GPS signal overdue.",
                dedupe_key=_dedupe(trip.id),
                target_roles=["dispatcher"],
            )
            created += int(alert_id is not None)
    await _resolve_stale(session, now=now)
    return created


def _dedupe(trip_id: int) -> str:
    return f"GPS_LOST:trip:{trip_id}"


async def _resolve_stale(session: AsyncSession, *, now: datetime) -> None:
    """Đóng GPS_LOST đang mở của chuyến không còn on_road hoặc market đã tắt GPS (không còn chờ tín hiệu)."""
    open_keys = (
        await session.scalars(
            select(Alert.dedupe_key).where(
                Alert.type == "GPS_LOST",
                Alert.resolved_at.is_(None),
                Alert.dedupe_key.like("GPS_LOST:trip:%"),
            )
        )
    ).all()
    for key in open_keys:
        trip_id = int(key.rsplit(":", 1)[1])
        still_tracked = await session.scalar(
            select(DeliveryTrip.id)
            .join(Location, Location.id == DeliveryTrip.warehouse_id)
            .join(Market, Market.id == Location.market_id)
            .where(DeliveryTrip.id == trip_id, DeliveryTrip.status == "on_road", Market.gps_enabled.is_(True))
        )
        if still_tracked is None:
            await resolve(session, key, now=now)


async def run() -> int:
    async with get_sessionmaker()() as session, session.begin():
        count = await check_lost(session, now=clock.now())
    log_event("scheduler", "gps_lost_check", rows_processed=count)
    return count
