"""GET /vehicles, /vehicles/{id} (06 mục 13.1; Q2 = A PR #12).

Dispatcher theo market, warehouse theo kho mình.
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

VEHICLE = (
    "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, capacity_m3, capabilities, "
    "required_licence, allowed_group_ids, status) VALUES "
)
VEHICLES = (
    VEHICLE
    + "(1, 'WH1-CR-01', 'TST101', 'Crane truck', 8000, 30, '{crane}', 'C', '{1,4}', 'available')",  # 1
    VEHICLE + "(3, 'WH2-12-01', 'TST201', 'Truck 12t', 6000, 40, '{}', 'C', '{}', 'available')",  # 2
    VEHICLE + "(4, 'ZZ-12-01', 'TST301', 'Other truck', 6000, 40, '{}', 'C', '{}', 'available')",  # 3
    VEHICLE + "(1, 'WH1-03-01', 'TST102', 'Van', 3500, 10, '{tail_lift}', 'B', '{}', 'maintenance')",  # 4
)


@pytest.fixture
def hr(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SETUP, *VEHICLES)
    return api


def codes(response: object) -> list[str]:
    return [v["code"] for v in response.json()["items"]]  # type: ignore[attr-defined]


def test_vehicle_schema(hr: Api) -> None:
    assert hr.get("/vehicles/1", DISPATCHER).json() == {
        "id": 1,
        "code": "WH1-CR-01",
        "plate": "TST101",
        "name": "Crane truck",
        "home_warehouse": {"id": 1, "code": "WH-1", "name": "Warehouse One"},
        "capacity_kg": 8000.0,
        "capacity_m3": 30.0,
        "capabilities": ["crane"],
        "required_licence": "C",
        "allowed_groups": [{"id": 1, "code": "N1"}, {"id": 4, "code": "N4"}],
        "status": "available",
    }
    assert hr.get("/vehicles/2", DISPATCHER).json()["allowed_groups"] == []  # rỗng = mọi nhóm


def test_US_EMP_04_AC2_dispatcher_reads_vehicles_of_market(hr: Api) -> None:
    r = hr.get("/vehicles", DISPATCHER)
    assert r.status_code == 200, r.text
    assert codes(r) == ["WH1-03-01", "WH1-CR-01", "WH2-12-01"] and r.json()["total"] == 3
    assert_error(hr.get("/vehicles/3", DISPATCHER), 404, "NOT_FOUND")  # market khác


def test_warehouse_reads_only_own_home_warehouse_vehicles(hr: Api) -> None:
    assert codes(hr.get("/vehicles", WAREHOUSE)) == ["WH1-03-01", "WH1-CR-01"]
    assert_error(hr.get("/vehicles/2", WAREHOUSE), 404, "NOT_FOUND")
    assert codes(hr.get("/vehicles", WAREHOUSE, home_warehouse_id=3)) == []  # ngoài phạm vi → rỗng
    assert codes(hr.get("/vehicles", ZZ_WAREHOUSE)) == ["ZZ-12-01"]


def test_admin_market_and_system_admin_all(hr: Api) -> None:
    assert codes(hr.get("/vehicles", ADMIN)) == ["WH1-03-01", "WH1-CR-01", "WH2-12-01"]
    assert codes(hr.get("/vehicles", SYSTEM_ADMIN)) == ["WH1-03-01", "WH1-CR-01", "WH2-12-01", "ZZ-12-01"]


@pytest.mark.parametrize("user", [SALES, DRIVER, CS, VIEWER])
def test_other_roles_forbidden(hr: Api, user: int) -> None:
    assert_error(hr.get("/vehicles", user), 403, "FORBIDDEN")
    assert_error(hr.get("/vehicles/1", user), 403, "FORBIDDEN")


def test_unauthenticated_and_unknown(hr: Api) -> None:
    assert_error(hr.get("/vehicles", None), 401, "AUTH_INVALID")
    assert_error(hr.get("/vehicles/999", ADMIN), 404, "NOT_FOUND")


def test_filters_sort_and_pagination(hr: Api) -> None:
    assert codes(hr.get("/vehicles", DISPATCHER, status="available")) == ["WH1-CR-01", "WH2-12-01"]
    assert codes(hr.get("/vehicles", DISPATCHER, capability="crane")) == ["WH1-CR-01"]
    assert codes(hr.get("/vehicles", DISPATCHER, home_warehouse_id=3)) == ["WH2-12-01"]
    assert codes(hr.get("/vehicles", DISPATCHER, sort="-capacity_kg")) == [
        "WH1-CR-01",
        "WH2-12-01",
        "WH1-03-01",
    ]
    r = hr.get("/vehicles", DISPATCHER, page=2, page_size=2)
    assert codes(r) == ["WH2-12-01"] and r.json()["total"] == 3
    assert_error(hr.get("/vehicles", DISPATCHER, status="broken"), 422, "VALIDATION_ERROR")
    assert_error(hr.get("/vehicles", DISPATCHER, sort="plate"), 422, "VALIDATION_ERROR")
