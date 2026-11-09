"""D3 GPS: verified trip-duty device ingestion, privacy cleanup and lost signals.

All writes participate in a caller-owned AsyncSession. GPS read access requires
a persisted dispatcher-to-trip assignment, which is not yet in the approved DB:
the APIs therefore fail closed, never fall back to market-wide access.
"""

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import ColumnElement, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import MarketConfig
from app.core.errors import DomainError
from app.domain.models.ops import Alert, DeliveryTrip, VehiclePosition
from app.domain.models.ref import ComplianceRecord, Location, Market
from app.services import alert_service
from app.services.gps_duty import active_duty, trip_collection_windows

MAX_GPS_BATCH_POSITIONS = 100  # Owner-approved G4 upload limit (DEC-OWNER-20261109)


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
        if cfg.gps.interval_min != approved.interval_min or cfg.gps.lost_min != approved.lost_min:
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
    if not 1 <= len(positions) <= MAX_GPS_BATCH_POSITIONS:
        raise DomainError("VALIDATION_ERROR", "GPS batch must contain 1 to 100 positions.")
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
    cfg = _market_config(market)
    cadence = timedelta(minutes=cfg.gps.interval_min)
    requested: list[datetime] = []
    for pos in positions:
        recorded = pos.get("recorded_at")
        if not isinstance(recorded, datetime) or pos.get("source") != "device":
            raise DomainError("VALIDATION_ERROR", "Unverified GPS source or timestamp.")
        requested.append(_aware(recorded))
    # The trip/recorded_at index supports exact replay and narrow cadence probes.
    # Loading the entire trip history here grows without bound during a long trip.
    existing = (
        await session.scalars(
            select(VehiclePosition).where(
                VehiclePosition.trip_id == trip.id,
                VehiclePosition.source == "device",
                VehiclePosition.recorded_at.in_(set(requested)),
            )
        )
    ).all()
    known: dict[datetime, VehiclePosition | dict[str, object]] = {}
    for item in existing:
        at = item.recorded_at.astimezone(UTC)
        if at in known:
            raise DomainError("DUPLICATE_EVENT", "Conflicting GPS timestamp.")
        known[at] = item
    new_rows: list[VehiclePosition] = []
    for pos, at in zip(positions, requested, strict=True):
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
        too_close = await session.scalar(
            select(VehiclePosition.id)
            .where(
                VehiclePosition.trip_id == trip.id,
                VehiclePosition.source == "device",
                VehiclePosition.recorded_at > at - cadence,
                VehiclePosition.recorded_at < at + cadence,
            )
            .limit(1)
        )
        if too_close is not None:
            raise DomainError("VALIDATION_ERROR", "GPS reporting exceeds approved cadence.")
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
    new_times = sorted(row.recorded_at for row in new_rows)
    if any(b - a < cadence for a, b in zip(new_times, new_times[1:], strict=False)):
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


RETENTION = timedelta(days=7)  # DEC-GPS-RET-20261109: absolute 7 x 24 h, never wall-clock/DST based


def _valid_points(windows: Mapping[int, tuple[datetime, datetime]], when: datetime) -> ColumnElement[bool]:
    return or_(
        False,
        *(
            and_(
                VehiclePosition.trip_id == trip_id,
                VehiclePosition.recorded_at >= start,
                VehiclePosition.recorded_at < end,
                VehiclePosition.recorded_at <= when,  # a point from the future is never valid
            )
            for trip_id, (start, end) in windows.items()
        ),
    )


async def close_trip_collection(session: AsyncSession, trip_id: int, *, now: datetime | None = None) -> int:
    """Terminal hook for Dev 1 (replaces the immediate raw-GPS delete): runs in the completion transaction.

    Locks the trip row (serialising a late offline upload), refuses an active session, and removes only
    INVALID points (outside the verified collection window). Valid points stay for the 7-day retention and
    are no longer readable live: live read is already tied to an active duty session. Idempotent.
    """
    when = _aware(now if now is not None else clock.now())
    trip = await session.scalar(select(DeliveryTrip).where(DeliveryTrip.id == trip_id).with_for_update())
    if trip is None:
        raise DomainError("NOT_FOUND", "Trip not found.")
    if trip_id in await active_duty(session, now=when):
        raise DomainError("NOT_ON_TRIP", "Cannot close an active GPS tracking session.")
    windows = await trip_collection_windows(session, [trip_id])
    removed = await session.scalars(
        delete(VehiclePosition)
        .where(VehiclePosition.trip_id == trip_id, ~_valid_points(windows, when))
        .returning(VehiclePosition.id)
    )
    return len(removed.all())


