"""Điểm danh kho (US-WH-01 AC1–AC4, US-WH-02 AC1; FR-PRP-05; BR-PRP-05; ASM-007).

Dữ liệu ở hr_fixture. Ngày điểm danh 2026-11-12 (thứ Năm, ISO 4), WH-1 có một ca 07:00–15:00, 7 giờ hữu ích.
Dòng attendance planned: 3 Wanda (quản lý, không tính công suất), 4 Will (operator), 5 Dora (tài xế),
6 Sam (cửa hàng — không thuộc roster WH-1), 7 Wes (đã chuyển sang WH-2), 9 Tom (đã nghỉ việc).
"""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core import clock
from app.core.errors import DomainError
from app.services import hr_service
from tests.integration.conftest import alembic_config, async_url, execute, fetch
from tests.integration.hr_fixture import SETUP

pytestmark = pytest.mark.integration
DAY = date(2026, 11, 12)


@dataclass(frozen=True)
class Actor:
    id: int
    employee_id: int | None
    roles: tuple[str, ...]
    location_ids: tuple[int, ...]


WH1_MANAGER = Actor(3, 3, ("warehouse",), (1,))
WH2_MANAGER = Actor(7, 7, ("warehouse",), (3,))


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(
        empty_db,
        *SETUP,
        "INSERT INTO hr.shift_template (warehouse_id, weekday, start_time, end_time, useful_hours_per_staff, "
        "expected_staff) VALUES (1, 4, '07:00', '15:00', 7, 3)",
        "INSERT INTO hr.attendance (employee_id, work_date, shift_template_id) VALUES "
        "(3, '2026-11-12', 1), (4, '2026-11-12', 1), (5, '2026-11-12', 1), (6, '2026-11-12', 1), "
        "(7, '2026-11-12', 1), (9, '2026-11-12', 1)",
    )
    yield empty_db


def run[T](dsn: str, fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def mark(
    dsn: str, actor: Actor, *, all_present: bool, items: tuple[tuple[int, str], ...] = (), warehouse: int = 1
) -> hr_service.AttendanceResult:
    return run(
        dsn,
        lambda s: hr_service.set_attendance(s, actor, warehouse, DAY, all_present=all_present, items=items),
    )


def statuses(dsn: str) -> dict[int, str]:
    rows = fetch(
        dsn, "SELECT employee_id, status::text AS s FROM hr.attendance WHERE work_date = '2026-11-12'"
    )
    return {r["employee_id"]: r["s"] for r in rows}


def present_staff(dsn: str) -> int:
    caps = run(
        dsn,
        lambda s: hr_service.day_capacities(s, 1, [DAY], now=clock.now(), today=date(2026, 11, 12)),
    )
    return caps[DAY].shifts[0].present_staff


def error_of(fn: Callable[[], object]) -> DomainError:
    with pytest.raises(DomainError) as caught:
        fn()
    return caught.value


def test_US_WH_01_AC1_all_present_in_one_write(db: str) -> None:
    result = mark(db, WH1_MANAGER, all_present=True)
    assert result.changed_employee_ids == (3, 4, 5)
    assert result.counts == {"planned": 0, "absent": 0, "leave": 0, "present": 3}
    # AC3: Sam (cửa hàng), Wes (WH-2), Tom (đã nghỉ) không bị đụng tới
    assert statuses(db) == {
        3: "present",
        4: "present",
        5: "present",
        6: "planned",
        7: "planned",
        9: "planned",
    }
    rec = fetch(db, "SELECT recorded_by, recorded_at FROM hr.attendance WHERE employee_id = 4")[0]
    assert rec["recorded_by"] == 3 and rec["recorded_at"] is not None


def test_US_WH_01_AC2_absence_lowers_capacity_and_is_logged(db: str) -> None:
    mark(db, WH1_MANAGER, all_present=True)
    assert present_staff(db) == 1  # AC4: chỉ Will tính công suất (quản lý và tài xế không tính)
    result = mark(db, WH1_MANAGER, all_present=False, items=((4, "absent"),))
    assert result.changed_employee_ids == (4,)
    assert present_staff(db) == 0
    logs = fetch(
        db,
        "SELECT action, entity, entity_id, actor_role, before, after, snapshot "
        "FROM audit.decision_log ORDER BY id",
    )
    assert [r["action"] for r in logs] == ["ATTENDANCE_CHANGED", "ATTENDANCE_CHANGED"]
    assert (logs[1]["entity"], logs[1]["entity_id"], logs[1]["actor_role"]) == (
        "attendance",
        "1:2026-11-12",
        "warehouse",
    )
    assert '"absent": 1' in logs[1]["after"] and '"changed_employee_ids": [4]' in logs[1]["snapshot"]
    assert "Will" not in logs[1]["snapshot"]  # không ghi tên nhân viên


def test_all_present_keeps_leave_and_items_override(db: str) -> None:
    mark(db, WH1_MANAGER, all_present=False, items=((5, "leave"),))
    result = mark(db, WH1_MANAGER, all_present=True, items=((3, "absent"),))
    assert statuses(db)[5] == "leave" and statuses(db)[3] == "absent" and statuses(db)[4] == "present"
    assert result.counts == {"planned": 0, "absent": 1, "leave": 1, "present": 1}


@pytest.mark.parametrize(
    "items",
    [
        ((6, "absent"),),  # AC3: nhân viên cửa hàng không thuộc roster kho
        ((7, "absent"),),  # đã chuyển sang WH-2
        ((9, "present"),),  # đã nghỉ việc
        ((4, "planned"),),  # trạng thái chỉ do job sinh
        ((4, "sick"),),
        ((4, "absent"), (4, "present")),  # trùng
    ],
)
def test_invalid_items_change_nothing(db: str, items: tuple[tuple[int, str], ...]) -> None:
    err = error_of(lambda: mark(db, WH1_MANAGER, all_present=True, items=items))
    assert (err.code, err.details["field"]) == ("VALIDATION_ERROR", "items")
    assert set(statuses(db).values()) == {"planned"}
    assert fetch(db, "SELECT count(*) AS n FROM audit.decision_log")[0]["n"] == 0


def test_US_EMP_03_AC2_other_warehouse_is_not_found(db: str) -> None:
    assert error_of(lambda: mark(db, WH2_MANAGER, all_present=True)).code == "NOT_FOUND"
    assert (
        error_of(lambda: mark(db, WH1_MANAGER, all_present=True, warehouse=2)).code == "NOT_FOUND"
    )  # cửa hàng
    assert error_of(lambda: mark(db, WH1_MANAGER, all_present=True, warehouse=999)).code == "NOT_FOUND"


@pytest.mark.parametrize("roles", [("admin",), ("dispatcher",), ("sales",), ("driver",), ("viewer",)])
def test_only_warehouse_role_records_attendance(db: str, roles: tuple[str, ...]) -> None:
    actor = Actor(1, 1, roles, (1,))
    assert error_of(lambda: mark(db, actor, all_present=True)).code == "FORBIDDEN"
    assert set(statuses(db).values()) == {"planned"}
