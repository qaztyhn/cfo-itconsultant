"""Verified database inputs for T14's pure planner.

No external calls, optimistic inventory locks or synthetic shifts. Q12/Q12b:
absence of an official shift or proven 56-day driver history fails closed.
The D7 source completeness marker is not present in the current schema; a
nonempty duty log is NOT evidence that all duty/rest records were ingested.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MarketConfig
from app.core.errors import DomainError
from app.domain.models.hr import (
    Absence,
    Attendance,
    DriverDutyLog,
    Employee,
    EmployeeAssignment,
    EmployeeShiftSchedule,
    ShiftTemplate,
    WarehouseStaff,
)
from app.domain.models.ops import CustomerOrder, OrderLine, StockSnapshot
from app.domain.models.ref import (
    HandlingGroup,
    Location,
    Market,
    MarketHoliday,
    ProductGlobal,
    ProductSE,
    SpecialFlag,
    Vehicle,
)
from app.engine.types import (
    DayCapacity,
    DriverCtx,
    HandlingGroupCtx,
    LineCtx,
    OrderCtx,
    PrepUnitT,
    ShiftCapacity,
    VehicleCtx,
    WarehouseCtx,
)
from app.services.hr_service import day_capacities
from app.services.planning_context import available_stock, confirmed_inbound, fleet_context, route_info
from app.services.planning_service import engine_config


@dataclass(frozen=True)
class PlanningInputs:
    order: OrderCtx
    warehouses: tuple[WarehouseCtx, ...]
    config: object
    snapshot: dict[str, object]


def _problem(message: str) -> DomainError:
    return DomainError("PLAN_NOT_APPROVABLE", message)


def _shift_times(
    row: EmployeeShiftSchedule, template: ShiftTemplate | None
) -> tuple[time, time, Decimal] | None:
    if template is not None and template.warehouse_id != row.warehouse_id:
        return None
    start = row.start_time or (template.start_time if template is not None else None)
    end = row.end_time or (template.end_time if template is not None else None)
    if start is None or end is None or start == end:
        return None
    if template is not None and row.start_time is None:
        useful = template.useful_hours_per_staff
    else:
        minutes = ((end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)) % (24 * 60)
        useful = Decimal(minutes) / 60
        if row.break_start is not None and row.break_end is not None:
            rest = (
                (row.break_end.hour * 60 + row.break_end.minute)
                - (row.break_start.hour * 60 + row.break_start.minute)
            ) % (24 * 60)
            useful -= Decimal(rest) / 60
    if useful <= 0:
        return None
    return start, end, useful


def _attendance_ok(status: str | None, day: date, today: date) -> bool:
    return status == "present" or (status == "planned" and day > today)


async def official_warehouse_capacity(
    session: AsyncSession,
    warehouse_id: int,
    days: list[date],
    *,
    now: datetime,
    zone: ZoneInfo,
    exclude_order_id: int,
) -> tuple[dict[date, DayCapacity], tuple[tuple[datetime, datetime], ...]]:
    """Only explicitly scheduled, assigned, attended employees count (never expected_staff)."""
    if not days:
        return {}, ()
    today = now.astimezone(zone).date()
    original = await day_capacities(
        session, warehouse_id, days, now=now, today=today, exclude_order_id=exclude_order_id
    )
    rows = (
        await session.execute(
            select(EmployeeShiftSchedule, ShiftTemplate, Attendance.status)
            .join(WarehouseStaff, WarehouseStaff.employee_id == EmployeeShiftSchedule.employee_id)
            .join(Employee, Employee.id == EmployeeShiftSchedule.employee_id)
            .join(
                EmployeeAssignment,
                and_(
                    EmployeeAssignment.employee_id == EmployeeShiftSchedule.employee_id,
                    EmployeeAssignment.location_id == warehouse_id,
                    EmployeeAssignment.start_date <= EmployeeShiftSchedule.work_date,
                    or_(
                        EmployeeAssignment.end_date.is_(None),
                        EmployeeAssignment.end_date >= EmployeeShiftSchedule.work_date,
                    ),
                ),
            )
            .outerjoin(ShiftTemplate, ShiftTemplate.id == EmployeeShiftSchedule.shift_template_id)
            .outerjoin(
                Attendance,
                and_(
                    Attendance.employee_id == EmployeeShiftSchedule.employee_id,
                    Attendance.work_date == EmployeeShiftSchedule.work_date,
                ),
            )
            .where(
                EmployeeShiftSchedule.warehouse_id == warehouse_id,
                EmployeeShiftSchedule.work_date.between(min(days), max(days)),
                EmployeeShiftSchedule.status == "scheduled",
                WarehouseStaff.counts_in_capacity.is_(True),
                Employee.status == "active",
            )
        )
    ).all()
    absent = {
        (emp, d)
        for emp, d in (
            await session.execute(
                select(Absence.employee_id, EmployeeShiftSchedule.work_date)
                .join(
                    EmployeeShiftSchedule,
                    EmployeeShiftSchedule.employee_id == Absence.employee_id,
                )
                .where(
                    EmployeeShiftSchedule.warehouse_id == warehouse_id,
                    EmployeeShiftSchedule.work_date.between(min(days), max(days)),
                    Absence.approved.is_(True),
                    Absence.start_date <= EmployeeShiftSchedule.work_date,
                    Absence.end_date >= EmployeeShiftSchedule.work_date,
                )
            )
        ).all()
    }
    grouped: dict[date, dict[tuple[time, time, Decimal], set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for shift, template, status in rows:
        if (shift.employee_id, shift.work_date) in absent:
            continue
        if not _attendance_ok(status, shift.work_date, today):
            continue
        info = _shift_times(shift, template)
        # The work-preparation engine's DayCapacity is same-day only.
        # Overnight shifts are not counted here until split into verified local days.
        if info is None or info[1] <= info[0]:
            continue
        grouped[shift.work_date][info].add(shift.employee_id)
    capacities: dict[date, DayCapacity] = {}
    windows: list[tuple[datetime, datetime]] = []
    for day in days:
        shifts: list[ShiftCapacity] = []
        for (start, end, useful), people in sorted(grouped[day].items(), key=lambda x: x[0][0]):
            shifts.append(ShiftCapacity(f"{start:%H:%M}-{end:%H:%M}", start, end, len(people), useful))
            windows.append((datetime.combine(day, start, zone), datetime.combine(day, end, zone)))
        capacities[day] = DayCapacity(day, tuple(shifts), original[day].booked_hours)
    return capacities, tuple(windows)


async def official_driver_context(
    session: AsyncSession,
    warehouse_id: int,
    vehicles: tuple[VehicleCtx, ...],
    drivers: tuple[DriverCtx, ...],
    *,
    days: list[date],
    now: datetime,
    zone: ZoneInfo,
) -> tuple[tuple[VehicleCtx, ...], tuple[DriverCtx, ...]]:
    """Attach official whole-duty shifts and recorded driving history; never infer completeness."""
    if not days:
        return vehicles, drivers
    vehicle_ids = {v.id for v in vehicles}
    vehicle_rows = (
        await session.scalars(select(Vehicle).where(Vehicle.id.in_(vehicle_ids)))
    ).all()
    scope = {
        v.id: {"in_scope": True, "out_of_scope": False}.get(v.regulation_561_scope)
        for v in vehicle_rows
    }
    vehicles = tuple(replace(v, regulation_561=scope.get(v.id)) for v in vehicles)
    ids = {d.employee_id for d in drivers}
    starts = min(days) - timedelta(days=1)
    ends = max(days)
    records = (
        await session.execute(
            select(EmployeeShiftSchedule, ShiftTemplate, Attendance.status)
            .outerjoin(ShiftTemplate, ShiftTemplate.id == EmployeeShiftSchedule.shift_template_id)
            .outerjoin(
                Attendance,
                and_(
                    Attendance.employee_id == EmployeeShiftSchedule.employee_id,
                    Attendance.work_date == EmployeeShiftSchedule.work_date,
                ),
            )
            .where(
                EmployeeShiftSchedule.employee_id.in_(ids),
                EmployeeShiftSchedule.warehouse_id == warehouse_id,
                EmployeeShiftSchedule.work_date.between(starts, ends),
                EmployeeShiftSchedule.status == "scheduled",
            )
        )
    ).all()
    today = now.astimezone(zone).date()
    intervals: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
    for shift, template, status in records:
        if not _attendance_ok(status, shift.work_date, today):
            continue
        times = _shift_times(shift, template)
        if times is None:
            continue
        start, end, _ = times
        begin = datetime.combine(shift.work_date, start, zone)
        finish = datetime.combine(shift.work_date + timedelta(days=int(end < start)), end, zone)
        if any(
            value.replace(fold=0).utcoffset() != value.replace(fold=1).utcoffset()
            for value in (begin, finish)
        ):
            continue  # Ambiguous DST: fail closed.
        intervals[shift.employee_id].append((begin, finish))
    logs = (
        await session.scalars(
            select(DriverDutyLog).where(
                DriverDutyLog.employee_id.in_(ids),
                DriverDutyLog.duty_end >= now - timedelta(days=56),
            )
        )
    ).all()
    histories: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
    driving: dict[int, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for duty in logs:
        histories[duty.employee_id].append((duty.duty_start, duty.duty_end))
        driving[duty.employee_id][duty.duty_start.astimezone(zone).date()] += duty.driving_min
    out: list[DriverCtx] = []
    for d in drivers:
        dlog = driving[d.employee_id]
        recent = today - timedelta(days=6)
        fortnight = today - timedelta(days=13)
        out.append(
            replace(
                d,
                shifts=tuple(sorted(intervals[d.employee_id])),
                duty_history=tuple(sorted(histories[d.employee_id])),
                driving_min_by_day=dict(dlog),
                driving_min_week=sum(minutes for day, minutes in dlog.items() if day >= recent),
                driving_min_fortnight=sum(minutes for day, minutes in dlog.items() if day >= fortnight),
                # D7's 56-day completeness marker has not been added to the DB.
                # Nonempty history is NOT proof of coverage on rest days.
                history_complete=False,
            )
        )
    return vehicles, tuple(out)


async def load_inputs(
    session: AsyncSession,
    order: CustomerOrder,
    market: Market,
    *,
    now: datetime,
    params: dict[str, object],
) -> PlanningInputs:
    """Compile fresh, conservative DB inputs. Other-market SKU mapping is not silently guessed."""
    cfg = MarketConfig.model_validate(market.config or {})
    zone = ZoneInfo(market.timezone)
    local = now.astimezone(zone)
    days = [local.date() + timedelta(days=i) for i in range(cfg.search_days_max)]
    holidays = (
        await session.scalars(
            select(MarketHoliday.holiday_date).where(
                MarketHoliday.market_id == market.id,
                MarketHoliday.holiday_date.in_(days),
            )
        )
    ).all()
    ecfg = engine_config(cfg, holidays)
    lines = (
        await session.scalars(
            select(OrderLine).where(OrderLine.order_id == order.id).order_by(OrderLine.line_no)
        )
    ).all()
    if not lines:
        raise _problem("Order has no lines to plan.")
    if market.code.strip() != "SE":
        raise _problem("Confirmed source-SKU mapping adapter not available for this market.")
    skus = [line.local_sku for line in lines]
    products = {
        row.local_sku: row
        for row in (
            await session.scalars(select(ProductSE).where(ProductSE.local_sku.in_(skus)))
        ).all()
    }
    global_ids = {line.global_product_id for line in lines if line.global_product_id is not None}
    globals_ = {
        row.id: row
        for row in (await session.scalars(select(ProductGlobal).where(ProductGlobal.id.in_(global_ids)))).all()
    }
    groups = {
        row.id: row for row in (await session.scalars(select(HandlingGroup))).all()
    }
    flags = {row.code: row.multiplier for row in (await session.scalars(select(SpecialFlag))).all()}
    order_lines: list[LineCtx] = []
    for line in lines:
        source = products.get(line.local_sku)
        global_product = globals_.get(line.global_product_id)
        if (
            source is None
            or source.mapping_status != "confirmed"
            or source.global_product_id != line.global_product_id
            or global_product is None
            or line.qty_base is None
            or line.qty_base <= 0
        ):
            raise _problem("Order is not eligible for CFO planning: source mapping is not confirmed.")
        group = groups.get(global_product.handling_group_id)
        if group is None or any(flag not in flags for flag in (global_product.flags or [])):
            raise _problem("Handling group or required special flag is missing.")
        order_lines.append(
            LineCtx(
                product=__import__("app.engine.types", fromlist=["ProductCtx"]).ProductCtx(
                    global_product_id=global_product.id,
                    group=HandlingGroupCtx(
                        group.code,
                        cast(PrepUnitT, group.prep_unit),
                        group.fixed_hours,
                        group.labour_hours_per_unit,
                        frozenset(group.vehicle_requirement),
                    ),
                    base_units_per_prep_unit=global_product.base_units_per_prep_unit,
                    flag_multipliers=tuple(flags[f] for f in (global_product.flags or [])),
                    weight_kg=global_product.weight_kg,
                    volume_m3=global_product.volume_m3,
                ),
                qty_base=line.qty_base,
            )
        )
    search_target = params.get("target_date")
    date_to = order.date_to
    if search_target is not None:
        if not isinstance(search_target, str) or order.date_mode == "exact":
            raise DomainError("VALIDATION_ERROR", "Target date override requires range/latest.")
        try:
            candidate = date.fromisoformat(search_target)
        except ValueError as exc:
            raise DomainError("VALIDATION_ERROR", "Invalid target date.") from exc
        if candidate > order.date_to or (
            order.date_mode == "range" and order.date_from is not None and candidate < order.date_from
        ):
            raise DomainError("VALIDATION_ERROR", "Target date is outside the customer's accepted range.")
        date_to = candidate
    order_ctx = OrderCtx(
        id=order.id,
        version=order.version,
        lat=float(order.delivery_lat),
        lon=float(order.delivery_lon),
        date_mode=cast("DateModeT", order.date_mode),
        date_from=order.date_from,
        date_to=date_to,
        window=(order.window_start, order.window_end)
        if order.window_start is not None and order.window_end is not None
        else None,
        lines=tuple(order_lines),
        now=local,
    )
    exclude_wh = set(params.get("exclude_warehouse_ids", []))
    exclude_vehicles = set(params.get("exclude_vehicle_ids", []))
    locations = (
        await session.scalars(
            select(Location)
            .where(
                Location.market_id == market.id,
                Location.type == "warehouse",
                Location.is_active.is_(True),
            )
            .order_by(Location.id)
        )
    ).all()
    locations = [wh for wh in locations if wh.id not in exclude_wh]
    if not locations:
        raise _problem("No active eligible warehouse.")
    wh_ids = [wh.id for wh in locations]
    product_ids = sorted(global_ids)
    snapshots = (
        await session.scalars(
            select(StockSnapshot).where(
                StockSnapshot.warehouse_id.in_(wh_ids),
                StockSnapshot.global_product_id.in_(product_ids),
            )
        )
    ).all()
    if not snapshots or any(
        row.as_of < now - timedelta(minutes=cfg.stale_stock_min)
        or row.as_of > now + timedelta(minutes=cfg.stale_stock_min)
        for row in snapshots
    ):
        raise DomainError("RESOURCE_CONFLICT", "Market stock snapshot unavailable or stale.")
    stock = await available_stock(session, wh_ids, product_ids, now=now, exclude_order_id=order.id)
    inbound = await confirmed_inbound(session, wh_ids, product_ids)
    routes = await route_info(session, wh_ids, order.delivery_lat, order.delivery_lon)
    warehouses: list[WarehouseCtx] = []
    for wh in locations:
        capacities, windows = await official_warehouse_capacity(
            session, wh.id, days, now=now, zone=zone, exclude_order_id=order.id
        )
        vehicles, drivers = await fleet_context(
            session, wh.id, days, now=now, today=local.date(), exclude_order_id=order.id
        )
        vehicles, drivers = await official_driver_context(
            session, wh.id, vehicles, drivers, days=days, now=now, zone=zone
        )
        warehouses.append(
            WarehouseCtx(
                id=wh.id,
                name=wh.name,
                cutoff=wh.loading_cutoff_time or time(0),
                efficiency=wh.efficiency_factor,
                stock_available=stock[wh.id],
                inbound=inbound.get(wh.id, ()),
                capacity=capacities,
                vehicles=tuple(v for v in vehicles if v.id not in exclude_vehicles),
                drivers=drivers,
                route=routes[wh.id],
                loading_windows=windows,
            )
        )
    return PlanningInputs(
        order=order_ctx,
        warehouses=tuple(warehouses),
        config=ecfg,
        snapshot={
            "order_id": order.id,
            "order_version": order.version,
            "source_version": order.source_version,
            "market": market.code.strip(),
            "as_of": now.isoformat(),
            "warehouse_ids": wh_ids,
            "stock_as_of": min(s.as_of for s in snapshots).isoformat(),
            "driver_history_verified": False,
        },
    )