async def purge_expired(*, session: AsyncSession | None = None, now: datetime | None = None) -> int:
    """Idempotent cleanup: (1) points older than 7 days, (2) invalid points immediately.

    Invalid = outside the verified duty/trip window of the point's trip (also for finished trips).
    Valid points of finished trips are kept until `recorded_at + 7 days`, which is never later than
    the collection-window end + 7 days. POD, milestones and duty/rest evidence are never touched.
    """
    if session is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "GPS cleanup requires a transaction.")
    when = _aware(now if now is not None else clock.now())
    expired = await session.scalars(
        delete(VehiclePosition)
        .where(VehiclePosition.recorded_at < when - RETENTION)
        .returning(VehiclePosition.id)
    )
    count = len(expired.all())
    trip_ids = [t for (t,) in (await session.execute(select(VehiclePosition.trip_id).distinct())).all()]
    windows = await trip_collection_windows(session, trip_ids)
    invalid = await session.scalars(
        delete(VehiclePosition).where(~_valid_points(windows, when)).returning(VehiclePosition.id)
    )
    return count + len(invalid.all())


HistoryAuthorizer = Callable[[AsyncSession, object, DeliveryTrip], Awaitable[bool]]


async def _deny(_session: AsyncSession, _actor: object, _trip: DeliveryTrip) -> bool:
    return False


async def read_history(
    session: AsyncSession,
    actor: object,
    trip_id: int,
    *,
    case_ref: str,
    reason: str,
    authorizer: HistoryAuthorizer = _deny,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    """Restricted post-trip investigation read (DEC-GPS-RET-20261109); NOT the live dispatcher path.

    Needs an explicit case and reason, an authorised reviewer for that market/trip, and writes an immutable
    audit row (no coordinates) in the same transaction. The reviewer-authority source is not approved yet,
    so the default authorizer DENIES: nothing is readable until a reviewed authorizer is wired in.
    """
    when = _aware(now if now is not None else clock.now())
    user_id = getattr(actor, "id", None)
    if not isinstance(user_id, int) or not case_ref.strip() or not reason.strip():
        raise DomainError("VALIDATION_ERROR", "A case reference and a reason are required.")
    row = (
        await session.execute(
            select(DeliveryTrip, Market)
            .join(Location, Location.id == DeliveryTrip.warehouse_id)
            .join(Market, Market.id == Location.market_id)
            .where(DeliveryTrip.id == trip_id)
        )
    ).one_or_none()
    if row is None or row[1].code.strip() != str(getattr(actor, "market", "")).strip():
        raise DomainError("NOT_FOUND", "Trip not found.")
    trip = row[0]
    if not await authorizer(session, actor, trip):
        raise DomainError("FORBIDDEN", "Historical GPS review is not authorized.")
    points = (
        await session.scalars(
            select(VehiclePosition)
            .where(VehiclePosition.trip_id == trip_id, VehiclePosition.recorded_at >= when - RETENTION)
            .order_by(VehiclePosition.recorded_at)
        )
    ).all()
    await record_decision(
        session,
        Action.GPS_HISTORY_ACCESSED,
        "trip",
        str(trip_id),
        reason_code="investigation",
        reason_text=reason.strip(),
        snapshot={"case_ref": case_ref.strip(), "points": len(points)},
        actor_user_id=user_id,
        actor_employee_id=getattr(actor, "employee_id", None),
        actor_role=next(iter(getattr(actor, "roles", ())), None),
    )
    return [
        {"recorded_at": p.recorded_at.isoformat(), "lat": float(p.lat), "lon": float(p.lon)} for p in points
    ]


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
