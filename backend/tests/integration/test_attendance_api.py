"""Điểm danh, công suất, attendance_gen (06 v1.4 mục 13.2; US-WH-01, US-WH-02 AC1–AC3; Q11 = B).

Dữ liệu ở hr_fixture (hôm nay = thứ Tư 2026-11-04, Stockholm). Thêm: hai operator WH-1 (SE-012, SE-013, tính
công suất), ca mẫu thứ Tư của WH-1: 07:00–15:00 (expected 1) và 15:00–22:00 (expected 1), 7 giờ hữu ích;
ngày lễ 2026-11-05. Roster WH-1 tính công suất theo employee_no: SE-004 Will, SE-012, SE-013.
"""

import asyncio
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.hr_service import generate_attendance
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401  (fixture)
from tests.integration.conftest import async_url, execute, fetch
from tests.integration.hr_fixture import (
    ADMIN,
    CS,
    DISPATCHER,
    DRIVER,
    SALES,
    SETUP,
    SYSTEM_ADMIN,
    VIEWER,
    WAREHOUSE,
    ZZ_WAREHOUSE,
)

pytestmark = pytest.mark.integration

EXTRA = (
    "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
    "VALUES "
    "(1, 'SE-012', 'Olga', 'Op', 'WAREHOUSE_OPERATOR', '2025-01-01'), "
    "(1, 'SE-013', 'Per', 'Op', 'WAREHOUSE_OPERATOR', '2025-01-01')",
    "INSERT INTO hr.employee_assignment (employee_id, location_id, start_date) VALUES "
    "(11, 1, '2025-01-01'), (12, 1, '2025-01-01')",
    "INSERT INTO hr.warehouse_staff (employee_id, role, counts_in_capacity) VALUES "
    "(11, 'operator', true), (12, 'operator', true)",
    "INSERT INTO hr.shift_template (warehouse_id, weekday, start_time, end_time, useful_hours_per_staff, "
    "expected_staff) VALUES (1, 3, '07:00', '15:00', 7, 1), (1, 3, '15:00', '22:00', 7, 1)",
    "INSERT INTO ref.market_holiday (market_id, holiday_date, name) VALUES (1, '2026-11-05', 'Test holiday')",
)


