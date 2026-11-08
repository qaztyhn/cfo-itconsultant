"""M6 order execution: transactional milestones and scoped read models (06 §8).

Risk and notification services are currently unfinished. Their absence deliberately
rolls back writes rather than committing a milestone without mandatory follow-up.
No GPS coordinates, customer financial data or inferred driver-hour eligibility.
"""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import DomainError
from app.domain.enums import OrderStatus
from app.domain.models.hr import (
    DriverDutyLog,
    DriverStaff,
    Employee,
    EmployeeAssignment,
    EmployeeShiftSchedule,
    LocationManager,
    ShiftTemplate,
    WarehouseStaff,
)
from app.domain.models.ops import (
    CustomerOrder,
    DeliveryTrip,
    IdempotencyKey,
    MilestoneEvent,
    ProofOfDelivery,
    TripStop,
)
from app.domain.models.plan import FulfilmentPlan
from app.domain.models.ref import Location, Market, Vehicle
from app.domain.transitions import transition
from app.engine.actuals import LabourSegment, actual_labour_hours
from app.services import alert_service, notify_service, planning_service, risk_service

WAREHOUSE_EVENTS = frozenset(
    {"START_PREP", "PREP_PAUSED", "PREP_RESUMED", "GOODS_READY", "LOADED",
     "SHORTAGE", "BREAKAGE", "VEHICLE_ISSUE", "SHIFT_CHANGE"}
)
DRIVER_EVENTS = frozenset({"DISPATCHED", "DELIVERED", "FAILED"})
FAILURE_CODES = frozenset(
    {"customer_absent", "site_inaccessible", "refused", "wrong_address",
     "vehicle_breakdown", "goods_damaged", "other"}
)


def _attr(actor: object, key: str) -> object:
    return getattr(actor, key, None)


def _actor_id(actor: object) -> int:
    value = _attr(actor, "id")
    if type(value) is not int:
        raise DomainError("FORBIDDEN", "Authenticated user required.")
    return value


def _employee(actor: object) -> int:
    value = _attr(actor, "employee_id")
    if type(value) is not int:
        raise DomainError("FORBIDDEN", "Active employee assignment required.")
    return value


def _has_role(actor: object, role: str) -> bool:
    return role in tuple(_attr(actor, "roles") or ())


async def _market(session: AsyncSession, actor: object) -> Market:
    code = _attr(actor, "market")
    if not isinstance(code, str) or not code:
        raise DomainError("FORBIDDEN", "A market-scoped account is required.")
    market = await session.scalar(select(Market).where(Market.code == code))
    if market is None:
        raise DomainError("FORBIDDEN", "Market not available.")
    return market


async def _warehouse(session: AsyncSession, actor: object, warehouse_id: int, market: Market) -> Location:
    if not _has_role(actor, "warehouse"):
        raise DomainError("FORBIDDEN", "Warehouse role required.")
    if warehouse_id not in tuple(_attr(actor, "location_ids") or ()):
        raise DomainError("NOT_FOUND", "Warehouse not found.")
    warehouse = await session.scalar(
        select(Location).where(
            Location.id == warehouse_id, Location.market_id == market.id,
            Location.type == "warehouse", Location.is_active.is_(True)
        )
    )
    if warehouse is None:
        raise DomainError("NOT_FOUND", "Warehouse not found.")
    local_day = clock.now().astimezone(ZoneInfo(market.timezone)).date()
    authorised = await session.scalar(
        select(WarehouseStaff.employee_id)
        .join(LocationManager, LocationManager.employee_id == WarehouseStaff.employee_id)
        .where(
            WarehouseStaff.employee_id == _employee(actor),
            WarehouseStaff.role.in_(("manager", "deputy", "supervisor")),
            LocationManager.location_id == warehouse_id,
            LocationManager.valid_from <= local_day,
            or_(LocationManager.valid_to.is_(None), LocationManager.valid_to >= local_day),
        ).limit(1)
    )
    if authorised is None:
        raise DomainError("FORBIDDEN", "Active warehouse manager or supervisor required.")
    return warehouse


