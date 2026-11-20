"""Read current DEC-R3-07 evidence and the market-local committed driving budget."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.hr import DriverAvailability, DriverVehicleEligibility, Employee, EmployeeAssignment
from app.domain.models.ops import DeliveryTrip
from app.domain.models.plan import FulfilmentPlan, PlanVehicle
from app.domain.models.ref import Market, Vehicle
from app.engine.delivery import verified_driver_problem
from app.engine.types import DriverQualification, DriverVerification, DriverWindow


def allowed_sources() -> tuple[str, ...]:
    return (
        ("fleet_api", "fleet_csv")
        if get_settings().app_env == "production"
        else ("fleet_api", "fleet_csv", "synthetic_demo")
    )


async def load_evidence(
    session: AsyncSession,
    market: Market,
    warehouse_id: int,
    drivers: Iterable[int],
    first: date,
    last: date,
    *,
    now: datetime,
    exclude_order_id: int | None = None,
    exclude_trip_id: int | None = None,
) -> dict[int, DriverVerification]:
    ids = tuple(drivers)
    if not ids:
        return {}
    zone = ZoneInfo(market.timezone)
    sources = allowed_sources()
    windows: dict[int, dict[date, DriverWindow]] = defaultdict(dict)
    availability = await session.scalars(
        select(DriverAvailability)
        .join(Employee, Employee.id == DriverAvailability.driver_employee_id)
        .join(EmployeeAssignment, EmployeeAssignment.employee_id == Employee.id)
        .where(
            DriverAvailability.driver_employee_id.in_(ids),
            DriverAvailability.work_date.between(first, last),
            DriverAvailability.superseded_at.is_(None),
            DriverAvailability.source.in_(sources),
            DriverAvailability.verified_at <= now,
            func.length(func.btrim(DriverAvailability.verified_by)) > 0,
            Employee.status == "active",
            Employee.market_id == market.id,
            Employee.hire_date <= DriverAvailability.work_date,
            or_(Employee.end_date.is_(None), Employee.end_date >= DriverAvailability.work_date),
            EmployeeAssignment.location_id == warehouse_id,
            EmployeeAssignment.start_date <= DriverAvailability.work_date,
            or_(
                EmployeeAssignment.end_date.is_(None),
                EmployeeAssignment.end_date >= DriverAvailability.work_date,
            ),
        )
    )
    for row in availability:
        if row.available_from.astimezone(zone).date() == row.work_date:
            windows[row.driver_employee_id][row.work_date] = DriverWindow(
                row.available_from, row.available_to, row.max_driving_min
            )

    qualifications: dict[int, list[DriverQualification]] = defaultdict(list)
    for qualification in await session.scalars(
        select(DriverVehicleEligibility).where(
            DriverVehicleEligibility.driver_employee_id.in_(ids),
            DriverVehicleEligibility.revoked_at.is_(None),
            DriverVehicleEligibility.source.in_(sources),
            DriverVehicleEligibility.verified_at <= now,
            func.length(func.btrim(DriverVehicleEligibility.verified_by)) > 0,
        )
    ):
        qualifications[qualification.driver_employee_id].append(
            DriverQualification(
                qualification.vehicle_id, qualification.licence_class, qualification.verified_until
            )
        )

    # Approved trips and trips that have departed continue to use their committed
    # out-and-back minutes. Held alternatives have no execution trip.
    depart = func.coalesce(DeliveryTrip.depart_actual_at, DeliveryTrip.depart_planned_at)
    query = (
        select(DeliveryTrip.driver_employee_id, depart, FulfilmentPlan.drive_min)
        .join(PlanVehicle, PlanVehicle.id == DeliveryTrip.plan_vehicle_id)
        .join(FulfilmentPlan, FulfilmentPlan.id == PlanVehicle.plan_id)
        .where(
            DeliveryTrip.driver_employee_id.in_(ids),
            depart >= datetime.combine(first, time.min, zone),
            depart < datetime.combine(last + timedelta(days=1), time.min, zone),
            or_(
                DeliveryTrip.depart_actual_at.is_not(None),
                and_(
                    DeliveryTrip.status.in_(("planned", "loading")),
                    FulfilmentPlan.status.in_(("approved", "manual")),
                ),
            ),
        )
    )
    if exclude_order_id is not None:
        query = query.where(
            or_(FulfilmentPlan.order_id != exclude_order_id, DeliveryTrip.depart_actual_at.is_not(None))
        )
    if exclude_trip_id is not None:
        query = query.where(DeliveryTrip.id != exclude_trip_id)
    budgets: dict[int, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for driver_id, when, minutes in await session.execute(query):
        budgets[driver_id][when.astimezone(zone).date()] += 2 * minutes
    return {
        driver_id: DriverVerification(
            windows[driver_id], tuple(qualifications[driver_id]), dict(budgets[driver_id])
        )
        for driver_id in ids
    }


async def stored_driver_problem(
    session: AsyncSession,
    market: Market,
    plan: FulfilmentPlan,
    assignment: PlanVehicle,
    *,
    now: datetime,
    depart_at: datetime | None = None,
    exclude_trip_id: int | None = None,
    event_at: datetime | None = None,
) -> str | None:
    vehicle = await session.get(Vehicle, assignment.vehicle_id)
    if vehicle is None:
        return "not_verified"
    zone = ZoneInfo(market.timezone)
    planned = assignment.depart_at.astimezone(zone)
    depart = (depart_at or planned).astimezone(zone)
    if depart.date() != planned.date():
        return "outside_shift"
    evidence = await load_evidence(
        session,
        market,
        plan.warehouse_id,
        (assignment.driver_employee_id,),
        depart.date(),
        depart.date(),
        now=now,
        exclude_trip_id=exclude_trip_id,
        exclude_order_id=plan.order_id if exclude_trip_id is None else None,
    )
    verification = evidence[assignment.driver_employee_id]
    window = verification.windows.get(depart.date())
    if event_at is not None and window is not None and not window.start <= event_at < window.end:
        return "outside_shift"
    # A later actual departure must still leave time for the planned return leg.
    delay = max(timedelta(), depart.astimezone(UTC) - planned.astimezone(UTC))
    return verified_driver_problem(
        verification,
        vehicle.id,
        vehicle.required_licence,
        min(depart, planned),
        assignment.trip_end_at + delay,
        2 * plan.drive_min,
    )
