"""Pure five-gate verification for a dispatcher-selected manual plan.

The caller must construct OrderCtx, WarehouseCtx and PlanCandidate from current,
trusted records inside the approval transaction. This module never approves or
persists a plan and never trusts the candidate's cached ``checks`` field.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from app.engine.atp import check_atp, stock_check
from app.engine.capacity import is_working_day
from app.engine.delivery import (
    can_carry,
    candidate_days,
    driver_problem,
    handling_minutes,
    receiving_window,
    vehicle_free,
)
from app.engine.schedule import schedule_preparation
from app.engine.types import CheckNameT, CheckResult, EngineConfig, OrderCtx, PlanCandidate, WarehouseCtx
from app.engine.workload import compute_workload, warehouse_labour_hours


def _check(name: CheckNameT, passed: bool, code: str, message: str) -> CheckResult:
    return CheckResult(name, passed, code, {"message": message})


def _inside_loading_shift(wh: WarehouseCtx, start: datetime, end: datetime) -> bool:
    return any(shift_start <= start and end <= shift_end for shift_start, shift_end in wh.loading_windows)


def verify_manual(
    order: OrderCtx, wh: WarehouseCtx, candidate: PlanCandidate, cfg: EngineConfig
) -> tuple[CheckResult, ...]:
    """Recheck the five existing engine gates, stopping at the first failure.

    The service must still enforce Dispatcher RBAC, order/version/routing state,
    WMS ACK, transaction locks, idempotency and audit. A five-pass result alone
    is never authorization to commit a reservation or change order status.
    """
    atp = check_atp(order, wh, cfg)
    stock = stock_check(atp)
    if not stock.passed or atp.stock_ready_date is None:
        return (stock,)
    checks = (stock,)

    workload = compute_workload(order.lines, cfg)
    prep = schedule_preparation(
        warehouse_labour_hours(workload, wh.efficiency), atp.stock_ready_date, order.now, wh, cfg
    )
    if not prep.check.passed or prep.goods_ready_at is None:
        return (*checks, prep.check)
    if (
        candidate.goods_ready_at < prep.goods_ready_at
        or candidate.goods_ready_at.date() < atp.stock_ready_date
    ):
        return (*checks, _check("preparation", False, "PREP_NO_CAPACITY", "Goods readiness is unverified."))
    if (
        candidate.prep_hours != warehouse_labour_hours(workload, wh.efficiency)
        or candidate.prep_by_day != prep.prep_by_day
    ):
        return (
            *checks,
            _check("preparation", False, "PREP_NO_CAPACITY", "Preparation allocation is unverified."),
        )
    checks += (prep.check,)

    if candidate.warehouse_id != wh.id or not candidate.vehicles or not order.lines:
        return (*checks, _check("truck", False, "NO_TRUCK_FIT", "Warehouse or load is incomplete."))
    vehicles = {vehicle.id: vehicle for vehicle in wh.vehicles}
    assigned_ids: set[int] = set()
    allocated: dict[int, Decimal] = defaultdict(Decimal)
    loading_intervals: list[tuple[datetime, datetime]] = []
    for assignment in candidate.vehicles:
        vehicle = vehicles.get(assignment.vehicle_id)
        if vehicle is None or vehicle.id in assigned_ids or not assignment.load_lines:
            return (*checks, _check("truck", False, "NO_TRUCK_FIT", "Vehicle assignment is invalid."))
        assigned_ids.add(vehicle.id)
        seen_lines: set[int] = set()
        load_kg = load_m3 = Decimal(0)
        for line_no, qty in assignment.load_lines:
            if line_no in seen_lines or line_no < 1 or line_no > len(order.lines) or qty <= 0:
                return (*checks, _check("truck", False, "NO_TRUCK_FIT", "Line allocation is invalid."))
            seen_lines.add(line_no)
            line = order.lines[line_no - 1]
            if not can_carry(vehicle, line):
                return (
                    *checks,
                    _check("truck", False, "NO_TRUCK_FIT", "Vehicle cannot carry an assigned line."),
                )
            allocated[line_no] += qty
            load_kg += qty * line.product.weight_kg
            load_m3 += qty * line.product.volume_m3
        if (
            assignment.vehicle_code != vehicle.code
            or assignment.capacity_kg != vehicle.capacity_kg
            or assignment.capacity_m3 != vehicle.capacity_m3
            or assignment.load_kg != load_kg
            or assignment.load_m3 != load_m3
        ):
            return (
                *checks,
                _check("truck", False, "NO_TRUCK_FIT", "Vehicle or load snapshot disagrees with source."),
            )
        if load_kg > vehicle.capacity_kg or load_m3 > vehicle.capacity_m3:
            return (*checks, _check("truck", False, "NO_TRUCK_FIT", "Vehicle capacity is exceeded."))
        if (
            assignment.loading_start_at < candidate.goods_ready_at
            or assignment.depart_at <= assignment.loading_start_at
        ):
            return (*checks, _check("truck", False, "TRUCK_BUSY", "Loading or departure time is invalid."))
        loading_end = assignment.loading_start_at + timedelta(
            minutes=handling_minutes(load_kg, cfg.loading_base_min, cfg.loading_min_per_ton)
        )
        if loading_end > assignment.depart_at or not _inside_loading_shift(
            wh, assignment.loading_start_at, loading_end
        ):
            return (*checks, _check("truck", False, "TRUCK_BUSY", "Loading lacks an official staffed shift."))
        if assignment.loading_start_at.time() > wh.cutoff or not vehicle_free(
            vehicle, assignment.loading_start_at, assignment.trip_end_at
        ):
            return (*checks, _check("truck", False, "TRUCK_BUSY", "Vehicle is unavailable for the trip."))
        loading_intervals.append((assignment.loading_start_at, loading_end))
    if any(allocated.get(i, Decimal(0)) != line.qty_base for i, line in enumerate(order.lines, start=1)):
        return (*checks, _check("truck", False, "NO_TRUCK_FIT", "Every line must be allocated exactly once."))
    ordered = sorted(loading_intervals)
    if any(earlier[1] > later[0] for earlier, later in zip(ordered, ordered[1:], strict=False)):
        return (*checks, _check("truck", False, "TRUCK_BUSY", "Vehicle loading windows overlap."))
    if (
        candidate.loading_start_at != min(a.loading_start_at for a in candidate.vehicles)
        or candidate.depart_at != min(a.depart_at for a in candidate.vehicles)
        or candidate.eta_at != max(a.eta_at for a in candidate.vehicles)
        or candidate.trip_end_at != max(a.trip_end_at for a in candidate.vehicles)
    ):
        return (*checks, _check("truck", False, "NO_TRUCK_FIT", "Trip summary disagrees with assignments."))
    checks += (_check("truck", True, "TRUCK_OK", "Complete load fits available vehicles."),)

    route = wh.route
    if route is None:
        return (*checks, _check("site_date", False, "ROUTE_DATA_UNAVAILABLE", "Route data is unavailable."))
    if (
        candidate.distance_km != route.distance_km
        or candidate.drive_min != route.drive_min
        or candidate.route_provenance != route.provenance
    ):
        return (
            *checks,
            _check("site_date", False, "ROUTE_DATA_UNAVAILABLE", "Route snapshot is unverified."),
        )
    open_at, close_at = receiving_window(order, cfg)
    arrival_times = [assignment.eta_at for assignment in candidate.vehicles]
    if not is_working_day(candidate.target_date, cfg):
        return (*checks, _check("site_date", False, "NON_WORKING_DAY", "Delivery date is not a working day."))
    if candidate.target_date not in candidate_days(order, candidate.target_date, cfg):
        return (
            *checks,
            _check("site_date", False, "DATE_AFTER_DEADLINE", "Delivery date is outside the agreed range."),
        )
    if any(
        eta.date() != candidate.target_date or not open_at <= eta.time() <= close_at for eta in arrival_times
    ):
        return (
            *checks,
            _check("site_date", False, "OUTSIDE_RECEIVING_HOURS", "Arrival is outside receiving hours."),
        )
    if (
        any(
            assignment.eta_at < assignment.depart_at + timedelta(minutes=route.drive_min)
            for assignment in candidate.vehicles
        )
        or (max(arrival_times) - min(arrival_times)).total_seconds() > cfg.max_arrival_spread_min * 60
    ):
        return (
            *checks,
            _check("site_date", False, "DATE_AFTER_DEADLINE", "Route or arrival spread is invalid."),
        )
    checks += (_check("site_date", True, "DATE_OK", "Every vehicle arrives within the agreed window."),)

    drivers = {driver.employee_id: driver for driver in wh.drivers}
    assigned_drivers: set[int] = set()
    for assignment in candidate.vehicles:
        vehicle = vehicles[assignment.vehicle_id]
        driver = drivers.get(assignment.driver_employee_id)
        if driver is None or driver.employee_id in assigned_drivers:
            return (*checks, _check("safety", False, "NO_DRIVER", "Distinct assigned drivers are required."))
        assigned_drivers.add(driver.employee_id)
        if vehicle.regulation_561 is None:
            return (
                *checks,
                _check("safety", False, "VEHICLE_SCOPE_UNKNOWN", "Driving-rule scope is unknown."),
            )
        if vehicle.regulation_561 and route.drive_min > cfg.driving_break_after_min:
            return (
                *checks,
                _check("safety", False, "DRIVING_BREAK_REQUIRED", "Required driving break is unscheduled."),
            )
        if candidate.target_date not in driver.available_days:
            return (
                *checks,
                _check("safety", False, "OUTSIDE_DRIVER_SHIFT", "Driver availability is unverified."),
            )
        problem = driver_problem(
            driver, vehicle, assignment.loading_start_at, assignment.trip_end_at, cfg, 2 * route.drive_min
        )
        if problem is not None:
            code = {
                "history": "DRIVER_HISTORY_MISSING",
                "rest": "DRIVER_REST_INSUFFICIENT",
                "hours": "DRIVER_HOURS_EXCEEDED",
                "driving": "DRIVING_TIME_EXCEEDED",
                "expired": "LICENCE_EXPIRED",
                "outside_shift": "OUTSIDE_DRIVER_SHIFT",
            }.get(problem, "NO_DRIVER")
            return (*checks, _check("safety", False, code, "Driver is ineligible for the assigned trip."))
        load_kg = sum(
            (qty * order.lines[line_no - 1].product.weight_kg for line_no, qty in assignment.load_lines),
            Decimal(0),
        )
        unload = handling_minutes(load_kg, cfg.unloading_base_min, cfg.unloading_min_per_ton)
        if assignment.trip_end_at < assignment.eta_at + timedelta(minutes=unload + route.drive_min):
            return (
                *checks,
                _check("safety", False, "DRIVER_HOURS_EXCEEDED", "Trip end omits unloading or return."),
            )
    return (*checks, _check("safety", True, "SAFETY_OK", "Assigned drivers passed duty and licence checks."))
