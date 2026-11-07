"""GET /employees, /employees/{id} (06 mục 13.1; Q1/Q3/Q4 PR #12).

Quyền, phạm vi, phân công theo ngày hiệu lực, hiển thị trường theo vai trò (tối thiểu hóa dữ liệu).
"""

import pytest

from tests.integration.api_harness import Api, api, assert_error  # noqa: F401  (fixture)
from tests.integration.conftest import execute
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

MINIMAL = {"id", "first_name", "last_name", "position", "assignment"}
ADMIN_ONLY = {"employee_no", "status", "employment_type", "hire_date", "end_date", "work_email", "work_phone"}
STAFF = {"warehouse_staff", "sales_staff", "dispatcher_staff", "driver_staff", "cs_staff"}


@pytest.fixture
def hr(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SETUP)
    return api


def ids(response: object) -> list[int]:
    return [e["id"] for e in response.json()["items"]]  # type: ignore[attr-defined]


def by_id(response: object) -> dict[int, dict[str, object]]:
    return {e["id"]: e for e in response.json()["items"]}  # type: ignore[attr-defined]


# --- phạm vi -----------------------------------------------------------------------------------------


def test_dispatcher_sees_market_employees_except_terminated(hr: Api) -> None:
    r = hr.get("/employees", DISPATCHER)
    assert r.status_code == 200, r.text
    assert sorted(ids(r)) == [1, 2, 3, 4, 5, 6, 7, 8]  # không có 9 (terminated), 10 (market khác)
    assert r.json()["total"] == 8


def test_warehouse_sees_only_employees_assigned_today_at_own_location(hr: Api) -> None:
    # WH-1 hôm nay: 2, 3, 4, 5 (9 terminated bị ẩn); 7 đã kết thúc 31/10; 8 bắt đầu 1/12
    assert sorted(ids(hr.get("/employees", WAREHOUSE))) == [2, 3, 4, 5]
    assert hr.get("/employees/4", WAREHOUSE).status_code == 200
    for out_of_scope in (7, 8, 6, 10, 9):
        assert_error(hr.get(f"/employees/{out_of_scope}", WAREHOUSE), 404, "NOT_FOUND")


def test_admin_sees_all_statuses_of_market_and_system_admin_all_markets(hr: Api) -> None:
    assert sorted(ids(hr.get("/employees", ADMIN))) == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert 10 in ids(hr.get("/employees", SYSTEM_ADMIN, page_size=50))
    assert_error(hr.get("/employees/10", DISPATCHER), 404, "NOT_FOUND")
    assert sorted(ids(hr.get("/employees", ZZ_WAREHOUSE))) == [10]


@pytest.mark.parametrize("user", [SALES, DRIVER, CS, VIEWER])
def test_other_roles_forbidden(hr: Api, user: int) -> None:
    assert_error(hr.get("/employees", user), 403, "FORBIDDEN")
    assert_error(hr.get("/employees/1", user), 403, "FORBIDDEN")


def test_unauthenticated_and_unknown(hr: Api) -> None:
    assert_error(hr.get("/employees", None), 401, "AUTH_INVALID")
    assert_error(hr.get("/employees/999", ADMIN), 404, "NOT_FOUND")


# --- hiển thị trường (Q4 = C có điều chỉnh) ----------------------------------------------------------


def test_dispatcher_minimal_fields_plus_driver_licence(hr: Api) -> None:
    people = by_id(hr.get("/employees", DISPATCHER))
    driver = people[5]
    assert set(driver) == MINIMAL | {"driver_staff"}
    assert driver["driver_staff"] == {
        "licence_class": "CE",
        "licence_expires_on": "2027-01-31",
        "home_warehouse_id": 1,
        "adr": False,
    }
    assert people[4]["driver_staff"] is None  # không phải tài xế: khối áp dụng được nhưng null
    assert not (ADMIN_ONLY | (STAFF - {"driver_staff"})) & set(driver)


def test_warehouse_minimal_fields_plus_warehouse_staff(hr: Api) -> None:
    worker = hr.get("/employees/4", WAREHOUSE).json()
    assert set(worker) == MINIMAL | {"warehouse_staff"}
    assert worker["warehouse_staff"] == {"role": "operator", "counts_in_capacity": True}
    driver = hr.get("/employees/5", WAREHOUSE).json()
    assert driver["warehouse_staff"] is None and "driver_staff" not in driver


def test_admin_full_fields_and_detail_extras(hr: Api) -> None:
    anna = by_id(hr.get("/employees", ADMIN))[1]
    assert set(anna) == MINIMAL | ADMIN_ONLY | STAFF
    assert (anna["work_email"], anna["work_phone"], anna["employee_no"]) == (
        "anna@cfo.test",
        "+46000001",
        "SE-001",
    )
    detail = hr.get("/employees/7", ADMIN).json()
    assert {"weekly_hours", "reports_to_employee_id", "assignment_history"} <= set(detail)
    assert detail["assignment_history"] == [
        {"location_id": 3, "location_code": "WH-2", "start_date": "2026-11-01", "end_date": None},
        {"location_id": 1, "location_code": "WH-1", "start_date": "2025-01-01", "end_date": "2026-10-31"},
    ]


def test_assignment_is_the_one_effective_today(hr: Api) -> None:
    people = by_id(hr.get("/employees", ADMIN))
    assert people[7]["assignment"] == {
        "location_id": 3,
        "location_code": "WH-2",
        "location_name": "Warehouse Two",
        "start_date": "2026-11-01",
    }
    assert people[8]["assignment"] is None  # phân công chỉ bắt đầu 1/12
    assert people[5]["position"] == {"code": "DRIVER", "name": "Driver"}


# --- lọc, sắp xếp, phân trang ------------------------------------------------------------------------


def test_filters_position_location_status_q(hr: Api) -> None:
    assert ids(hr.get("/employees", DISPATCHER, position_code="DRIVER")) == [5]
    assert sorted(ids(hr.get("/employees", DISPATCHER, location_id=3))) == [7]  # phân công hiệu lực hôm nay
    assert ids(hr.get("/employees", WAREHOUSE, location_id=3)) == []  # ngoài phạm vi → rỗng, không lỗi
    assert ids(hr.get("/employees", ADMIN, status="terminated")) == [9]
    assert ids(hr.get("/employees", DISPATCHER, status="terminated")) == []
    assert ids(hr.get("/employees", DISPATCHER, q="dora")) == [5]
    assert ids(hr.get("/employees", ADMIN, q="SE-006")) == [6]
    assert ids(hr.get("/employees", DISPATCHER, q="SE-006")) == []  # employee_no chỉ admin tìm
    assert_error(hr.get("/employees", ADMIN, status="retired"), 422, "VALIDATION_ERROR")


def test_sort_fields_by_role_and_pagination(hr: Api) -> None:
    r = hr.get("/employees", DISPATCHER, page=1, page_size=3)
    assert [e["last_name"] for e in r.json()["items"]] == ["Admin", "Dispatcher", "Driver"]
    assert r.json()["total"] == 8
    assert ids(hr.get("/employees", ADMIN, sort="-employee_no", page_size=2)) == [9, 8]
    assert_error(hr.get("/employees", DISPATCHER, sort="employee_no"), 422, "VALIDATION_ERROR")
    assert_error(hr.get("/employees", DISPATCHER, sort="hire_date"), 422, "VALIDATION_ERROR")
