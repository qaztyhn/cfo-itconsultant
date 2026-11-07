"""hr_service.day_capacities: DayCapacity cho engine từ DB.

US-WH-02; 05 mục 4 quy tắc 5; 04 mục 6.2 bước 2b. Kho 1 (WH-1), ca 06–14 và 14–22.
Nhân viên 3..12: công nhân kho (counts_in_capacity), 13: quản lý (không tính).
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.engine.types import DayCapacity
from app.services.hr_service import day_capacities
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute

pytestmark = pytest.mark.integration

TUE, WED, THU = date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5)
NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)
WORKERS = range(3, 13)  # 10 công nhân: employee id 3..12
SHIFT_SQL = (
    "INSERT INTO hr.shift_template (warehouse_id, weekday, start_time, end_time, useful_hours_per_staff, "
    "expected_staff) VALUES "
)


def _setup() -> tuple[str, ...]:
    stmts: list[str] = [
        *rows.REF_HR,
        "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) "
        "VALUES (1, 'warehouse', 'WH-2', 'Warehouse 2', 57.7, 11.9, '15:00')",  # location 3
    ]
    for weekday in (2, 3, 4):  # Thứ Ba, Tư, Năm
        stmts += [
            SHIFT_SQL + f"(1, {weekday}, '06:00', '14:00', 7.0, 8)",
            SHIFT_SQL + f"(1, {weekday}, '14:00', '22:00', 7.0, 4)",
        ]
    for i in [*WORKERS, 13]:
        stmts.append(
            "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, "
            f"hire_date) VALUES (1, 'W{i}', 'W', '{i}', 'TEST_POS', '2026-01-01')"
        )
        stmts.append(
            "INSERT INTO hr.warehouse_staff (employee_id, role, counts_in_capacity) "
            f"VALUES ({i}, '{'manager' if i == 13 else 'operator'}', {'false' if i == 13 else 'true'})"
        )
        location = 3 if i == 12 else 1  # W12 phân công ở kho khác
        stmts.append(
            "INSERT INTO hr.employee_assignment (employee_id, location_id, start_date) "
            f"VALUES ({i}, {location}, '2026-01-01')"
        )
    return tuple(stmts)


def _attendance(employee: int, day: date, status: str, shift_id: int) -> str:
    return (
        "INSERT INTO hr.attendance (employee_id, work_date, shift_template_id, status) "
        f"VALUES ({employee}, '{day}', {shift_id}, '{status}')"
    )


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(empty_db, *_setup())
    yield empty_db


def _capacities(dsn: str, days: list[date], exclude_order_id: int | None = None) -> dict[date, DayCapacity]:
    async def run() -> dict[date, DayCapacity]:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session:
                return await day_capacities(
                    session, 1, days, now=NOW, today=WED, exclude_order_id=exclude_order_id
                )
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _staff(cap: DayCapacity) -> list[int]:
    return [s.present_staff for s in cap.shifts]


def test_US_WH_02_AC1_present_staff_per_shift_with_useful_hours(db: str) -> None:
    # shift id: Thứ Tư = 3 (06–14), 4 (14–22)
    execute(db, *(_attendance(e, WED, "present", 3) for e in range(3, 11)))  # 8 người ca sáng
    cap = _capacities(db, [WED])[WED]
    assert [(s.start.hour, s.end.hour) for s in cap.shifts] == [(6, 14), (14, 22)]
    assert _staff(cap) == [8, 0] and cap.shifts[0].useful_hours_per_staff == Decimal("7.00")
    assert cap.booked_hours == Decimal(0)


def test_today_and_past_count_only_present_future_counts_planned(db: str) -> None:
    execute(
        db,
        _attendance(3, TUE, "present", 1),
        _attendance(4, TUE, "planned", 1),  # quá khứ: planned không tính
        _attendance(5, WED, "planned", 3),  # hôm nay: planned không tính
        _attendance(6, WED, "present", 3),
        _attendance(7, THU, "planned", 5),  # tương lai: planned tính
        _attendance(8, THU, "present", 5),
        _attendance(9, THU, "absent", 5),
        _attendance(10, THU, "leave", 5),
    )
    caps = _capacities(db, [TUE, WED, THU])
    assert (_staff(caps[TUE]), _staff(caps[WED]), _staff(caps[THU])) == ([1, 0], [1, 0], [2, 0])


def test_excludes_non_capacity_roles_other_warehouses_and_approved_leave(db: str) -> None:
    execute(
        db,
        _attendance(13, THU, "planned", 5),  # quản lý: counts_in_capacity = false
        _attendance(12, THU, "planned", 5),  # phân công ở kho khác
        _attendance(3, THU, "planned", 5),
        _attendance(4, THU, "planned", 5),
        _attendance(5, THU, "planned", 5),
        "INSERT INTO hr.absence (employee_id, start_date, end_date, type, approved) "
        f"VALUES (3, '{THU}', '{THU}', 'leave', true)",
        "INSERT INTO hr.absence (employee_id, start_date, end_date, type, approved) "
        f"VALUES (4, '{THU}', '{THU}', 'sick', false)",  # chưa duyệt → vẫn tính
    )
    assert _staff(_capacities(db, [THU])[THU]) == [2, 0]


def test_assignment_must_be_active_on_the_day(db: str) -> None:
    execute(
        db,
        f"UPDATE hr.employee_assignment SET end_date = '{WED}' WHERE employee_id = 3",
        _attendance(3, THU, "planned", 5),
        _attendance(4, THU, "planned", 5),
    )
    assert _staff(_capacities(db, [THU])[THU]) == [1, 0]


def test_booked_hours_committed_and_unexpired_held_of_other_orders(db: str) -> None:
    execute(
        db,
        rows.order_sql(1),
        rows.order_sql(2),
        rows.order_sql(3),
        rows.run_sql(1, 1),
        rows.run_sql(2, 1),
        rows.run_sql(3, 1),
        "UPDATE plan.planning_run SET hold_expires_at = '2026-11-04T09:20Z' WHERE id = 2",  # còn hạn
        "UPDATE plan.planning_run SET hold_expires_at = '2026-11-04T09:00Z' WHERE id = 3",  # hết hạn
        "INSERT INTO plan.prep_reservation (run_id, order_id, warehouse_id, work_date, hours, status) VALUES "
        f"(1, 1, 1, '{THU}', 5.5, 'committed'), (2, 2, 1, '{THU}', 3.0, 'held'), "
        f"(3, 3, 1, '{THU}', 7.0, 'held'), (1, 1, 1, '{WED}', 2.0, 'released')",
    )
    assert _capacities(db, [WED, THU])[THU].booked_hours == Decimal("8.500")
    assert _capacities(db, [THU], exclude_order_id=1)[THU].booked_hours == Decimal("3.000")
    assert _capacities(db, [WED])[WED].booked_hours == Decimal(0)


def test_day_without_shift_template_has_no_shifts(db: str) -> None:
    sat = date(2026, 11, 7)
    assert _capacities(db, [sat])[sat].shifts == ()
