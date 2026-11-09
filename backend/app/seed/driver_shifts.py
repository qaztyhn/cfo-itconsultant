"""Named, manager-attributed *synthetic* driver shifts for the demo.

Schedules are official within this isolated demo only: no auto-attendance,
driving-time history, D7 legal attestation, licence override or GPS permission.
Existing scheduled or cancelled rows are never changed. Manager authority and
employee assignment are checked before any write.
"""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.domain.models.hr import (
    DriverStaff,
    Employee,
    EmployeeAssignment,
    EmployeeShiftSchedule,
    LocationManager,
    ShiftTemplate,
)
from app.domain.models.ref import AppUser, Location, Market

REASON = "Synthetic demo driver roster explicitly assigned by named warehouse manager."


async def seed_driver_shifts(session: AsyncSession, *, shifts: list[dict[str, object]], now: datetime) -> int:
    """Caller owns transaction; missing permission/fixture causes rollback."""
    if now.tzinfo is None:
        raise ValueError("Driver roster timestamp must include timezone")
    await session.execute(text("SELECT pg_advisory_xact_lock(20261104)"))
    market = (await session.scalars(select(Market).where(Market.code == "SE"))).one()
    inserted = 0
    for fixture in shifts:
        employee_no = str(fixture["employee_no"])
        warehouse_code = str(fixture["warehouse_code"])
        day = __import__("datetime").date.fromisoformat(str(fixture["work_date"]))
        begins = time.fromisoformat(str(fixture["start"]))
        ends = time.fromisoformat(str(fixture["end"]))
        pause = time.fromisoformat(str(fixture["break_start"]))
        resume = time.fromisoformat(str(fixture["break_end"]))
        if not (begins < pause < resume < ends):
            raise ValueError("Synthetic driver shift requires an in-shift break")
        warehouse = (
            await session.scalars(
                select(Location).where(
                    Location.market_id == market.id,
                    Location.code == warehouse_code,
                    Location.type == "warehouse",
                )
            )
        ).one()
        driver = (
            await session.scalars(
                select(Employee).where(
                    Employee.market_id == market.id,
                    Employee.employee_no == employee_no,
                )
            )
        ).one()
        if await session.get(DriverStaff, driver.id) is None:
            raise ValueError("Driver roster member is not a registered driver")
        manager = (
            await session.scalars(
                select(Employee).where(
                    Employee.market_id == market.id,
                    Employee.employee_no == str(fixture["authority"]),
                    Employee.position_code == "WAREHOUSE_MANAGER",
                )
            )
        ).one()
        user = (await session.scalars(select(AppUser).where(AppUser.employee_id == manager.id))).one()
        if not user.is_active or "warehouse" not in user.roles:
            raise ValueError("Demo manager cannot assign driver shifts")
        valid_manager = await session.scalar(
            select(LocationManager.id).where(
                LocationManager.employee_id == manager.id,
                LocationManager.location_id == warehouse.id,
                LocationManager.level == "primary",
                LocationManager.can_approve.is_(True),
                LocationManager.valid_from <= day,
                or_(LocationManager.valid_to.is_(None), LocationManager.valid_to >= day),
            )
        )
        valid_driver = await session.scalar(
            select(EmployeeAssignment.id).where(
                EmployeeAssignment.employee_id == driver.id,
                EmployeeAssignment.location_id == warehouse.id,
                EmployeeAssignment.start_date <= day,
                or_(EmployeeAssignment.end_date.is_(None), EmployeeAssignment.end_date >= day),
            )
        )
        if valid_manager is None or valid_driver is None:
            raise ValueError("Driver/manager is not assigned to this warehouse on shift date")
        existing = await session.scalar(
            select(EmployeeShiftSchedule.id).where(
                EmployeeShiftSchedule.employee_id == driver.id,
                EmployeeShiftSchedule.work_date == day,
            )
        )
        if existing is not None:
            continue  # Including cancelled shifts; no automatic resurrection.
        template = (
            await session.scalars(
                select(ShiftTemplate).where(
                    ShiftTemplate.warehouse_id == warehouse.id,
                    ShiftTemplate.weekday == day.isoweekday(),
                    ShiftTemplate.start_time == begins,
                    ShiftTemplate.end_time == ends,
                )
            )
        ).one()
        schedule = EmployeeShiftSchedule(
            employee_id=driver.id,
            warehouse_id=warehouse.id,
            work_date=day,
            shift_template_id=template.id,
            break_start=pause,
            break_end=resume,
            assigned_by=manager.id,
            assigned_at=now,
            reason_text=REASON,
        )
        session.add(schedule)
        await session.flush()
        await record_decision(
            session,
            Action.SHIFT_CHANGED,
            "employee_shift_schedule",
            str(schedule.id),
            reason_text=REASON,
            actor_user_id=user.id,
            actor_employee_id=manager.id,
            actor_role="warehouse",
            before=None,
            after={
                "employee_id": driver.id,
                "warehouse_id": warehouse.id,
                "work_date": day.isoformat(),
                "shift_template_id": template.id,
                "break_start": pause.isoformat(),
                "break_end": resume.isoformat(),
                "status": "scheduled",
            },
        )
        inserted += 1
    return inserted
