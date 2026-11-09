"""Canonical warehouse Prep Queue read model (06 Appendix A / A.1, PROPOSAL-M6-PREP-QUEUE-001).

Single implementation behind `GET /warehouses/{id}/prep-queue` (and its legacy alias). Read-only.

Official schedule verification (ASM-007, Q12d, BR-PRP-06). A day's capacity is `schedule_verified=true`
only when ALL of these hold for that warehouse and market-local day:
  1. at least one `hr.employee_shift_schedule` row with status `scheduled` exists;
  2. every such row was entered (`assigned_by`) by an employee who held an active `can_approve`
     `hr.location_manager` record for this warehouse on the market-local date of `assigned_at`;
  3. every such row resolves to a usable shift (template or explicit times, positive useful hours).
Anything else (no schedule, a row by an unauthorised person, an unusable row) is `false`: capacity is
reported as `total_min = free_min = 0`, `shifts = []`; booked workload and approved orders are still
returned because they come from persisted reservations/plans. `expected_staff` is never used.
Unexpected failures (missing market timezone, inconsistent approved plan) raise a standard error: they are
never turned into a 200 with invented numbers.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import MarketConfig
from app.core.errors import DomainError
from app.domain.models.hr import (
    Absence,
    Attendance,
    Employee,
    EmployeeAssignment,
    EmployeeShiftSchedule,
    LocationManager,
    ShiftTemplate,
    WarehouseStaff,
)
from app.domain.models.ops import CustomerOrder, DeliveryTrip, MilestoneEvent, OrderLine
from app.domain.models.plan import FulfilmentPlan, PlanningRun, PlanVehicle, PrepReservation
from app.domain.models.ref import HandlingGroup, Location, Market, MarketHoliday, ProductGlobal, Vehicle
from app.services import execution_service
from app.services.planning_inputs import _attendance_ok, _shift_times

QUEUE_STATUSES = ("APPROVED", "PREPARING", "GOODS_READY", "LOADED")
LOADED_TRIP_STATUSES = frozenset({"loading", "on_road", "completed"})
SIXTY = Decimal(60)


def _minutes(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _zone(market: Market) -> ZoneInfo:
    try:
        if not market.timezone or not market.timezone.strip():
            raise ValueError
        return ZoneInfo(market.timezone)
    except (ValueError, ZoneInfoNotFoundError, OSError):
        raise DomainError("INTERNAL_ERROR", "Market time zone configuration is invalid.") from None


def _share(market: Market) -> Decimal:
    try:
        return Decimal(str(MarketConfig.model_validate(market.config or {}).delivery_share))
    except ValueError:
        raise DomainError("INTERNAL_ERROR", "Market capacity configuration is invalid.") from None


def _allocate(total: int, weights: list[int]) -> list[int]:
    """Largest-remainder split so the parts add up exactly to `total` (no rounding drift)."""
    base = sum(weights)
    if total <= 0 or base <= 0:
        return [0] * len(weights)
    exact = [Decimal(total * w) / Decimal(base) for w in weights]
    parts = [int(x) for x in exact]
    order = sorted(range(len(weights)), key=lambda i: (exact[i] - parts[i], -i), reverse=True)
    for i in order[: total - sum(parts)]:
        parts[i] += 1
    return parts


async def _booked_minutes(session: AsyncSession, warehouse_id: int, day: date, now: datetime) -> int:
    """Committed and still-valid held labour per order, counted once per order (committed wins)."""
    rows = (
        await session.execute(
            select(PrepReservation.order_id, PrepReservation.status, PrepReservation.hours)
            .join(PlanningRun, PlanningRun.id == PrepReservation.run_id)
            .where(
                PrepReservation.warehouse_id == warehouse_id,
                PrepReservation.work_date == day,
                PrepReservation.resource == "labour",
                or_(
                    PrepReservation.status == "committed",
                    and_(PrepReservation.status == "held", PlanningRun.hold_expires_at > now),
                ),
            )
        )
    ).all()
    per_order: dict[int, dict[str, Decimal]] = defaultdict(
        lambda: {"committed": Decimal(0), "held": Decimal(0)}
    )
    for order_id, status, hours in rows:
        per_order[order_id][status] += Decimal(hours)
    total = Decimal(0)
    for hours_by_status in per_order.values():
        total += hours_by_status["committed"] if hours_by_status["committed"] > 0 else hours_by_status["held"]
    return _minutes(total * SIXTY)


async def _capacity(
    session: AsyncSession,
    warehouse: Location,
    market: Market,
    zone: ZoneInfo,
    day: date,
    now: datetime,
) -> dict[str, object]:
    today = now.astimezone(zone).date()
    booked = await _booked_minutes(session, warehouse.id, day, now)
    cutoff = f"{warehouse.loading_cutoff_time:%H:%M}" if warehouse.loading_cutoff_time else None
    unverified: dict[str, object] = {
        "booked_min": booked,
        "total_min": 0,
        "free_min": 0,
        "schedule_verified": False,
        "shifts": [],
        "cutoff": cutoff,
    }
    entries = (
        await session.execute(
            select(EmployeeShiftSchedule, ShiftTemplate)
            .outerjoin(ShiftTemplate, ShiftTemplate.id == EmployeeShiftSchedule.shift_template_id)
            .where(
                EmployeeShiftSchedule.warehouse_id == warehouse.id,
                EmployeeShiftSchedule.work_date == day,
                EmployeeShiftSchedule.status == "scheduled",
            )
        )
    ).all()
    if not entries:
        return unverified
    authorised: set[tuple[int, date]] = set()
    for row, _ in entries:
        assigned_day = row.assigned_at.astimezone(zone).date()
        ok = await session.scalar(
            select(LocationManager.id)
            .where(
                LocationManager.employee_id == row.assigned_by,
                LocationManager.location_id == warehouse.id,
                LocationManager.can_approve.is_(True),
                LocationManager.valid_from <= assigned_day,
                or_(LocationManager.valid_to.is_(None), LocationManager.valid_to >= assigned_day),
            )
            .limit(1)
        )
        if ok is not None:
            authorised.add((row.assigned_by, assigned_day))
    shifts_by_key: dict[tuple[time, time, Decimal], set[int]] = defaultdict(set)
    for row, template in entries:
        if (row.assigned_by, row.assigned_at.astimezone(zone).date()) not in authorised:
            return unverified  # a schedule entry not made by an authorised manager is never trusted
        info = _shift_times(row, template)
        if info is None:
            return unverified  # unusable shift definition: do not guess
        counted = await session.scalar(
            select(WarehouseStaff.employee_id)
            .join(Employee, Employee.id == WarehouseStaff.employee_id)
            .join(
                EmployeeAssignment,
                and_(
                    EmployeeAssignment.employee_id == WarehouseStaff.employee_id,
                    EmployeeAssignment.location_id == warehouse.id,
                    EmployeeAssignment.start_date <= day,
                    or_(EmployeeAssignment.end_date.is_(None), EmployeeAssignment.end_date >= day),
                ),
            )
            .where(
                WarehouseStaff.employee_id == row.employee_id,
                WarehouseStaff.counts_in_capacity.is_(True),
                Employee.status == "active",
            )
            .limit(1)
        )
        if counted is None:
            continue
        on_leave = await session.scalar(
            select(Absence.id)
            .where(
                Absence.employee_id == row.employee_id,
                Absence.approved.is_(True),
                Absence.start_date <= day,
                Absence.end_date >= day,
            )
            .limit(1)
        )
        status = await session.scalar(
            select(Attendance.status).where(
                Attendance.employee_id == row.employee_id, Attendance.work_date == day
            )
        )
        if on_leave is None and _attendance_ok(status, day, today):
            shifts_by_key[info].add(row.employee_id)
    holiday = (
        await session.scalar(
            select(MarketHoliday.holiday_date).where(
                MarketHoliday.market_id == market.id, MarketHoliday.holiday_date == day
            )
        )
    ) is not None
    share = _share(market)
    built: list[dict[str, object]] = []
    minutes_list: list[int] = []
    for (start, end, useful), people in sorted(shifts_by_key.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        start_at = datetime.combine(day, start, zone)
        end_at = datetime.combine(day if end > start else day + timedelta(days=1), end, zone)
        minutes = 0 if holiday else _minutes(Decimal(len(people)) * useful * share * SIXTY)
        minutes_list.append(minutes)
        built.append(
            {
                "name": f"{start:%H:%M}-{end:%H:%M}",
                "start": start_at.isoformat(),
                "end": end_at.isoformat(),
                "present": len(people),
                "useful_hours": float(useful),
                "share": float(share),
                "minutes": minutes,
            }
        )
    total = sum(minutes_list)
    for shift, part in zip(built, _allocate(booked, minutes_list), strict=True):
        shift["booked"] = part
    return {
        "booked_min": booked,
        "total_min": total,
        "free_min": max(0, total - booked),
        "schedule_verified": True,
        "shifts": built,
        "cutoff": cutoff,
    }


def _next_action(status: str, prep_state: str | None, loadings: list[dict[str, object]]) -> str | None:
    """Next event the (already authorised) warehouse caller may record; None when nothing is allowed."""
    if status == "APPROVED":
        return "START_PREP"
    if status == "PREPARING":
        return "PREP_RESUMED" if prep_state == "paused" else "GOODS_READY"
    if status in ("GOODS_READY", "LOADED") and any(not item["loaded"] for item in loadings):
        return "LOADED"
    return None


async def build(
    session: AsyncSession, actor: object, warehouse_id: int, day: date | None
) -> dict[str, object]:
    market = await execution_service._market(session, actor)
    zone = _zone(market)  # invalid market timezone fails before anything is read (never UTC)
    warehouse = await execution_service._warehouse(session, actor, warehouse_id, market)
    now = clock.now()
    day = day or now.astimezone(zone).date()
    capacity = await _capacity(session, warehouse, market, zone, day, now)

    pairs = (
        await session.execute(
            select(CustomerOrder, FulfilmentPlan)
            .join(FulfilmentPlan, FulfilmentPlan.id == CustomerOrder.approved_plan_id)
            .where(
                FulfilmentPlan.warehouse_id == warehouse.id,
                FulfilmentPlan.target_date == day,
                FulfilmentPlan.status.in_(("approved", "manual")),
                CustomerOrder.market_id == market.id,
                CustomerOrder.status.in_(QUEUE_STATUSES),
            )
            .order_by(CustomerOrder.submitted_at, CustomerOrder.id)
        )
    ).all()
    order_ids = [o.id for o, _ in pairs]
    plan_ids = [p.id for _, p in pairs]
    lines: dict[int, list[tuple[float, str, str]]] = defaultdict(list)
    line_count: dict[int, int] = defaultdict(int)
    milestones: dict[int, list[MilestoneEvent]] = defaultdict(list)
    loadings: dict[int, list[dict[str, object]]] = defaultdict(list)
    if order_ids:
        for order_id, qty, weight, code, name in (
            await session.execute(
                select(
                    OrderLine.order_id,
                    OrderLine.qty_base,
                    ProductGlobal.weight_kg,
                    HandlingGroup.code,
                    HandlingGroup.name,
                )
                .join(ProductGlobal, ProductGlobal.id == OrderLine.global_product_id)
                .join(HandlingGroup, HandlingGroup.id == ProductGlobal.handling_group_id)
                .where(OrderLine.order_id.in_(order_ids))
            )
        ).all():
            lines[order_id].append((float(Decimal(qty or 0) * Decimal(weight or 0)), code, name))
        for (order_id,) in (
            await session.execute(select(OrderLine.order_id).where(OrderLine.order_id.in_(order_ids)))
        ).all():
            line_count[order_id] += 1
        for event in (
            await session.scalars(
                select(MilestoneEvent)
                .where(
                    MilestoneEvent.order_id.in_(order_ids),
                    MilestoneEvent.event_type.in_(execution_service.WAREHOUSE_EVENTS),
                )
                .order_by(MilestoneEvent.occurred_at, MilestoneEvent.id)
            )
        ).all():
            milestones[event.order_id].append(event)
        cutoff_time = warehouse.loading_cutoff_time
        for plan_vehicle, trip, vehicle in (
            await session.execute(
                select(PlanVehicle, DeliveryTrip, Vehicle)
                .outerjoin(DeliveryTrip, DeliveryTrip.plan_vehicle_id == PlanVehicle.id)
                .join(Vehicle, Vehicle.id == PlanVehicle.vehicle_id)
                .where(PlanVehicle.plan_id.in_(plan_ids))
                .order_by(PlanVehicle.plan_id, PlanVehicle.seq)
            )
        ).all():
            if trip is None:
                raise DomainError("INTERNAL_ERROR", "An approved plan vehicle has no trip.")
            at = plan_vehicle.loading_start_at
            loadings[plan_vehicle.plan_id].append(
                {
                    "trip_id": trip.id,
                    "at": at.astimezone(zone).isoformat(),
                    "vehicle_code": vehicle.code,
                    "after_cutoff": bool(cutoff_time and at.astimezone(zone).time() > cutoff_time),
                    "loaded": trip.status in LOADED_TRIP_STATUSES,
                }
            )
    orders: list[dict[str, object]] = []
    for order, plan in pairs:
        events = milestones[order.id]
        prep_state: str | None = None
        for event in events:
            if event.event_type in ("START_PREP", "PREP_RESUMED"):
                prep_state = "running"
            elif event.event_type == "PREP_PAUSED":
                prep_state = "paused"
            elif event.event_type == "GOODS_READY":
                prep_state = None
        started = next((e for e in events if e.event_type == "START_PREP"), None)
        ready = next((e for e in events if e.event_type == "GOODS_READY"), None)
        mix = sorted({(code, name) for _, code, name in lines[order.id]})
        trip_loadings = loadings[plan.id]
        orders.append(
            {
                "order_id": order.id,
                "order_no": order.order_no,
                "lines": line_count[order.id],
                "weight_kg": round(sum(w for w, _, _ in lines[order.id]), 3),
                "handling_mix": [{"code": c, "name": n} for c, n in mix],
                "work_min": _minutes(Decimal(plan.prep_hours) * SIXTY),
                # Planned start is not persisted: only an actual START_PREP is a reliable start (else null).
                "prep_window": {
                    "start": started.occurred_at.astimezone(zone).isoformat() if started else None,
                    "end": (ready.occurred_at if ready else plan.goods_ready_at).astimezone(zone).isoformat(),
                },
                "loading": trip_loadings,
                "prep_state": prep_state,
                "status": order.status,
                "next_action": _next_action(order.status, prep_state, trip_loadings),
            }
        )
    return {
        "warehouse_id": warehouse.id,
        "date": day.isoformat(),
        "capacity": capacity,
        "orders": orders,
    }
