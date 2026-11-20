"""Verified R3 GPS windows. Dispatcher authorization remains trip-scoped at the API."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.hr import DriverAvailability, DriverStaff, Employee, EmployeeAssignment
from app.domain.models.ops import DeliveryTrip, VehiclePosition
from app.domain.models.ref import Location, Market


def _verified_availability() -> ColumnElement[bool]:
    return and_(
        DriverAvailability.driver_employee_id == DeliveryTrip.driver_employee_id,
        DriverAvailability.superseded_at.is_(None),
        DriverAvailability.max_driving_min > 0,
    )


async def active_duty(
    session: AsyncSession, *, now: datetime, trip_id: int | None = None
) -> dict[int, tuple[datetime, datetime]]:
    """Current verified availability intersected with an active trip."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("GPS duty time must be aware")
    query = (
        select(DeliveryTrip, DriverAvailability, Market.timezone, Employee, EmployeeAssignment)
        .join(Location, Location.id == DeliveryTrip.warehouse_id)
        .join(Market, Market.id == Location.market_id)
        .join(DriverAvailability, _verified_availability())
        .join(Employee, Employee.id == DeliveryTrip.driver_employee_id)
        .join(DriverStaff, DriverStaff.employee_id == Employee.id)
        .join(
            EmployeeAssignment,
            and_(
                EmployeeAssignment.employee_id == Employee.id,
                EmployeeAssignment.location_id == DeliveryTrip.warehouse_id,
            ),
        )
        .where(
            Market.gps_enabled.is_(True),
            Employee.market_id == Market.id,
            Employee.status == "active",
            DriverAvailability.available_from <= now,
            DriverAvailability.available_to > now,
            DeliveryTrip.status == "on_road",
            DeliveryTrip.ended_at.is_(None),
            DeliveryTrip.depart_actual_at <= now,
        )
        .order_by(DriverAvailability.available_from, DriverAvailability.id)
    )
    if trip_id is not None:
        query = query.where(DeliveryTrip.id == trip_id)
    result: dict[int, tuple[datetime, datetime]] = {}
    for trip, availability, zone, employee, assignment in await session.execute(query):
        local_day = now.astimezone(ZoneInfo(zone)).date()
        if (
            trip.depart_actual_at is None
            or local_day < max(employee.hire_date, assignment.start_date)
            or (employee.end_date is not None and local_day > employee.end_date)
            or (assignment.end_date is not None and local_day > assignment.end_date)
        ):
            continue
        # Overlapping active intervals all contain now. The earliest start covers
        # the widest range of recorded points up to now.
        result.setdefault(
            trip.id, (max(availability.available_from, trip.depart_actual_at), availability.available_to)
        )
    return result


def valid_collection_point(when: datetime) -> ColumnElement[bool]:
    """Retention predicate for one point, including points collected before a trip ended."""
    return (
        select(DeliveryTrip.id)
        .join(Location, Location.id == DeliveryTrip.warehouse_id)
        .join(Market, Market.id == Location.market_id)
        .join(DriverAvailability, _verified_availability())
        .where(
            DeliveryTrip.id == VehiclePosition.trip_id,
            Market.gps_enabled.is_(True),
            VehiclePosition.recorded_at >= DeliveryTrip.depart_actual_at,
            VehiclePosition.recorded_at >= DriverAvailability.available_from,
            VehiclePosition.recorded_at < DriverAvailability.available_to,
            VehiclePosition.recorded_at <= when,
            (DeliveryTrip.ended_at.is_(None) | (VehiclePosition.recorded_at < DeliveryTrip.ended_at)),
        )
        .correlate(VehiclePosition)
        .exists()
    )
