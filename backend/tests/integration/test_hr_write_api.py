"""Ghi nhân sự cho admin (06 mục 13; US-EMP-01 AC1–AC5, US-EMP-03 AC4; ASM-006).

Dữ liệu ở hr_fixture (hôm nay = 2026-11-04 theo giờ Stockholm). WH-1 = 1: quản lý chính Wanda (3), phó
tương lai Fay (8, phân công WH-1 từ 2026-12-01), owner = 3. Will (4) và Dora (5) làm ở WH-1; Sam (6) ở
ST-1 (2).
"""

import asyncpg
import pytest

from tests.integration.api_harness import Api, api, assert_error  # noqa: F401  (fixture)
from tests.integration.conftest import execute, fetch, rejects
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
NON_ADMINS = (DISPATCHER, WAREHOUSE, DRIVER, SALES, CS, VIEWER, ZZ_WAREHOUSE)


@pytest.fixture
def hr(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SETUP)
    return api


def assignments(dsn: str, employee_id: int) -> list[tuple[int, str, str | None]]:
    rows = fetch(
        dsn,
        "SELECT location_id, start_date::text AS s, end_date::text AS e FROM hr.employee_assignment "
        "WHERE employee_id = $1 ORDER BY start_date",
        employee_id,
    )
    return [(r["location_id"], r["s"], r["e"]) for r in rows]


def managers(dsn: str, location_id: int) -> list[tuple[int, str, str, str | None]]:
    rows = fetch(
        dsn,
        "SELECT employee_id, level::text AS level, valid_from::text AS f, valid_to::text AS t "
        "FROM hr.location_manager WHERE location_id = $1 ORDER BY id",
        location_id,
    )
    return [(r["employee_id"], r["level"], r["f"], r["t"]) for r in rows]


def field_error(response: object, field: str) -> None:
    assert_error(response, 422, "VALIDATION_ERROR")  # type: ignore[arg-type]
    assert response.json()["error"]["details"]["field"] == field  # type: ignore[attr-defined]


# --- assignments ------------------------------------------------------------------------------------------


def test_US_EMP_01_AC2_transfer_closes_old_assignment(hr: Api) -> None:
    r = hr.send("POST", "/employees/4/assignments", ADMIN, {"location_id": 3, "start_date": "2026-11-10"})
    assert r.status_code == 200, r.text
    assert r.json()["assignment"]["location_id"] == 1  # hôm nay vẫn ở WH-1
    assert assignments(hr.dsn, 4) == [(1, "2025-01-01", "2026-11-09"), (3, "2026-11-10", None)]


