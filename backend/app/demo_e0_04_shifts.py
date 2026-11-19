"""Add named manager-attributed Dec 2 shifts to the disposable E0-04 demo."""

import asyncio
import os
from datetime import date

from sqlalchemy import select

from app.core import clock
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.deps import CurrentUser
from app.domain.models.hr import Attendance, Employee, EmployeeShiftSchedule
from app.domain.models.ref import AppUser, Location
from app.seed.driver_shifts import seed_driver_shifts
from app.seed.roster import seed_roster
from app.services.hr_service import set_attendance

DEMO_NOW = "2026-12-01T10:05:00+01:00"


async def run() -> tuple[int, int]:
    settings = get_settings()
    if settings.app_env != "test" or settings.app_now != DEMO_NOW or os.environ.get("DEMO_DISPOSABLE") != "1":
        raise ValueError("Disposable E0-04 clock required")
    clock.init_from_settings(settings.app_now)
    prep_day = date(2026, 12, 1)
    day = date(2026, 12, 2)
    fixture = {
        "employee_no": "DEMO-DRIVER-2",
        "warehouse_code": "STO",
        "work_date": day.isoformat(),
        "start": "06:00",
        "end": "14:00",
        "break_start": "10:00",
        "break_end": "11:00",
        "authority": "DEMO-STO-W00",
    }
    try:
        async with get_sessionmaker()() as session, session.begin():
            warehouse = await seed_roster(session, start=prep_day, end=day, now=clock.now())
            driver = await seed_driver_shifts(session, shifts=[fixture], now=clock.now())
            schedules = (
                await session.scalars(
                    select(EmployeeShiftSchedule).where(
                        EmployeeShiftSchedule.work_date.in_((prep_day, day)),
                        EmployeeShiftSchedule.status == "scheduled",
                    )
                )
            ).all()
            for shift in schedules:
                existing = await session.scalar(
                    select(Attendance.id).where(
                        Attendance.employee_id == shift.employee_id,
                        Attendance.work_date == shift.work_date,
                    )
                )
                if existing is None:
                    session.add(
                        Attendance(
                            employee_id=shift.employee_id,
                            work_date=shift.work_date,
                            shift_template_id=shift.shift_template_id,
                            status="planned",
                        )
                    )
            await session.flush()
            manager = await session.scalar(select(Employee).where(Employee.employee_no == "DEMO-STO-W00"))
            warehouse_location = await session.scalar(
                select(Location).where(Location.code == "STO", Location.type == "warehouse")
            )
            if manager is None or warehouse_location is None:
                raise ValueError("Named warehouse manager or GBG missing")
            user = await session.scalar(select(AppUser).where(AppUser.employee_id == manager.id))
            if user is None or not user.is_active or "warehouse" not in user.roles:
                raise ValueError("Named warehouse manager account inactive")
            actor = CurrentUser(
                id=user.id,
                employee_id=manager.id,
                roles=tuple(user.roles),
                market="SE",
                location_ids=(warehouse_location.id,),
            )
            await set_attendance(session, actor, warehouse_location.id, prep_day, all_present=True)
        return warehouse, driver
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    try:
        wh_count, driver_count = asyncio.run(run())
    except Exception:
        print("BLOCKED: E0-04 named shifts unavailable; review manager authority and date.")
        raise SystemExit(2) from None
    print(f"PASS: Dec 1-2 named warehouse shifts added={wh_count}; Dec 2 driver shifts added={driver_count}.")