async def _order(session: AsyncSession, actor: object, order_id: int) -> tuple[CustomerOrder, Market]:
    market = await _market(session, actor)
    order = await session.scalar(
        select(CustomerOrder)
        .where(CustomerOrder.id == order_id, CustomerOrder.market_id == market.id)
        .with_for_update()
    )
    if order is None:
        raise DomainError("NOT_FOUND", "Order not found.")
    return order, market


async def _trips(session: AsyncSession, order_id: int) -> list[tuple[DeliveryTrip, TripStop]]:
    return list((await session.execute(
        select(DeliveryTrip, TripStop)
        .join(TripStop, TripStop.trip_id == DeliveryTrip.id)
        .where(TripStop.order_id == order_id)
        .order_by(DeliveryTrip.id)
        .with_for_update(of=(DeliveryTrip, TripStop))
    )).all())


def _require_positive(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise DomainError("VALIDATION_ERROR", f"{name} must be a positive integer.")
    return value


def _validate(event_type: str, data: dict[str, object]) -> None:
    required: dict[str, tuple[str, ...]] = {
        "START_PREP": ("crew_size",),
        "PREP_RESUMED": ("crew_size",),
        "LOADED": ("trip_id",),
        "DISPATCHED": ("trip_id",),
        "DELIVERED": ("trip_id", "recipient_name"),
        "FAILED": ("trip_id", "failure_reason"),
        "VEHICLE_ISSUE": ("vehicle_id",),
        "SHORTAGE": ("sku", "qty_missing"),
        "BREAKAGE": ("sku", "qty"),
        "SHIFT_CHANGE": ("date", "staff_present"),
    }
    permitted: dict[str, frozenset[str]] = {
        "START_PREP": frozenset({"crew_size"}),
        "PREP_PAUSED": frozenset({"note"}),
        "PREP_RESUMED": frozenset({"crew_size"}),
        "GOODS_READY": frozenset({"crew_size"}),
        "LOADED": frozenset({"trip_id"}),
        "DISPATCHED": frozenset({"trip_id"}),
        "DELIVERED": frozenset({"trip_id", "recipient_name", "note"}),
        "FAILED": frozenset({"trip_id", "failure_reason", "note"}),
        "VEHICLE_ISSUE": frozenset({"vehicle_id", "note"}),
        "SHORTAGE": frozenset({"sku", "qty_missing", "note"}),
        "BREAKAGE": frozenset({"sku", "qty", "note"}),
        "SHIFT_CHANGE": frozenset({"date", "staff_present", "note"}),
    }
    if event_type not in permitted:
        raise DomainError("VALIDATION_ERROR", "Unknown execution event type.")
    if set(data).difference(permitted[event_type]) or any(k not in data for k in required.get(event_type, ())):
        raise DomainError("VALIDATION_ERROR", "Event payload is incomplete or contains unknown fields.")
    for field in ("crew_size", "trip_id", "vehicle_id", "qty_missing", "qty"):
        if field in data:
            _require_positive(data[field], field)
    if "staff_present" in data and (type(data["staff_present"]) is not int or data["staff_present"] < 0):
        raise DomainError("VALIDATION_ERROR", "staff_present must be a nonnegative integer.")
    if "date" in data:
        try:
            date.fromisoformat(str(data["date"]))
        except ValueError as exc:
            raise DomainError("VALIDATION_ERROR", "Invalid shift date.") from exc
    for field in ("recipient_name", "failure_reason", "sku", "note"):
        if field in data and (not isinstance(data[field], str) or (field != "note" and not data[field].strip())):
            raise DomainError("VALIDATION_ERROR", f"Invalid {field}.")
    if event_type == "FAILED" and data["failure_reason"] not in FAILURE_CODES:
        raise DomainError("VALIDATION_ERROR", "Unknown failure reason.")


async def _claim(
    session: AsyncSession, actor: object, key: str, order_id: int,
    event_type: str, occurred_at: datetime, payload: dict[str, object]
) -> tuple[IdempotencyKey, dict[str, object] | None]:
    endpoint = f"POST /orders/{order_id}/events"
    digest = hashlib.sha256(json.dumps({
        "event_type": event_type, "occurred_at": occurred_at.isoformat(), "payload": payload
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    await session.execute(
        insert(IdempotencyKey).values(
            key=key, user_id=_actor_id(actor), endpoint=endpoint, request_hash=digest
        ).on_conflict_do_nothing(index_elements=["key", "user_id"])
    )
    row = await session.scalar(select(IdempotencyKey).where(
        IdempotencyKey.key == key, IdempotencyKey.user_id == _actor_id(actor)
    ).with_for_update())
    if row is None or row.endpoint != endpoint or row.request_hash != digest:
        raise DomainError("IDEMPOTENCY_CONFLICT", "Idempotency-Key belongs to a different request.")
    if row.response_status == 200 and row.response_body is not None:
        return row, dict(row.response_body)
    if row.response_status is not None:
        raise DomainError("IDEMPOTENCY_CONFLICT", "Earlier event cannot be replayed.")
    return row, None


def _labour(history: list[MilestoneEvent], event_type: str,
            occurred_at: datetime, payload: dict[str, object]) -> tuple[list[LabourSegment], bool]:
    """Derive exact crew segments from append-only event history; no staff scheduling assumption."""
    segments: list[LabourSegment] = []
    started: datetime | None = None
    crew = 0
    for kind, at, data in [
        *((e.event_type, e.occurred_at, e.payload) for e in history
          if e.event_type in ("START_PREP", "PREP_PAUSED", "PREP_RESUMED", "GOODS_READY")),
        (event_type, occurred_at, payload),
    ]:
        if kind in ("START_PREP", "PREP_RESUMED"):
            if started is not None:
                raise DomainError("ILLEGAL_TRANSITION", "Preparation already running.")
            if kind == "PREP_RESUMED" and not segments:
                raise DomainError("ILLEGAL_TRANSITION", "Preparation was not paused.")
            started = at
            crew = int(data["crew_size"])
        elif kind == "PREP_PAUSED":
            if started is None or started >= at:
                raise DomainError("ILLEGAL_TRANSITION", "Preparation is not running.")
            segments.append(LabourSegment(started, at, crew))
            started = None
        elif kind == "GOODS_READY":
            if started is None or started >= at:
                raise DomainError("ILLEGAL_TRANSITION", "Preparation is not running.")
            segments.append(LabourSegment(started, at, int(data.get("crew_size", crew))))
            started = None
    return segments, started is not None


async def _driver_gate(session: AsyncSession, actor: object, trip: DeliveryTrip,
                       market: Market, occurred_at: datetime) -> None:
    """Official shift and licence checks; missing 56-day completeness marker never authorizes duty."""
    if not _has_role(actor, "driver") or trip.driver_employee_id != _employee(actor):
        raise DomainError("FORBIDDEN", "Driver is not assigned to this trip.")
    zone = ZoneInfo(market.timezone)
    local = occurred_at.astimezone(zone)
    driver = await session.get(DriverStaff, trip.driver_employee_id)
    employee = await session.get(Employee, trip.driver_employee_id)
    vehicle = await session.get(Vehicle, trip.vehicle_id)
    if driver is None or employee is None or vehicle is None or employee.status != "active":
        raise DomainError("PLAN_NOT_APPROVABLE", "Verified driver and vehicle data required.")
    if driver.licence_expires_on < local.date():
        raise DomainError("LICENCE_EXPIRED", "Driver licence has expired.")
    if vehicle.regulation_561_scope == "unknown" or vehicle.max_permissible_mass_kg is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "Vehicle regulatory scope is unverified.")
    if employee.market_id != market.id:
        raise DomainError("FORBIDDEN", "Driver is outside the market.")
    assigned = await session.scalar(select(EmployeeAssignment.id).where(
        EmployeeAssignment.employee_id == employee.id,
        EmployeeAssignment.location_id == trip.warehouse_id,
        EmployeeAssignment.start_date <= local.date(),
        or_(EmployeeAssignment.end_date.is_(None), EmployeeAssignment.end_date >= local.date())
    ))
    if assigned is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "Driver has no effective warehouse assignment.")
    rows = (await session.execute(
        select(EmployeeShiftSchedule, ShiftTemplate)
        .outerjoin(ShiftTemplate, ShiftTemplate.id == EmployeeShiftSchedule.shift_template_id)
        .where(
            EmployeeShiftSchedule.employee_id == employee.id,
            EmployeeShiftSchedule.warehouse_id == trip.warehouse_id,
            EmployeeShiftSchedule.status == "scheduled",
            EmployeeShiftSchedule.work_date.in_((local.date(), local.date() - timedelta(days=1)))
        )
    )).all()
    valid_shift = False
    for row, template in rows:
        start = row.start_time or (template.start_time if template else None)
        end = row.end_time or (template.end_time if template else None)
        if start is None or end is None or start == end:
            continue
        if template and template.warehouse_id != trip.warehouse_id:
            continue
        begin = datetime.combine(row.work_date, start, zone)
        finish = datetime.combine(row.work_date + timedelta(days=int(end < start)), end, zone)
        if any(t.replace(fold=0).utcoffset() != t.replace(fold=1).utcoffset()
               for t in (begin, finish)):
            continue
        if begin <= local < finish:
            valid_shift = True
    if not valid_shift:
        raise DomainError("PLAN_NOT_APPROVABLE", "Event is outside the verified official driver shift.")
    history = (await session.scalars(select(DriverDutyLog).where(
        DriverDutyLog.employee_id == employee.id,
        DriverDutyLog.duty_end >= occurred_at - timedelta(days=56),
        DriverDutyLog.duty_start < occurred_at
    ))).all()
    if history and any(
        0 <= (occurred_at - duty.duty_end).total_seconds() < 11 * 3600 for duty in history
    ):
        raise DomainError("PLAN_NOT_APPROVABLE", "Required 11-hour driver rest is not verified.")
    # Database stores observed duty intervals, but has no evidence that the
    # last 56 days were reported completely (see planning_inputs.py §Q12b).
    # A nonempty duty log is *not* permission to drive.
    raise DomainError("PLAN_NOT_APPROVABLE", "Driver 56-day history completeness is not verified.")


async def record_event(session: AsyncSession, order_id: int, actor: object, event_type: str,
                       occurred_at: datetime, payload: dict[str, object],
                       idempotency_key: str) -> dict[str, object]:
    """Transaction owned by caller; no commit until mandatory ETA/outbox effects succeed."""
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise DomainError("VALIDATION_ERROR", "occurred_at must have a timezone offset.")
    if occurred_at > clock.now() + timedelta(minutes=5):
        raise DomainError("VALIDATION_ERROR", "occurred_at is too far in the future.")
    _validate(event_type, payload)
    if event_type not in WAREHOUSE_EVENTS | DRIVER_EVENTS:
        raise DomainError("VALIDATION_ERROR", "Unsupported execution event.")
    if not (_has_role(actor, "warehouse") if event_type in WAREHOUSE_EVENTS else _has_role(actor, "driver")):
        raise DomainError("FORBIDDEN", "Event role not permitted.")
    order, market = await _order(session, actor, order_id)
    record, replay = await _claim(
        session, actor, idempotency_key, order_id, event_type, occurred_at, payload
    )
    if replay is not None:
        return replay
    if order.approved_plan_id is None:
        raise DomainError("ILLEGAL_TRANSITION", "Order has no approved execution plan.")
    plan = await session.get(FulfilmentPlan, order.approved_plan_id)
    if plan is None or plan.order_id != order.id or plan.status not in ("approved", "manual"):
        raise DomainError("PLAN_NOT_APPROVABLE", "Approved plan is unavailable.")
    if event_type in WAREHOUSE_EVENTS:
        await _warehouse(session, actor, plan.warehouse_id, market)
    trips = await _trips(session, order.id)
    if event_type in {"LOADED", "DISPATCHED", "DELIVERED", "FAILED"} and not trips:
        raise DomainError("ILLEGAL_TRANSITION", "No approved trips are assigned.")
    trip: DeliveryTrip | None = None
    stop: TripStop | None = None
    if event_type in DRIVER_EVENTS | {"LOADED"}:
        pair = next(((t, s) for t, s in trips if t.id == payload["trip_id"]), None)
        if pair is None:
            raise DomainError("NOT_FOUND", "Trip not found.")
        trip, stop = pair
        if event_type in DRIVER_EVENTS:
            await _driver_gate(session, actor, trip, market, occurred_at)
    previous = (await session.scalars(select(MilestoneEvent)
        .where(MilestoneEvent.order_id == order_id)
        .order_by(MilestoneEvent.occurred_at, MilestoneEvent.id)
        .with_for_update())).all()
    if previous and occurred_at < previous[-1].occurred_at:
        raise DomainError("ILLEGAL_TRANSITION", "Event occurred before the last recorded event.")
    segments: list[LabourSegment] = []
    event_data = dict(payload)
    if event_type in {"START_PREP", "PREP_PAUSED", "PREP_RESUMED", "GOODS_READY"}:
        if event_type == "START_PREP" and order.status != "APPROVED":
            raise DomainError("ILLEGAL_TRANSITION", "Preparation must start on an approved order.")
        if event_type != "START_PREP" and order.status != "PREPARING":
            raise DomainError("ILLEGAL_TRANSITION", "Order is not being prepared.")
        segments, running = _labour(previous, event_type, occurred_at, payload)
        if event_type in {"START_PREP", "PREP_RESUMED"} and not running:
            raise DomainError("ILLEGAL_TRANSITION", "Preparation could not be resumed.")
        if event_type == "GOODS_READY":
            hours = actual_labour_hours(segments)
            event_data["actual_labour_hours"] = str(hours.quantize(Decimal("0.001")))
            event_data["labour_segments"] = [
                {"start": s.start.isoformat(), "end": s.end.isoformat(), "crew_size": s.crew_size}
                for s in segments
            ]
        if event_type == "START_PREP":
            await transition(session, order.id, OrderStatus.PREPARING, "warehouse")
        if event_type == "GOODS_READY":
            await transition(session, order.id, OrderStatus.GOODS_READY, "warehouse")
    elif event_type == "LOADED":
        assert trip is not None
        if order.status != "GOODS_READY" or trip.status != "planned":
            raise DomainError("ILLEGAL_TRANSITION", "Trip is not ready for loading.")
        trip.status = "loading"
        if all(t.status == "loading" for t, _ in trips):
            await transition(session, order.id, OrderStatus.LOADED, "warehouse")
    elif event_type == "DISPATCHED":
        assert trip is not None
        if order.status not in ("LOADED", "DISPATCHED") or trip.status != "loading":
            raise DomainError("ILLEGAL_TRANSITION", "Trip is not loaded.")
        trip.status, trip.depart_actual_at = "on_road", occurred_at
        if order.status == "LOADED":
            await transition(session, order.id, OrderStatus.DISPATCHED, "driver")
    elif event_type in ("DELIVERED", "FAILED"):
        assert trip is not None and stop is not None
        if order.status != "DISPATCHED" or trip.status != "on_road" or stop.status != "pending":
            raise DomainError("ILLEGAL_TRANSITION", "Trip stop cannot be completed.")
        outcome = "delivered" if event_type == "DELIVERED" else "failed"
        stop.status, stop.completed_at = outcome, occurred_at
        trip.status, trip.ended_at = "completed", occurred_at
        session.add(ProofOfDelivery(
            trip_stop_id=stop.id, order_id=order.id, result=outcome, completed_at=occurred_at,
            recipient_name=payload.get("recipient_name") if isinstance(payload.get("recipient_name"), str) else None,
            failure_reason=payload.get("failure_reason") if isinstance(payload.get("failure_reason"), str) else None,
            note=payload.get("note") if isinstance(payload.get("note"), str) else None,
        ))
        if all(s.status in ("delivered", "failed") for _, s in trips):
            if all(s.status == "delivered" for _, s in trips):
                await transition(session, order.id, OrderStatus.DELIVERED, "driver")
                order.delivered_at = occurred_at
            else:
                await transition(session, order.id, OrderStatus.FAILED, "driver",
                                 str(payload.get("failure_reason", "partial_delivery")))
    elif event_type == "VEHICLE_ISSUE":
        if not any(t.vehicle_id == payload["vehicle_id"] for t, _ in trips):
            raise DomainError("NOT_FOUND", "Vehicle not assigned to this order.")
        await alert_service.raise_alert(
            session, market_id=market.id, order_id=order.id, type_="EXCEPTION",
            level="warning", message="Vehicle issue reported for dispatcher review.",
            target_roles=["dispatcher"], dedupe_key=f"vehicle-issue:{order.id}:{payload['vehicle_id']}"
        )
        await planning_service.suggest_replan(order.id, "vehicle_issue", session=session)
    elif event_type in ("SHORTAGE", "BREAKAGE"):
        await alert_service.raise_alert(
            session, market_id=market.id, order_id=order.id, type_="EXCEPTION",
            level="warning", message="Warehouse exception reported.",
            target_roles=["dispatcher"], dedupe_key=f"warehouse-exception:{order.id}:{event_type}"
        )
    session.add(MilestoneEvent(
        order_id=order.id, plan_id=order.approved_plan_id,
        trip_id=trip.id if trip else None, event_type=event_type, occurred_at=occurred_at.astimezone(UTC),
        actor_user_id=_actor_id(actor), actor_employee_id=_employee(actor),
        payload=event_data, idempotency_key=idempotency_key,
    ))
    await session.flush()
    new_event = await session.scalar(select(MilestoneEvent).where(
        MilestoneEvent.idempotency_key == idempotency_key
    ))
    assert new_event is not None
    try:
        risk = await risk_service.recalculate(order.id, f"event:{event_type}")
        if event_type in ("DISPATCHED", "DELIVERED", "FAILED") and order.status == event_type:
            await notify_service.enqueue(order.id, event_type, plan_id=order.approved_plan_id)
    except NotImplementedError as exc:
        raise DomainError(
            "PLAN_NOT_APPROVABLE", "Mandatory ETA or notification integration is not available."
        ) from exc
    if risk is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "ETA recalculation did not produce a verified result.")
    result: dict[str, object] = {
        "event_id": new_event.id, "order_status": order.status, "risk": risk
    }
    if event_type == "GOODS_READY":
        result["actual_labour_hours"] = event_data["actual_labour_hours"]
    record.response_status, record.response_body = 200, result
    return result


async def driver_trips(session: AsyncSession, actor: object, day: date | None = None,
                       trip_id: int | None = None) -> dict[str, object]:
    """Only trips assigned to authenticated driver; no totals, scores, coordinates or GPS."""
    if not _has_role(actor, "driver"):
        raise DomainError("FORBIDDEN", "Driver role required.")
    market = await _market(session, actor)
    zone = ZoneInfo(market.timezone)
    day = day or clock.now().astimezone(zone).date()
    stmt = (select(DeliveryTrip, TripStop, CustomerOrder, Vehicle, Location)
            .join(TripStop, TripStop.trip_id == DeliveryTrip.id)
            .join(CustomerOrder, CustomerOrder.id == TripStop.order_id)
            .join(Vehicle, Vehicle.id == DeliveryTrip.vehicle_id)
            .join(Location, Location.id == DeliveryTrip.warehouse_id)
            .where(DeliveryTrip.driver_employee_id == _employee(actor),
                   CustomerOrder.market_id == market.id, Location.market_id == market.id))
    if trip_id is not None:
        stmt = stmt.where(DeliveryTrip.id == trip_id)
    else:
        stmt = stmt.where(cast(func.timezone(market.timezone, DeliveryTrip.depart_planned_at), Date) == day)
    result: dict[int, dict[str, object]] = {}
    for trip, stop, order, vehicle, warehouse in (await session.execute(
        stmt.order_by(DeliveryTrip.id, TripStop.seq)
    )).all():
        row = result.setdefault(trip.id, {
            "trip_id": trip.id, "warehouse_id": warehouse.id,
            "warehouse_code": warehouse.code, "vehicle_code": vehicle.code,
            "status": trip.status, "depart_planned_at": trip.depart_planned_at.isoformat(),
            "depart_actual_at": trip.depart_actual_at.isoformat() if trip.depart_actual_at else None,
            "stops": [],
        })
        stops = row["stops"]
        assert isinstance(stops, list)
        stops.append({
            "trip_stop_id": stop.id, "order_id": order.id, "order_no": order.order_no,
            "status": stop.status, "eta_planned_at": stop.eta_planned_at.isoformat(),
            "delivery_address": order.delivery_address,
            "contact_name": order.contact_name, "contact_phone": order.contact_phone,
            "receiving_window": {
                "start": order.window_start.isoformat() if order.window_start else None,
                "end": order.window_end.isoformat() if order.window_end else None,
            }, "special_requirements": order.special_requirements,
        })
    if trip_id is not None:
        if trip_id not in result:
            raise DomainError("NOT_FOUND", "Trip not found.")
        return result[trip_id]
    return {"items": list(result.values())}


async def prep_queue(session: AsyncSession, warehouse_id: int, day: date | None,
                     actor: object) -> dict[str, object]:
    """Market and manager scoped warehouse queue; never guesses staffing or attendance."""
    market = await _market(session, actor)
    await _warehouse(session, actor, warehouse_id, market)
    day = day or clock.now().astimezone(ZoneInfo(market.timezone)).date()
    stmt = (select(CustomerOrder, FulfilmentPlan)
            .join(FulfilmentPlan, FulfilmentPlan.id == CustomerOrder.approved_plan_id)
            .where(FulfilmentPlan.warehouse_id == warehouse_id,
                   FulfilmentPlan.target_date == day,
                   CustomerOrder.market_id == market.id,
                   CustomerOrder.status.in_(("APPROVED", "PREPARING", "GOODS_READY", "LOADED")))
            .order_by(CustomerOrder.submitted_at, CustomerOrder.id))
    items: list[dict[str, object]] = []
    for order, plan in (await session.execute(stmt)).all():
        milestones = (await session.scalars(select(MilestoneEvent)
            .where(MilestoneEvent.order_id == order.id)
            .order_by(MilestoneEvent.occurred_at, MilestoneEvent.id))).all()
        items.append({
            "order_id": order.id, "order_no": order.order_no, "status": order.status,
            "planned_prep_hours": str(plan.prep_hours), "workload": plan.workload,
            "goods_ready_planned_at": plan.goods_ready_at.isoformat(),
            "events": [{"event_type": m.event_type, "occurred_at": m.occurred_at.isoformat()}
                       for m in milestones if m.event_type in WAREHOUSE_EVENTS],
        })
    return {"warehouse_id": warehouse_id, "date": day.isoformat(), "items": items}
