"""D3 GPS: verified trip-duty device ingestion, privacy cleanup and lost signals.

All writes participate in a caller-owned AsyncSession. GPS read access requires
a persisted dispatcher-to-trip assignment, which is not yet in the approved DB:
the APIs therefore fail closed, never fall back to market-wide access.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import ValidationError
from sqlalchemy import ColumnElement, and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import MarketConfig, get_settings
from app.core.errors import DomainError
from app.domain.models.hr import DriverAvailability
from app.domain.models.ops import (
    Alert,
    CustomerOrder,
    DeliveryTrip,
    EtaForecast,
    IdempotencyKey,
    MilestoneEvent,
    TripStop,
    VehiclePosition,
)
from app.domain.models.ref import ComplianceRecord, Location, Market, Vehicle
from app.providers.routing_ors import OrsRoutingProvider, RoutingUnavailable, route_with_fallback
from app.services import alert_service, risk_service
from app.services.gps_duty import active_duty, trip_collection_windows

MAX_GPS_BATCH_POSITIONS = 100  # Owner-approved G4 upload limit (DEC-OWNER-20261109)

@dataclass(frozen=True)
class RemainingRoute:
    """Verified routing output for T14 (route source is NOT the GPS point source)."""

    recorded_at: datetime
    remaining_km: Decimal
    remaining_min: int
    provider: Literal["ors", "fallback"]


PointSource = Literal["driver_tap", "driver_incident", "driver_completion"]


def _number(value: object, name: str, minimum: Decimal, maximum: Decimal) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise DomainError("VALIDATION_ERROR", f"Invalid GPS {name}.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DomainError("VALIDATION_ERROR", f"Invalid GPS {name}.") from exc
    if not number.is_finite() or not minimum <= number <= maximum:
        raise DomainError("VALIDATION_ERROR", f"Invalid GPS {name}.")
    return number


def _point_time(value: object) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DomainError("VALIDATION_ERROR", "GPS timestamp must be ISO 8601 with timezone.") from exc
    if not isinstance(value, datetime):
        raise DomainError("VALIDATION_ERROR", "GPS timestamp is required.")
    return _aware(value)


async def _trip_context(
    session: AsyncSession, trip_id: int,
) -> tuple[DeliveryTrip, Market, CustomerOrder]:
    row = (
        await session.execute(
            select(DeliveryTrip, Market, CustomerOrder)
            .join(Location, Location.id == DeliveryTrip.warehouse_id)
            .join(Market, Market.id == Location.market_id)
            .join(TripStop, TripStop.trip_id == DeliveryTrip.id)
            .join(CustomerOrder, CustomerOrder.id == TripStop.order_id)
            .where(DeliveryTrip.id == trip_id, TripStop.status == "pending")
            .with_for_update(of=DeliveryTrip)
        )
    ).all()
    if len(row) != 1:
        raise DomainError("NOT_ON_TRIP", "A uniquely identified active delivery stop is required.")
    return row[0]


async def record_point(
    session: AsyncSession, trip_id: int, point: Mapping[str, object], source: PointSource,
) -> RemainingRoute:
    """T13/T14 shared: write one verified point, no commit, no risk/ETA side effect.

    Caller owns transaction, identity/authorization and event decisions. This service
    verifies active trip + official availability and obtains authoritative route
    provenance; T13's endpoint calls RiskService exactly once after a new write.
    """
    if source not in ("driver_tap", "driver_incident", "driver_completion"):
        raise DomainError("VALIDATION_ERROR", "Unknown GPS point source.")
    if set(point) != {"lat", "lon", "accuracy_m", "recorded_at"}:
        raise DomainError("VALIDATION_ERROR", "A GPS point must contain exactly four fields.")
    at = _point_time(point["recorded_at"])
    now = _aware(clock.now())
    latitude = _number(point["lat"], "latitude", Decimal("-90"), Decimal("90"))
    longitude = _number(point["lon"], "longitude", Decimal("-180"), Decimal("180"))
    accuracy = _number(point["accuracy_m"], "accuracy", Decimal("0.000001"), Decimal("9999999"))
    trip, market, order = await _trip_context(session, trip_id)
    if not market.gps_enabled:
        raise DomainError("GPS_DISABLED", "GPS is disabled for this market.")
    if trip.status != "on_road" or trip.ended_at is not None or trip.depart_actual_at is None:
        raise DomainError("NOT_ON_TRIP", "Trip is no longer on the road.")
    if at > now or at < trip.depart_actual_at:
        raise DomainError("NOT_ON_TRIP", "GPS point is outside the active trip interval.")
    # New R3 official availability is explicit. Never infer it from a generated shift.
    availability = await session.scalar(
        select(DriverAvailability.id)
        .where(
            DriverAvailability.driver_employee_id == trip.driver_employee_id,
            DriverAvailability.superseded_at.is_(None),
            DriverAvailability.available_from <= at,
            DriverAvailability.available_from <= now,
            DriverAvailability.available_to > at,
            DriverAvailability.available_to > now,
            DriverAvailability.max_driving_min > 0,
        )
        .limit(1)
    )
    if availability is None:
        raise DomainError("NOT_ON_TRIP", "Verified driver availability is missing or inactive.")
    notice = await session.scalar(
        select(ComplianceRecord.id)
        .where(
            ComplianceRecord.market_id == market.id,
            ComplianceRecord.type == "GPS_NOTICE",
            ComplianceRecord.status == "approved",
        ).limit(1)
    )
    if notice is None:
        raise DomainError("FORBIDDEN", "Approved GPS privacy notice is unavailable.")
    earlier = await session.scalar(
        select(VehiclePosition.id)
        .where(VehiclePosition.trip_id == trip_id, VehiclePosition.recorded_at >= at)
        .limit(1)
    )
    if earlier is not None:
        raise DomainError("DUPLICATE_EVENT", "GPS timestamp must be newer than the last accepted point.")
    try:
        config = MarketConfig.model_validate(market.config or {})
    except ValidationError as exc:
        raise DomainError("PLAN_NOT_APPROVABLE", "Approved routing configuration is invalid.") from exc
    try:
        route = await route_with_fallback(
            OrsRoutingProvider(get_settings().ors_api_key or ""),
            float(latitude), float(longitude), float(order.delivery_lat), float(order.delivery_lon),
            allow_fallback=config.routing.allow_fallback,
        )
    except (RoutingUnavailable, ValueError) as exc:
        raise DomainError("PLAN_NOT_APPROVABLE", "Verified remaining route is unavailable.") from exc
    distance = route.distance_km.quantize(Decimal("0.1"))
    if not 0 <= distance < Decimal("1000000") or route.duration_min < 0:
        raise DomainError("PLAN_NOT_APPROVABLE", "Remaining route exceeds accepted bounds.")
    saved = VehiclePosition(
        trip_id=trip_id,
        vehicle_id=trip.vehicle_id,
        lat=latitude.quantize(Decimal("0.00001")),
        lon=longitude.quantize(Decimal("0.00001")),
        accuracy_m=accuracy.quantize(Decimal("0.1")),
        recorded_at=at,
        source=source,
        remaining_km=distance,
        remaining_min=route.duration_min,
        # DB provenance is "haversine_estimate"; the wire DTO calls it "fallback".
        route_source="haversine_estimate" if route.provider == "fallback" else "ors",
    )
    session.add(saved)
    await session.flush()
    return RemainingRoute(at, distance, route.duration_min, route.provider)


async def trusted_remaining_for_order(
    session: AsyncSession, order_id: int,
) -> dict[int, tuple[datetime, int]]:
    """Freshest persisted route durations for all trips in one approved order."""
    trip_ids = (
        await session.scalars(
            select(TripStop.trip_id).where(TripStop.order_id == order_id).distinct()
        )
    ).all()
    evidence: dict[int, tuple[datetime, int]] = {}
    for trip_id in trip_ids:
        latest = await session.scalar(
            select(VehiclePosition)
            .where(VehiclePosition.trip_id == trip_id)
            .order_by(VehiclePosition.recorded_at.desc(), VehiclePosition.id.desc()).limit(1)
        )
        if latest is not None:
            if latest.remaining_min is None or latest.route_source not in ("ors", "haversine_estimate"):
                raise DomainError("PLAN_NOT_APPROVABLE", "GPS route duration has no verified provenance.")
            evidence[trip_id] = (latest.recorded_at, latest.remaining_min)
    return evidence


async def post_driver_position(
    session: AsyncSession, trip_id: int, actor: object, point: Mapping[str, object], key: str,
) -> dict[str, object]:
    """202 API boundary: atomic replay, one new GPS point, one risk calculation."""
    _role(actor, "driver")
    actor_id = getattr(actor, "id", None)
    if not isinstance(actor_id, int) or actor_id <= 0:
        raise DomainError("FORBIDDEN", "An authenticated driver is required.")
    endpoint = f"POST /trips/{trip_id}/positions"
    normalized = {
        "lat": str(point.get("lat")), "lon": str(point.get("lon")),
        "accuracy_m": str(point.get("accuracy_m")),
        "recorded_at": _point_time(point.get("recorded_at")).isoformat(),
    }
    digest = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    other_user = await session.scalar(
        select(IdempotencyKey.user_id)
        .where(IdempotencyKey.key == key, IdempotencyKey.user_id != actor_id)
        .limit(1)
    )
    if other_user is not None:
        raise DomainError("IDEMPOTENCY_CONFLICT", "The request key belongs to another actor.")
    await session.execute(
        insert(IdempotencyKey)
        .values(key=key, user_id=actor_id, endpoint=endpoint, request_hash=digest)
        .on_conflict_do_nothing(index_elements=["key", "user_id"])
    )
    claim = await session.scalar(
        select(IdempotencyKey)
        .where(IdempotencyKey.key == key, IdempotencyKey.user_id == actor_id)
        .with_for_update()
    )
    if claim is None or claim.endpoint != endpoint or claim.request_hash != digest:
        raise DomainError("IDEMPOTENCY_CONFLICT", "The request key belongs to a different payload.")
    if claim.response_status == 202 and claim.response_body is not None:
        return dict(claim.response_body)
    if claim.response_status is not None:
        raise DomainError("IDEMPOTENCY_CONFLICT", "The prior request cannot be replayed.")
    # Important: no idempotency replay can reach the trip gate, recorder or RiskService.
    trip, _market = await _assigned_trip(session, trip_id, actor)
    result = await record_point(session, trip_id, point, "driver_tap")
    order_id = await session.scalar(select(TripStop.order_id).where(TripStop.trip_id == trip.id))
    if order_id is None:
        raise DomainError("NOT_ON_TRIP", "Delivery stop is unavailable.")
    await risk_service.recalculate(
        order_id,
        trigger="position",
        session=session,
        signal_at=result.recorded_at,
        trusted_remaining=await trusted_remaining_for_order(session, order_id),
    )
    response: dict[str, object] = {
        "accepted": 1,
        "trip_id": trip_id,
        "recorded_at": result.recorded_at.isoformat(),
        "remaining_km": str(result.remaining_km),
        "remaining_min": result.remaining_min,
        "provider": result.provider,
    }
    claim.response_status = 202
    claim.response_body = response
    await session.flush()
    return response


async def purge_order(session: AsyncSession, order_id: int) -> int:
    """T14/cancellation hook: purge coordinates in the caller transaction."""
    ids = select(TripStop.trip_id).where(TripStop.order_id == order_id).distinct()
    removed = await session.scalars(
        delete(VehiclePosition).where(VehiclePosition.trip_id.in_(ids)).returning(VehiclePosition.id)
    )
    return len(removed.all())





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


async def live(actor: object, *, session: AsyncSession | None = None) -> list[dict[str, object]]:
    """One latest point per assigned active trip, never market-wide or historical."""
    dispatcher_id = _role(actor, "dispatcher")
    if session is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "GPS live read requires a transaction.")
    now = _aware(clock.now())
    # R3 verified availability replaces the legacy per-person shift reader.
    available_drivers = set(
        (
            await session.scalars(
                select(DriverAvailability.driver_employee_id).where(
                    DriverAvailability.superseded_at.is_(None),
                    DriverAvailability.available_from <= now,
                    DriverAvailability.available_to > now,
                    DriverAvailability.max_driving_min > 0,
                )
            )
        ).all()
    )
    rows = (
        await session.execute(
            select(DeliveryTrip, Market, Vehicle, CustomerOrder)
            .join(Location, Location.id == DeliveryTrip.warehouse_id)
            .join(Market, Market.id == Location.market_id)
            .join(Vehicle, Vehicle.id == DeliveryTrip.vehicle_id)
            .join(TripStop, TripStop.trip_id == DeliveryTrip.id)
            .join(CustomerOrder, CustomerOrder.id == TripStop.order_id)
            .where(
                DeliveryTrip.assigned_dispatcher_employee_id == dispatcher_id,
                DeliveryTrip.status == "on_road",
                DeliveryTrip.ended_at.is_(None),
                DeliveryTrip.depart_actual_at.is_not(None),
                DeliveryTrip.depart_actual_at <= now,
                Market.gps_enabled.is_(True),
            )
            .order_by(DeliveryTrip.id)
        )
    ).all()
    output: list[dict[str, object]] = []
    for trip, market, vehicle, order in rows:
        if (
            market.code.strip() != str(getattr(actor, "market", "")).strip()
            or trip.driver_employee_id not in available_drivers
        ):
            continue
        point = await session.scalar(
            select(VehiclePosition)
            .where(VehiclePosition.trip_id == trip.id)
            .order_by(VehiclePosition.recorded_at.desc(), VehiclePosition.id.desc())
            .limit(1)
        )
        forecast = await session.scalar(
            select(EtaForecast)
            .where(EtaForecast.order_id == order.id)
            .order_by(EtaForecast.version.desc(), EtaForecast.id.desc())
            .limit(1)
        )
        unresolved = await session.scalar(
            select(Alert.id)
            .where(Alert.order_id == order.id, Alert.type == "DRIVER_INCIDENT", Alert.resolved_at.is_(None))
            .limit(1)
        )
        incident = None
        if unresolved is not None:
            incident_event = await session.scalar(
                select(MilestoneEvent)
                .where(
                    MilestoneEvent.order_id == order.id,
                    MilestoneEvent.trip_id == trip.id,
                    MilestoneEvent.event_type == "DRIVER_INCIDENT",
                )
                .order_by(MilestoneEvent.id.desc()).limit(1)
            )
            if incident_event is not None:
                candidate = incident_event.payload.get("reason")
                if candidate in ("vehicle_breakdown", "traffic_or_accident", "site_inaccessible", "other"):
                    incident = candidate
        output.append({
            "trip_id": trip.id,
            "order_id": order.id,
            "vehicle_code": vehicle.code,
            "last_position": {"lat": float(point.lat), "lon": float(point.lon)} if point else None,
            "remaining_km": str(point.remaining_km) if point and point.remaining_km is not None else None,
            "updated_at": point.recorded_at.isoformat() if point else None,
            "forecast_eta": forecast.forecast_eta.isoformat() if forecast else None,
            "risk": {"status": forecast.risk_status, "color": forecast.risk_color}
            if forecast else {"status": None, "color": None},
            "open_incident": incident,
        })
    return output


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
    # DELIVERED/CANCELLED never retain coordinates, regardless of the 7-day FAILED limit.
    terminal_trip_ids = (
        select(TripStop.trip_id)
        .join(CustomerOrder, CustomerOrder.id == TripStop.order_id)
        .where(CustomerOrder.status.in_(("DELIVERED", "CANCELLED")))
        .distinct()
    )
    terminals = await session.scalars(
        delete(VehiclePosition)
        .where(VehiclePosition.trip_id.in_(terminal_trip_ids))
        .returning(VehiclePosition.id)
    )
    terminal_count = len(terminals.all())
    expired = await session.scalars(
        delete(VehiclePosition)
        .where(VehiclePosition.recorded_at < when - RETENTION)
        .returning(VehiclePosition.id)
    )
    count = terminal_count + len(expired.all())
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
