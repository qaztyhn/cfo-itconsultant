"""Authorized on-road duty intervals for D3 maintenance, never for attendance tracking.

No coordinates returned. Dispatcher-to-trip read authorization is a separate API handoff.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.hr import (
    DriverStaff,
    Employee,
    EmployeeAssignment,
    EmployeeShiftSchedule,
    ShiftTemplate,
)
from app.domain.models.ops import DeliveryTrip
from app.domain.models.ref import Location, Market


async def active_duty(session: AsyncSession, *, now: datetime) -> dict[int, tuple[datetime, datetime]]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("GPS duty time must be aware")
    result: dict[int, tuple[datetime, datetime]] = {}
    for market in (await session.scalars(select(Market).where(Market.gps_enabled.is_(True)))).all():
        zone = ZoneInfo(market.timezone)
        local_day = now.astimezone(zone).date()
        rows = await session.execute(
            select(DeliveryTrip, EmployeeShiftSchedule, ShiftTemplate)
            .join(Location, Location.id == DeliveryTrip.warehouse_id)
            .join(Employee, Employee.id == DeliveryTrip.driver_employee_id)
            .join(DriverStaff, DriverStaff.employee_id == Employee.id)
            .join(EmployeeAssignment, EmployeeAssignment.employee_id == Employee.id)
            .join(EmployeeShiftSchedule, EmployeeShiftSchedule.employee_id == Employee.id)
            .outerjoin(
                ShiftTemplate,
                ShiftTemplate.id == EmployeeShiftSchedule.shift_template_id,
            )
            .where(
                Location.market_id == market.id,
                Employee.market_id == market.id,
                Employee.status == "active",
                Employee.hire_date <= local_day,
                or_(Employee.end_date.is_(None), Employee.end_date >= local_day),
                EmployeeAssignment.location_id == DeliveryTrip.warehouse_id,
                EmployeeAssignment.start_date <= local_day,
                or_(
                    EmployeeAssignment.end_date.is_(None),
                    EmployeeAssignment.end_date >= local_day,
                ),
                EmployeeShiftSchedule.warehouse_id == DeliveryTrip.warehouse_id,
                EmployeeShiftSchedule.status == "scheduled",
                EmployeeShiftSchedule.work_date.in_((local_day, local_day - timedelta(days=1))),
                DeliveryTrip.status == "on_road",
                DeliveryTrip.ended_at.is_(None),
                DeliveryTrip.depart_actual_at <= now,
            )
        )
        for trip, shift, template in rows:
            if trip.depart_actual_at is None:
                continue
            start_time = shift.start_time or (template.start_time if template else None)
            end_time = shift.end_time or (template.end_time if template else None)
            if start_time is None or end_time is None or start_time == end_time:
                continue  # Missing/ambiguous duty never authorizes GPS.
            if template is not None and template.warehouse_id != shift.warehouse_id:
                continue
            begins = datetime.combine(shift.work_date, start_time, zone)
            ends = datetime.combine(
                shift.work_date + timedelta(days=int(end_time < start_time)),
                end_time,
                zone,
            )
            if any(
                boundary.replace(fold=0).utcoffset() != boundary.replace(fold=1).utcoffset()
                for boundary in (begins, ends)
            ):
                continue  # Ambiguous/nonexistent DST boundary needs an explicit corrected schedule.
            begins = max(begins, trip.depart_actual_at)
            if begins <= now < ends:
                result[trip.id] = (begins.astimezone(UTC), ends.astimezone(UTC))
    return result


async def trip_collection_windows(
    session: AsyncSession, trip_ids: list[int]
) -> dict[int, tuple[datetime, datetime]]:
    """Valid collection window of each trip, also AFTER it ended (7-day retention validity, DEC-GPS-RET).

    window = [max(official shift start, actual departure), min(official shift end, trip end)). The shift is
    the one of the trip's driver/warehouse that contains the actual departure. A trip with no verified
    shift/departure has NO window, so none of its points is considered valid. No coordinates are read.
    """
    result: dict[int, tuple[datetime, datetime]] = {}
    for trip in (await session.scalars(select(DeliveryTrip).where(DeliveryTrip.id.in_(trip_ids)))).all():
        if trip.depart_actual_at is None:
            continue
        market = await session.scalar(
            select(Market)
            .join(Location, Location.market_id == Market.id)
            .where(Location.id == trip.warehouse_id)
        )
        if market is None:
            continue
        zone = ZoneInfo(market.timezone)
        depart_day = trip.depart_actual_at.astimezone(zone).date()
        rows = await session.execute(
            select(EmployeeShiftSchedule, ShiftTemplate)
            .outerjoin(ShiftTemplate, ShiftTemplate.id == EmployeeShiftSchedule.shift_template_id)
            .where(
                EmployeeShiftSchedule.employee_id == trip.driver_employee_id,
                EmployeeShiftSchedule.warehouse_id == trip.warehouse_id,
                EmployeeShiftSchedule.status == "scheduled",
                EmployeeShiftSchedule.work_date.in_((depart_day, depart_day - timedelta(days=1))),
            )
        )
        for shift, template in rows:
            start_time = shift.start_time or (template.start_time if template else None)
            end_time = shift.end_time or (template.end_time if template else None)
            if start_time is None or end_time is None or start_time == end_time:
                continue
            if template is not None and template.warehouse_id != shift.warehouse_id:
                continue
            begins = datetime.combine(shift.work_date, start_time, zone)
            ends = datetime.combine(
                shift.work_date + timedelta(days=int(end_time < start_time)), end_time, zone
            )
            if any(b.replace(fold=0).utcoffset() != b.replace(fold=1).utcoffset() for b in (begins, ends)):
                continue  # ambiguous/nonexistent DST boundary: never authorises collection
            if not begins <= trip.depart_actual_at < ends:
                continue
            last = min(ends, trip.ended_at) if trip.ended_at is not None else ends
            result[trip.id] = (max(begins, trip.depart_actual_at).astimezone(UTC), last.astimezone(UTC))
            break
    return result