def test_US_EMP_01_AC2_transfer_starting_today_is_effective_now(hr: Api) -> None:
    r = hr.send(
        "POST", "/employees/4/assignments", SYSTEM_ADMIN, {"location_id": 3, "start_date": "2026-11-04"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["assignment"]["location_id"] == 3


def test_US_EMP_01_AC1_db_rejects_second_open_assignment(hr: Api) -> None:
    rejects(
        hr.dsn,
        asyncpg.UniqueViolationError,
        "ux_one_active_assignment",
        "INSERT INTO hr.employee_assignment (employee_id, location_id, start_date) "
        "VALUES (4, 3, '2026-11-10')",
    )


@pytest.mark.parametrize(
    ("employee_id", "body", "field"),
    [
        (4, {"location_id": 1, "start_date": "2026-11-10"}, "location_id"),  # đã ở đó
        (4, {"location_id": 3, "start_date": "2026-11-03"}, "start_date"),  # quá khứ
        (4, {"location_id": 4, "start_date": "2026-11-10"}, "location_id"),  # market khác
        (4, {"location_id": 5, "start_date": "2026-11-10"}, "location_id"),  # địa điểm đóng
        (4, {"location_id": 999, "start_date": "2026-11-10"}, "location_id"),
        (9, {"location_id": 3, "start_date": "2026-11-10"}, "employee_id"),  # đã nghỉ việc
        (3, {"location_id": 3, "start_date": "2026-11-10"}, "employee_id"),  # quản lý chính WH-1
        (8, {"location_id": 3, "start_date": "2026-11-20"}, "start_date"),  # phân công mở bắt đầu 12-01
    ],
)
def test_assignment_validation(hr: Api, employee_id: int, body: dict[str, object], field: str) -> None:
    before = assignments(hr.dsn, employee_id)
    field_error(hr.send("POST", f"/employees/{employee_id}/assignments", ADMIN, body), field)
    assert assignments(hr.dsn, employee_id) == before


def test_assignment_body_is_strict(hr: Api) -> None:
    body = {"location_id": 3, "start_date": "2026-11-10", "end_date": "2027-01-01"}
    assert_error(hr.send("POST", "/employees/4/assignments", ADMIN, body), 422, "VALIDATION_ERROR")
    assert_error(
        hr.send("POST", "/employees/4/assignments", ADMIN, {"location_id": 3}), 422, "VALIDATION_ERROR"
    )


@pytest.mark.parametrize("user_id", NON_ADMINS)
def test_assignment_forbidden_for_non_admin(hr: Api, user_id: int) -> None:
    r = hr.send("POST", "/employees/4/assignments", user_id, {"location_id": 3, "start_date": "2026-11-10"})
    assert_error(r, 403, "FORBIDDEN")
    assert assignments(hr.dsn, 4) == [(1, "2025-01-01", None)]


def test_write_without_token_is_401(hr: Api) -> None:
    r = hr.send("POST", "/employees/4/assignments", None, {"location_id": 3, "start_date": "2026-11-10"})
    assert_error(r, 401, "AUTH_INVALID")


def test_admin_cannot_touch_other_market(hr: Api) -> None:
    r = hr.send("POST", "/employees/10/assignments", ADMIN, {"location_id": 4, "start_date": "2026-11-10"})
    assert_error(r, 404, "NOT_FOUND")
    assert_error(hr.send("POST", "/employees/10/terminate", ADMIN), 404, "NOT_FOUND")
    assert_error(hr.send("PATCH", "/locations/4/owner", ADMIN, {"owner_employee_id": 10}), 404, "NOT_FOUND")
    assert_error(
        hr.send("PUT", "/locations/4/managers", ADMIN, {"primary_employee_id": 10}), 404, "NOT_FOUND"
    )


# --- terminate --------------------------------------------------------------------------------------------


def test_US_EMP_03_AC4_terminate_locks_account_and_keeps_history(hr: Api) -> None:
    assert hr.get("/auth/me", 4).status_code == 200
    r = hr.send("POST", "/employees/4/terminate", ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "terminated"
    employee = fetch(hr.dsn, "SELECT status::text AS s, end_date::text AS e FROM hr.employee WHERE id = 4")[0]
    assert (employee["s"], employee["e"]) == ("terminated", "2026-11-04")
    assert assignments(hr.dsn, 4) == [(1, "2025-01-01", "2026-11-04")]
    assert fetch(hr.dsn, "SELECT is_active FROM ref.app_user WHERE employee_id = 4")[0]["is_active"] is False
    assert_error(hr.get("/auth/me", 4), 401, "AUTH_INVALID")  # token cũ bị từ chối ở lần gọi kế


def test_terminate_also_caps_a_closed_assignment_ending_later(hr: Api) -> None:
    hr.send("POST", "/employees/4/assignments", ADMIN, {"location_id": 3, "start_date": "2026-11-04"})
    # phân công WH-1 đã đóng 2026-11-03, WH-2 mở từ hôm nay
    assert hr.send("POST", "/employees/4/terminate", ADMIN).status_code == 200
    assert assignments(hr.dsn, 4) == [(1, "2025-01-01", "2026-11-03"), (3, "2026-11-04", "2026-11-04")]


@pytest.mark.parametrize("employee_id", [3, 8, 9])  # quản lý chính, phó tương lai, đã nghỉ
def test_terminate_validation(hr: Api, employee_id: int) -> None:
    field_error(hr.send("POST", f"/employees/{employee_id}/terminate", ADMIN), "employee_id")


@pytest.mark.parametrize("user_id", NON_ADMINS)
def test_terminate_forbidden_for_non_admin(hr: Api, user_id: int) -> None:
    assert_error(hr.send("POST", "/employees/4/terminate", user_id), 403, "FORBIDDEN")
    assert fetch(hr.dsn, "SELECT status::text AS s FROM hr.employee WHERE id = 4")[0]["s"] == "active"


# --- managers ---------------------------------------------------------------------------------------------


def test_US_EMP_01_AC4_new_primary_replaces_old_and_takes_ownership(hr: Api) -> None:
    r = hr.send("PUT", "/locations/1/managers", ADMIN, {"primary_employee_id": 5, "deputy_employee_id": 4})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["managers"]["primary"]["employee_id"] == 5 and body["managers"]["deputy"]["employee_id"] == 4
    assert body["owner"]["employee_id"] == 5
    assert managers(hr.dsn, 1) == [
        (3, "primary", "2025-01-01", "2026-11-03"),
        (7, "deputy", "2025-01-01", "2026-10-31"),
        (8, "deputy", "2026-12-01", "2026-11-30"),  # phó tương lai bị hủy, vẫn giữ lịch sử
        (5, "primary", "2026-11-04", None),
        (4, "deputy", "2026-11-04", None),
    ]


def test_unchanged_primary_keeps_its_record(hr: Api) -> None:
    r = hr.send("PUT", "/locations/1/managers", ADMIN, {"primary_employee_id": 3, "deputy_employee_id": None})
    assert r.status_code == 200, r.text
    rows = managers(hr.dsn, 1)
    assert rows[0] == (3, "primary", "2025-01-01", None) and len(rows) == 3
    assert r.json()["managers"]["deputy"] is None


def test_custom_owner_is_kept_when_primary_changes(hr: Api) -> None:
    assert hr.send("PATCH", "/locations/1/owner", ADMIN, {"owner_employee_id": 4}).status_code == 200
    r = hr.send("PUT", "/locations/1/managers", ADMIN, {"primary_employee_id": 5})
    assert r.json()["owner"]["employee_id"] == 4


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"primary_employee_id": 6}, "primary_employee_id"),  # AC5: làm ở ST-1, không ở WH-1
        ({"primary_employee_id": 5, "deputy_employee_id": 8}, "deputy_employee_id"),  # phân công từ 12-01
        ({"primary_employee_id": 5, "deputy_employee_id": 5}, "deputy_employee_id"),
        ({"primary_employee_id": 9}, "primary_employee_id"),  # đã nghỉ
        ({"primary_employee_id": 10}, "primary_employee_id"),  # market khác
        ({"primary_employee_id": 7}, "primary_employee_id"),  # phân công WH-1 đã kết thúc
    ],
)
def test_US_EMP_01_AC5_manager_needs_effective_assignment(
    hr: Api, body: dict[str, object], field: str
) -> None:
    before = managers(hr.dsn, 1)
    field_error(hr.send("PUT", "/locations/1/managers", ADMIN, body), field)
    assert managers(hr.dsn, 1) == before


