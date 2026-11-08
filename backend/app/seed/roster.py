"""Explicit synthetic warehouse roster (M3, US-WH-06 fixture subset, ASM-009).

Offline demo seed only: named assignments attributed to the seeded demo manager.
Never a production scheduling job; never allocate from expected_staff, overwrite
existing schedules, resurrect cancellations, or create attendance/driver history.
"""

import argparse
import asyncio
from datetime import date, datetime, time, timedelta

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import MarketConfig, get_settings
from app.core.db import get_engine, get_sessionmaker
from app.domain.models.hr import (
    Employee,
    EmployeeAssignment,
    EmployeeShiftSchedule,
    LocationManager,
    ShiftTemplate,
    WarehouseStaff,
)
from app.domain.models.ref import AppUser, Location, Market, MarketHoliday
from app.seed.infrastructure import WAREHOUSES

# Fixed people-to-shift fixture, independent of the template's headcount target.
EARLY = (2, 4, 5, 6, 7, 8, 9)
LATE = (3, 10, 11, 12, 13, 14)
SHIFTS = ((EARLY, time(6), time(14), time(10), time(11)), (LATE, time(14), time(22), time(18), time(19)))
REASON = "Synthetic demo roster: explicit named assignments by the demo warehouse manager."


async def _assigned(session: AsyncSession, person: Employee, warehouse_id: int, day: date) -> bool:
    if person.status != "active" or person.hire_date > day or (person.end_date and person.end_date < day):
        return False
    return (
        await session.scalar(
            select(EmployeeAssignment.id).where(
                EmployeeAssignment.employee_id == person.id,
                EmployeeAssignment.location_id == warehouse_id,
                EmployeeAssignment.start_date <= day,
                or_(EmployeeAssignment.end_date.is_(None), EmployeeAssignment.end_date >= day),
            )
        )
    ) is not None


async def seed_roster(session: AsyncSession, *, start: date, end: date, now: datetime) -> int:
    """Caller owns transaction. Require seed-reference first; retain every existing day/person row."""
    if now.tzinfo is None or not 0 <= (end - start).days < 31:
        raise ValueError("Supply an aware timestamp and a date range of 1–31 days")
    await session.execute(text("SELECT pg_advisory_xact_lock(20261104)"))
    market = (await session.scalars(select(Market).where(Market.code == "SE"))).one()
    config = MarketConfig.model_validate(market.config)
    holidays = set(
        (
            await session.scalars(
                select(MarketHoliday.holiday_date).where(
                    MarketHoliday.market_id == market.id, MarketHoliday.holiday_date.between(start, end)
                )
            )
        ).all()
    )
    inserted = 0
    for code, *_ in WAREHOUSES:
        warehouse = (
            await session.scalars(
                select(Location).where(
                    Location.market_id == market.id,
                    Location.code == code,
                    Location.type == "warehouse",
                    Location.is_active.is_(True),
                )
            )
        ).one()
        people = {
            p.employee_no: p
            for p in (
                await session.scalars(
                    select(Employee).where(
                        Employee.market_id == market.id, Employee.employee_no.like(f"DEMO-{code}-W%")
                    )
                )
            ).all()
        }
        manager = people.get(f"DEMO-{code}-W00")
        if manager is None or manager.position_code != "WAREHOUSE_MANAGER":
            raise ValueError("Demo warehouse manager unavailable; run seed-reference first")
        user = (await session.scalars(select(AppUser).where(AppUser.employee_id == manager.id))).one()
        if not user.is_active or "warehouse" not in user.roles:
            raise ValueError("Demo warehouse manager account cannot assign a roster")
        day = start
        while day <= end:
            if day.isoweekday() in config.working_days and day not in holidays:
                authority = await session.scalar(
                    select(LocationManager.id).where(
                        LocationManager.location_id == warehouse.id,
                        LocationManager.employee_id == manager.id,
                        LocationManager.level == "primary",
                        LocationManager.can_approve.is_(True),
                        LocationManager.valid_from <= day,
                        or_(LocationManager.valid_to.is_(None), LocationManager.valid_to >= day),
                    )
                )
                if authority is None or not await _assigned(session, manager, warehouse.id, day):
                    raise ValueError("Demo manager is not effective/authorized at the warehouse")
                for members, begins, finishes, pause, resumes in SHIFTS:
                    template = (
                        await session.scalars(
                            select(ShiftTemplate).where(
                                ShiftTemplate.warehouse_id == warehouse.id,
                                ShiftTemplate.weekday == day.isoweekday(),
                                ShiftTemplate.start_time == begins,
                                ShiftTemplate.end_time == finishes,
                            )
                        )
                    ).one()
                    for number in members:
                        person = people.get(f"DEMO-{code}-W{number:02d}")
                        if person is None or not await _assigned(session, person, warehouse.id, day):
                            raise ValueError("Demo roster employee is not effective at the warehouse")
                        if await session.get(WarehouseStaff, person.id) is None:
                            raise ValueError("Demo roster employee is not warehouse staff")
                        exists = await session.scalar(
                            select(EmployeeShiftSchedule.id).where(
                                EmployeeShiftSchedule.employee_id == person.id,
                                EmployeeShiftSchedule.work_date == day,
                            )
                        )
                        if exists is not None:
                            continue  # Includes cancellations: never recreate an operator-cancelled shift.
                        row = EmployeeShiftSchedule(
                            employee_id=person.id,
                            warehouse_id=warehouse.id,
                            work_date=day,
                            shift_template_id=template.id,
                            break_start=pause,
                            break_end=resumes,
                            assigned_by=manager.id,
                            assigned_at=now,
                            reason_text=REASON,
                        )
                        session.add(row)
                        await session.flush()
                        await record_decision(
                            session,
                            Action.SHIFT_CHANGED,
                            "employee_shift_schedule",
                            str(row.id),
                            reason_text=REASON,
                            actor_user_id=user.id,
                            actor_employee_id=manager.id,
                            actor_role="warehouse",
                            before=None,
                            after={
                                "employee_id": person.id,
                                "warehouse_id": warehouse.id,
                                "work_date": day.isoformat(),
                                "shift_template_id": template.id,
                                "break_start": pause.isoformat(),
                                "break_end": resumes.isoformat(),
                                "status": "scheduled",
                            },
                        )
                        inserted += 1
            day += timedelta(days=1)
    return inserted


async def run(start: date, end: date) -> int:
    clock.init_from_settings(get_settings().app_now)
    try:
        async with get_sessionmaker()() as session, session.begin():
            return await seed_roster(session, start=start, end=end, now=clock.now())
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    parser.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    try:
        count = asyncio.run(run(args.start, args.end))
    except Exception:
        print("Demo roster failed; check migration, reference seed, named employees and manager authority.")
        return 1
    print(f"Demo roster seeded: {count} new named shifts; existing schedules and attendance preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
