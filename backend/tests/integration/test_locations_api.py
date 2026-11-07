"""GET /locations, /locations/{id} (06 mục 13.1; Q1/Q3 PR #12).

Quyền, phạm vi, ngày hiệu lực, lọc, phân trang.
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


@pytest.fixture
def hr(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SETUP)
    return api


def codes(response: object) -> list[str]:
    body = response.json()  # type: ignore[attr-defined]
    return [item["code"] for item in body["items"]]


def test_dispatcher_sees_active_locations_of_own_market(hr: Api) -> None:
    r = hr.get("/locations", DISPATCHER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert codes(r) == ["ST-1", "WH-1", "WH-2"] and body["total"] == 3
    assert (body["page"], body["page_size"]) == (1, 50)


def test_location_schema_owner_and_effective_managers(hr: Api) -> None:
    wh1 = hr.get("/locations/1", DISPATCHER).json()
    assert wh1 == {
        "id": 1,
        "market": "SE",
        "type": "warehouse",
        "code": "WH-1",
        "name": "Warehouse One",
        "address": "Dock 1",
        "lat": 59.3293,
        "lon": 18.0686,
        "loading_cutoff_time": "15:00",
        "is_active": True,
        "owner": {"employee_id": 3, "name": "Wanda Warehouse"},
        # phó cũ hết hạn 31/10 và phó tương lai từ 1/12 không hiển thị (ngày hiệu lực)
        "managers": {"primary": {"employee_id": 3, "name": "Wanda Warehouse"}, "deputy": None},
    }
    wh2 = hr.get("/locations/3", DISPATCHER).json()
    assert wh2["managers"] == {"primary": None, "deputy": None} and wh2["owner"] is None  # chính hết hạn 3/11
    assert "efficiency_factor" not in wh1


def test_warehouse_user_limited_to_locations_assigned_today(hr: Api) -> None:
    assert codes(hr.get("/locations", WAREHOUSE)) == ["WH-1"]
    assert hr.get("/locations/1", WAREHOUSE).status_code == 200
    assert_error(hr.get("/locations/3", WAREHOUSE), 404, "NOT_FOUND")  # cùng market nhưng không phân công
    assert_error(hr.get("/locations/2", WAREHOUSE), 404, "NOT_FOUND")


def test_market_isolation(hr: Api) -> None:
    assert codes(hr.get("/locations", ZZ_WAREHOUSE)) == ["ZZ-WH"]
    assert_error(hr.get("/locations/4", DISPATCHER), 404, "NOT_FOUND")
    assert_error(hr.get("/locations/1", ZZ_WAREHOUSE), 404, "NOT_FOUND")
    assert codes(hr.get("/locations", ADMIN)) == ["ST-1", "WH-1", "WH-2"]  # admin gắn market SE
    assert codes(hr.get("/locations", SYSTEM_ADMIN)) == ["ST-1", "WH-1", "WH-2", "ZZ-WH"]  # admin hệ thống


@pytest.mark.parametrize("user", [SALES, DRIVER, CS, VIEWER])
def test_other_roles_forbidden(hr: Api, user: int) -> None:
    assert_error(hr.get("/locations", user), 403, "FORBIDDEN")
    assert_error(hr.get("/locations/1", user), 403, "FORBIDDEN")


def test_requires_authentication(hr: Api) -> None:
    assert_error(hr.get("/locations", None), 401, "AUTH_INVALID")


def test_unknown_location_404(hr: Api) -> None:
    assert_error(hr.get("/locations/999", ADMIN), 404, "NOT_FOUND")


def test_filters_type_is_active_and_q(hr: Api) -> None:
    assert codes(hr.get("/locations", ADMIN, type="warehouse")) == ["WH-1", "WH-2"]
    assert codes(hr.get("/locations", ADMIN, is_active="false")) == ["OLD"]
    assert codes(hr.get("/locations", ADMIN, q="two")) == ["WH-2"]
    assert codes(hr.get("/locations", ADMIN, q="st-")) == ["ST-1"]
    assert_error(hr.get("/locations", ADMIN, type="garage"), 422, "VALIDATION_ERROR")


def test_sort_and_pagination(hr: Api) -> None:
    r = hr.get("/locations", ADMIN, sort="-name", page=2, page_size=2)
    assert codes(r) == ["ST-1"] and r.json()["total"] == 3  # tên giảm dần: WH Two, WH One | Store One
    assert codes(hr.get("/locations", ADMIN, sort="-code")) == ["WH-2", "WH-1", "ST-1"]
    assert_error(hr.get("/locations", ADMIN, sort="efficiency_factor"), 422, "VALIDATION_ERROR")
    assert_error(hr.get("/locations", ADMIN, page_size=201), 422, "VALIDATION_ERROR")
    assert_error(hr.get("/locations", ADMIN, page=0), 422, "VALIDATION_ERROR")