async def _generate(dsn: str) -> int:
    engine = create_async_engine(async_url(dsn), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            return await generate_attendance(session)
    finally:
        await engine.dispose()


@pytest.fixture
def at(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SETUP, *EXTRA)
    return api


def shifts_of(dsn: str, day: date) -> dict[int, int]:
    rows = fetch(
        dsn,
        "SELECT employee_id, shift_template_id FROM hr.attendance "
        "WHERE work_date = $1 AND status = 'planned'",
        day,
    )
    return {r["employee_id"]: r["shift_template_id"] for r in rows}


def test_Q11_attendance_gen_fills_shifts_in_employee_no_order(at: Api) -> None:
    created = asyncio.run(_generate(at.dsn))
    # 14 ngày từ 04/11: thứ Tư 04/11 và 11/11 có ca; mỗi ngày 3 người tính công suất ở WH-1
    assert created == 6
    assert shifts_of(at.dsn, date(2026, 11, 4)) == {4: 1, 11: 2, 12: 2}  # ca 1 đủ 1 người, dư vào ca cuối
    assert asyncio.run(_generate(at.dsn)) == 0  # chạy lại không tạo trùng
    managers = fetch(at.dsn, "SELECT count(*) AS n FROM hr.attendance WHERE employee_id IN (3, 5)")
    assert managers[0]["n"] == 0  # quản lý, tài xế không tính công suất


def test_US_WH_01_AC1_put_all_present_returns_roster(at: Api) -> None:
    asyncio.run(_generate(at.dsn))
    body = {"date": "2026-11-04", "all_present": True, "items": [{"employee_id": 12, "status": "absent"}]}
    r = at.send("PUT", "/warehouses/1/attendance", WAREHOUSE, body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["counts"] == {"planned": 0, "present": 2, "absent": 1, "leave": 0}
    rows = {i["employee_id"]: i for i in out["items"]}
    assert rows[4]["shift"] == {"id": 1, "start": "07:00", "end": "15:00"} and rows[4]["counts_in_capacity"]
    assert rows[12]["status"] == "absent" and rows[12]["on_approved_leave"] is False
    assert fetch(at.dsn, "SELECT action FROM audit.decision_log")[0]["action"] == "ATTENDANCE_CHANGED"


@pytest.mark.parametrize("user_id", [ADMIN, SYSTEM_ADMIN, DISPATCHER, WAREHOUSE])
def test_get_attendance_allowed(at: Api, user_id: int) -> None:
    asyncio.run(_generate(at.dsn))
    r = at.get("/warehouses/1/attendance", user_id, date="2026-11-04")
    assert r.status_code == 200, r.text
    assert r.json()["counts"]["planned"] == 3


@pytest.mark.parametrize("user_id", [SALES, DRIVER, CS, VIEWER])
def test_attendance_and_capacity_forbidden_roles(at: Api, user_id: int) -> None:
    assert_error(at.get("/warehouses/1/attendance", user_id, date="2026-11-04"), 403, "FORBIDDEN")
    capacity = at.get("/warehouses/1/capacity", user_id, **{"from": "2026-11-04", "to": "2026-11-04"})
    assert_error(capacity, 403, "FORBIDDEN")


def test_attendance_scope(at: Api) -> None:
    assert_error(at.get("/warehouses/1/attendance", ZZ_WAREHOUSE, date="2026-11-04"), 404, "NOT_FOUND")
    assert_error(at.get("/warehouses/3/attendance", WAREHOUSE, date="2026-11-04"), 404, "NOT_FOUND")  # WH-2
    assert_error(at.get("/warehouses/2/attendance", ADMIN, date="2026-11-04"), 404, "NOT_FOUND")  # cửa hàng


@pytest.mark.parametrize("user_id", [ADMIN, DISPATCHER])
def test_put_attendance_only_warehouse(at: Api, user_id: int) -> None:
    body = {"date": "2026-11-04", "all_present": True}
    assert_error(at.send("PUT", "/warehouses/1/attendance", user_id, body), 403, "FORBIDDEN")


def test_put_attendance_body_is_strict(at: Api) -> None:
    body = {"date": "2026-11-04", "all_present": True, "note": "x"}
    assert_error(at.send("PUT", "/warehouses/1/attendance", WAREHOUSE, body), 422, "VALIDATION_ERROR")


def test_US_WH_02_capacity_formula_booked_and_holiday(at: Api) -> None:
    asyncio.run(_generate(at.dsn))
    at.send("PUT", "/warehouses/1/attendance", WAREHOUSE, {"date": "2026-11-04", "all_present": True})
    execute(
        at.dsn,
        "INSERT INTO ref.customer (market_id, external_ref, type, name) VALUES (1, 'C-1', 'business', 'C')",
        "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, contact_name, "
        "delivery_address, delivery_lat, delivery_lon, date_mode, date_to, order_date, currency, "
        "submitted_at) "
        "VALUES ('SE-1', 1, 'E-1', 1, 'C', 'A', 59, 18, 'latest', '2026-11-20', '2026-11-01T08:00Z', 'SEK', "
        "'2026-11-01T08:00Z'), ('SE-2', 1, 'E-2', 1, 'C', 'A', 59, 18, 'latest', '2026-11-20', "
        "'2026-11-01T08:00Z', 'SEK', '2026-11-01T08:00Z')",
        "INSERT INTO plan.planning_run (order_id, order_version, run_no, input_snapshot, result, "
        "hold_expires_at) "
        "VALUES (1, 1, 1, '{}', 'feasible', NULL), (2, 1, 1, '{}', 'feasible', '2026-11-04T23:00Z')",
        "INSERT INTO plan.prep_reservation (run_id, order_id, warehouse_id, work_date, hours, status) VALUES "
        "(1, 1, 1, '2026-11-04', 4, 'committed'), (2, 2, 1, '2026-11-04', 2, 'held')",
    )
    r = at.get("/warehouses/1/capacity", DISPATCHER, **{"from": "2026-11-04", "to": "2026-11-05"})
    assert r.status_code == 200, r.text
    today, holiday = r.json()["days"]
    assert [s["present"] for s in today["shifts"]] == [1, 2]
    assert today["labour_cap_hours"] == pytest.approx(18.9)  # (1 + 2) × 7 × 0,9 (AC1)
    assert today["booked_hours"] == {"committed": 4.0, "held": 2.0}
    assert today["free_hours"] == pytest.approx(12.9)  # AC2
    assert holiday["holiday"] is True and holiday["labour_cap_hours"] == 0  # AC3


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-11-05", "to": "2026-11-04"},
        {"from": "2026-11-01", "to": "2026-12-02"},
        {"from": "2026-11-01"},
    ],
)
def test_capacity_range_validation(at: Api, params: dict[str, str]) -> None:
    assert_error(at.get("/warehouses/1/capacity", ADMIN, **params), 422, "VALIDATION_ERROR")