def test_US_EMP_01_AC3_db_rejects_second_primary(hr: Api) -> None:
    rejects(
        hr.dsn,
        asyncpg.UniqueViolationError,
        "ux_one_primary_manager",
        "INSERT INTO hr.location_manager (location_id, employee_id, level, valid_from) "
        "VALUES (1, 5, 'primary', '2026-11-04')",
    )


@pytest.mark.parametrize("user_id", NON_ADMINS)
def test_managers_and_owner_forbidden_for_non_admin(hr: Api, user_id: int) -> None:
    assert_error(
        hr.send("PUT", "/locations/1/managers", user_id, {"primary_employee_id": 5}), 403, "FORBIDDEN"
    )
    assert_error(hr.send("PATCH", "/locations/1/owner", user_id, {"owner_employee_id": 5}), 403, "FORBIDDEN")


# --- owner ------------------------------------------------------------------------------------------------


def test_US_EMP_01_AC4_admin_reassigns_owner(hr: Api) -> None:
    r = hr.send("PATCH", "/locations/2/owner", ADMIN, {"owner_employee_id": 6})
    assert r.status_code == 200, r.text
    assert r.json()["owner"] == {"employee_id": 6, "name": "Sam Sales"}


@pytest.mark.parametrize("owner", [9, 10, 999])
def test_owner_must_be_active_in_market(hr: Api, owner: int) -> None:
    field_error(
        hr.send("PATCH", "/locations/2/owner", ADMIN, {"owner_employee_id": owner}), "owner_employee_id"
    )


def test_unknown_location_is_404(hr: Api) -> None:
    assert_error(hr.send("PATCH", "/locations/999/owner", ADMIN, {"owner_employee_id": 6}), 404, "NOT_FOUND")
