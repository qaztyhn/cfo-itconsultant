"""D3 GPS: verified trip-duty device ingestion, privacy cleanup and lost signals.

All writes participate in a caller-owned AsyncSession. GPS read access requires
a persisted dispatcher-to-trip assignment, which is not yet in the approved DB:
the APIs therefore fail closed, never fall back to market-wide access.
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import MarketConfig
from app.core.errors import DomainError
from app.domain.models.ops import Alert, DeliveryTrip, VehiclePosition
from app.domain.models.ref import ComplianceRecord, Location, Market
from app.services import alert_service
from app.services.gps_duty import active_duty


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainError("VALIDATION_ERROR", "GPS timestamps must include a timezone.")
    return value.astimezone(UTC)


def _role(actor: object, role: str) -> int:
    employee = getattr(actor, "employee_id", None)
    if role not in getattr(actor, "roles", ()) or not isinstance(employee, int):
        raise DomainError("FORBIDDEN", "This GPS operation is not authorized.")
    return employee


def _market_config(market: Market) -> MarketConfig:
    try:
        cfg = MarketConfig.model_validate(market.config or {})
        approved = MarketConfig().gps
        if (
            cfg.gps.interval_min != approved.interval_min
            or cfg.gps.lost_min != approved.lost_min
        ):
            raise ValueError("Unapproved GPS collection or loss frequency")
        return cfg
    except ValueError as exc:
        raise DomainError("VALIDATION_ERROR", "Approved GPS configuration is unavailable.") from exc


async def _assigned_trip(session: AsyncSession, trip_id: int, actor: object) -> tuple[DeliveryTrip, Market]:
    employee_id = _role(actor, "driver")
    result = await session.execute(
        select(DeliveryTrip, Market)
        .join(Location, Location.id == DeliveryTrip.warehouse_id)
        .join(Market, Market.id == Location.market_id)
        .where(DeliveryTrip.id == trip_id, DeliveryTrip.driver_employee_id == employee_id)
        .with_for_update(of=DeliveryTrip)
    )
    item = result.one_or_none()
    if item is None:
        raise DomainError("NOT_FOUND", "Trip not found.")
    trip, market = item
    if market.code.strip() != str(getattr(actor, "market", "")).strip():
        raise DomainError("NOT_FOUND", "Trip not found.")
    return trip, market


async def ingest_positions(
    trip_id: int,
    actor: object,
    positions: list[Mapping[str, object]],
    *,
    session: AsyncSession | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """US-GPS-01: atomic, replay-safe device batch during current verified duty.

    Recorded-at may precede receipt for an offline upload, but cannot precede
    the current active duty or be uploaded after trip/shift termination.
    """
    if session is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "GPS requires the caller's transaction.")
    timestamp = _aware(now if now is not None else clock.now())
    trip, market = await _assigned_trip(session, trip_id, actor)
    if not market.gps_enabled:
        raise DomainError("GPS_DISABLED", "GPS is disabled in this market.")
    if trip.status != "on_road" or trip.ended_at is not None or trip.depart_actual_at is None:
        raise DomainError("NOT_ON_TRIP", "Trip is not actively on the road.")
    notice = await session.scalar(
        select(ComplianceRecord.id)
        .where(
            ComplianceRecord.market_id == market.id,
            ComplianceRecord.type == "GPS_NOTICE",
            ComplianceRecord.status == "approved",
        )
        .limit(1)
    )
    if notice is None:
        raise DomainError("FORBIDDEN", "An approved GPS privacy notice is required.")
    duty = (await active_duty(session, now=timestamp)).get(trip_id)
    if duty is None:
        raise DomainError("NOT_ON_TRIP", "Official driver shift is not active.")
    begins, ends = duty
    if not positions:
        raise DomainError("VALIDATION_ERROR", "GPS batch cannot be empty.")
    cfg = _market_config(market)
    existing = (
        await session.scalars(
            select(VehiclePosition)
            .where(VehiclePosition.trip_id == trip.id, VehiclePosition.source == "device")
            .order_by(VehiclePosition.recorded_at, VehiclePosition.id)
        )
    ).all()
    known: dict[datetime, VehiclePosition | dict[str, object]] = {
        item.recorded_at.astimezone(UTC): item for item in existing
    }
    new_rows: list[VehiclePosition] = []
    for pos in positions:
        recorded = pos.get("recorded_at")
        if not isinstance(recorded, datetime) or pos.get("source") != "device":
            raise DomainError("VALIDATION_ERROR", "Unverified GPS source or timestamp.")
        at = _aware(recorded)
        if not begins <= at <= timestamp or at >= ends:
            raise DomainError("NOT_ON_TRIP", "GPS point falls outside active driver duty.")
        try:
            lat, lon = Decimal(str(pos["lat"])), Decimal(str(pos["lon"]))
            accuracy = Decimal(str(pos["accuracy_m"])) if pos.get("accuracy_m") is not None else None
        except (KeyError, ValueError, TypeError) as exc:
            raise DomainError("VALIDATION_ERROR", "GPS point values are invalid.") from exc
        if (
            not lat.is_finite()
            or not lon.is_finite()
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
            or (accuracy is not None and (not accuracy.is_finite() or accuracy <= 0))
        ):
            raise DomainError("VALIDATION_ERROR", "GPS point values are invalid.")
        prior = known.get(at)
        if prior is not None:
            if isinstance(prior, VehiclePosition):
                matches = (
                    prior.source == "device"
                    and prior.lat == lat
                    and prior.lon == lon
                    and prior.accuracy_m == accuracy
                )
            else:
                matches = prior["lat"] == lat and prior["lon"] == lon and prior["accuracy_m"] == accuracy
            if not matches:
                raise DomainError("DUPLICATE_EVENT", "Conflicting GPS timestamp.")
            continue
        known[at] = {"lat": lat, "lon": lon, "accuracy_m": accuracy}
        new_rows.append(
            VehiclePosition(
                trip_id=trip.id,
                vehicle_id=trip.vehicle_id,
                lat=lat,
                lon=lon,
                accuracy_m=accuracy,
                recorded_at=at,
                source="device",
            )
        )
    times = sorted(known)
    cadence = timedelta(minutes=cfg.gps.interval_min)
    if any(b - a < cadence for a, b in zip(times, times[1:], strict=False)):
        raise DomainError("VALIDATION_ERROR", "GPS reporting exceeds approved cadence.")
    session.add_all(new_rows)
    await session.flush()
    return {"accepted": len(new_rows), "eta": None}


async def trip_positions(
    trip_id: int,
    actor: object,
    *,
    session: AsyncSession,
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    """Fail closed: dispatcher-trip mapping is not persisted/approved (D3)."""
    _role(actor, "dispatcher")
    raise DomainError("FORBIDDEN", "Verified dispatcher-to-trip assignment is unavailable.")


async def live(actor: object, *, session: AsyncSession | None = None) -> list[dict[str, object]]:
    """Never silently grant market-wide GPS positions to a dispatcher."""
    _role(actor, "dispatcher")
    raise DomainError("FORBIDDEN", "Verified dispatcher-to-trip assignment is unavailable.")


async def purge_trip_on_terminal(session: AsyncSession, trip_id: int, *, now: datetime | None = None) -> int:
    """Dev 1 hook: after terminal transition, before transaction commit.

    Also allows cleanup when the driver shift ended or GPS is disabled;
    refuses to delete an actively authorized session by mistake.
    """
    when = _aware(now if now is not None else clock.now())
    trip = await session.scalar(select(DeliveryTrip).where(DeliveryTrip.id == trip_id).with_for_update())
    if trip is None:
        raise DomainError("NOT_FOUND", "Trip not found.")
    if trip_id in await active_duty(session, now=when):
        raise DomainError("NOT_ON_TRIP", "Cannot purge an active GPS tracking session.")
    removed = await session.scalars(
        delete(VehiclePosition).where(VehiclePosition.trip_id == trip_id).returning(VehiclePosition.id)
    )
    return len(removed.all())


async def purge_expired(*, session: AsyncSession | None = None, now: datetime | None = None) -> int:
    """D3 compensating cleanup: invalid duty points are purged immediately, not after 30 days."""
    if session is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "GPS cleanup requires a transaction.")
    when = _aware(now if now is not None else clock.now())
    duty = await active_duty(session, now=when)
    authorized = or_(
        False,
        *(
            and_(
                VehiclePosition.trip_id == trip_id,
                VehiclePosition.recorded_at >= start,
                VehiclePosition.recorded_at < end,
                VehiclePosition.recorded_at <= when,
            )
            for trip_id, (start, end) in duty.items()
        ),
    )
    removed = await session.scalars(delete(VehiclePosition).where(~authorized).returning(VehiclePosition.id))
    return len(removed.all())


def _lost_key(trip_id: int) -> str:
    return f"GPS_LOST:trip:{trip_id}"


async def lost_check(*, session: AsyncSession | None = None, now: datetime | None = None) -> int:
    """US-GPS-03 AC1: deduped loss only for currently authorized trips/shifts.

    The existing gps_lost job and its scheduler remain unmodified.
    """
    if session is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "GPS loss check requires a transaction.")
    when = _aware(now if now is not None else clock.now())
    active = await active_duty(session, now=when)
    created = 0
    for trip_id, (started, _) in active.items():
        result = await session.execute(
            select(Market)
            .join(Location, Location.market_id == Market.id)
            .join(DeliveryTrip, DeliveryTrip.warehouse_id == Location.id)
            .where(DeliveryTrip.id == trip_id, Market.gps_enabled.is_(True))
        )
        market = result.scalar_one_or_none()
        if market is None:
            continue
        last = await session.scalar(
            select(func.max(VehiclePosition.recorded_at)).where(
                VehiclePosition.trip_id == trip_id,
                VehiclePosition.recorded_at >= started,
                VehiclePosition.recorded_at <= when,
            )
        )
        signal = max(started, last) if last is not None else started
        if when - signal > timedelta(minutes=_market_config(market).gps.lost_min):
            alert_id = await alert_service.raise_alert(
                session,
                market_id=market.id,
                type_="GPS_LOST",
                level="warning",
                message="Trip GPS signal overdue.",
                dedupe_key=_lost_key(trip_id),
                target_roles=("dispatcher",),
            )
            created += int(alert_id is not None)
        else:
            await alert_service.resolve(session, _lost_key(trip_id), now=when)
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
        trip = key.rsplit(":", 1)[-1]
        if trip.isdigit() and int(trip) not in active:
            await alert_service.resolve(session, key, now=when)
    return created
