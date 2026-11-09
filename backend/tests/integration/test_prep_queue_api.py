# ruff: noqa: F811
"""M6 canonical Prep Queue (06 Appendix A.1, PROPOSAL-M6-PREP-QUEUE-001) on real PostgreSQL."""

from datetime import UTC, datetime

import pytest

from app.core import clock
from tests.integration import rows
from tests.integration.api_harness import Api, assert_error
from tests.integration.conftest import execute
from tests.integration.hr_fixture import DISPATCHER, DRIVER, SALES, SYSTEM_ADMIN, WAREHOUSE, ZZ_WAREHOUSE
from tests.integration.test_execution_api import api, execution_api  # noqa: F401

pytestmark = pytest.mark.integration

PATH = "/warehouses/1/prep-queue"
DAY = {"date": "2026-11-10"}  # Tuesday: ISO weekday 2

TEMPLATE = (
    "INSERT INTO hr.shift_template (warehouse_id, weekday, start_time, end_time, useful_hours_per_staff, "
    "expected_staff) VALUES (1, 2, '07:00', '15:00', 7, 5)"
)


def schedule(
    employee: int, by: int = 3, day: str = "2026-11-10", template: bool = True, **extra: str
) -> tuple[str, ...]:
    cols = "employee_id, warehouse_id, work_date, status, assigned_by, assigned_at"
    vals = f"{employee}, 1, '{day}', 'scheduled', {by}, '2026-11-05T08:00Z'"
    if template:
        cols, vals = cols + ", shift_template_id", vals + ", 1"
    for key, value in extra.items():
        cols, vals = cols + f", {key}", vals + f", {value}"
    return (
        f"INSERT INTO hr.employee_shift_schedule ({cols}) VALUES ({vals})",
        f"INSERT INTO hr.attendance (employee_id, work_date, status) VALUES ({employee}, '{day}', 'present')",
    )


def booked(hours: str, status: str = "committed", run: int = 1) -> str:
    return (
        "INSERT INTO plan.prep_reservation (run_id, order_id, warehouse_id, work_date, hours, status) "
        f"VALUES ({run}, 1, 1, '2026-11-10', {hours}, '{status}')"
    )


def queue(api_: Api, actor: int = WAREHOUSE, **params: object):
    return api_.get(PATH, actor, **(DAY | params))


def test_unverified_when_no_official_schedule_still_reads_orders_and_booked(execution_api: Api) -> None:
    execute(execution_api.dsn, booked("1.5"))
    response = queue(execution_api)
    assert response.status_code == 200, response.text
    body = response.json()
    capacity = body["capacity"]
    assert capacity["schedule_verified"] is False
    assert (capacity["total_min"], capacity["free_min"], capacity["shifts"]) == (0, 0, [])
    assert capacity["booked_min"] == 90 and type(capacity["booked_min"]) is int
    assert capacity["cutoff"] == "15:00"
    assert [o["order_no"] for o in body["orders"]] == ["SE-M6"]


def test_expected_staff_alone_never_creates_capacity(execution_api: Api) -> None:
    execute(execution_api.dsn, TEMPLATE)  # 5 expected staff, but nobody officially scheduled
    capacity = queue(execution_api).json()["capacity"]
    assert capacity["schedule_verified"] is False and capacity["total_min"] == 0


def test_verified_official_schedule_capacity_and_integer_serialization(execution_api: Api) -> None:
    execute(execution_api.dsn, TEMPLATE, *schedule(4), booked("1.5"))
    capacity = queue(execution_api).json()["capacity"]
    assert capacity["schedule_verified"] is True
    [shift] = capacity["shifts"]
    # 1 present x 7 h x 0.9 x 60 = 378 min; 1.5 h committed = 90 min
    assert (capacity["total_min"], capacity["booked_min"], capacity["free_min"]) == (378, 90, 288)
    assert shift["minutes"] == 378 and shift["booked"] == 90 and shift["present"] == 1
    assert shift["useful_hours"] == 7.0 and shift["share"] == 0.9
    for key in ("total_min", "booked_min", "free_min"):
        assert type(capacity[key]) is int
    assert type(shift["minutes"]) is int and type(shift["booked"]) is int
    assert shift["start"] == "2026-11-10T07:00:00+01:00" and shift["end"] == "2026-11-10T15:00:00+01:00"


def test_schedule_entered_by_a_non_manager_is_not_verified(execution_api: Api) -> None:
    execute(execution_api.dsn, TEMPLATE, *schedule(4, by=4))  # employee 4 is an operator, not a manager
    capacity = queue(execution_api).json()["capacity"]
    assert capacity["schedule_verified"] is False and capacity["total_min"] == 0


def test_manager_without_active_authority_at_assignment_time_is_not_verified(execution_api: Api) -> None:
    # deputy 7's authority at WH-1 ended 2026-10-31, before the entry was assigned on 2026-11-05
    execute(execution_api.dsn, TEMPLATE, *schedule(4, by=7))
    assert queue(execution_api).json()["capacity"]["schedule_verified"] is False


def test_booked_counts_committed_and_only_valid_held_without_double_counting(execution_api: Api) -> None:
    execute(
        execution_api.dsn,
        TEMPLATE,
        *schedule(4),
        booked("2.0", "committed"),
        "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, contact_name, "
        "delivery_address, delivery_lat, delivery_lon, date_mode, date_to, order_date, currency, "
        "submitted_at) VALUES ('SE-HELD', 1, 'EX-HELD', 1, 'x', 'y', 59, 18, 'latest', '2026-11-10', "
        "'2026-11-04T09:00Z', 'SEK', '2026-11-04T09:00Z')",
        "UPDATE plan.planning_run SET hold_expires_at='2026-11-10T16:00Z' WHERE id=1",
        "INSERT INTO plan.prep_reservation (run_id, order_id, warehouse_id, work_date, hours, status) "
        "VALUES (1, 2, 1, '2026-11-10', 1.0, 'held')",
    )
    assert queue(execution_api).json()["capacity"]["booked_min"] == 180  # 2.0 h + 1.0 h
    execute(execution_api.dsn, "UPDATE plan.planning_run SET hold_expires_at='2026-11-10T14:00Z' WHERE id=1")
    assert queue(execution_api).json()["capacity"]["booked_min"] == 120  # expired hold is not booked


def test_booked_above_total_never_gives_negative_free(execution_api: Api) -> None:
    execute(execution_api.dsn, TEMPLATE, *schedule(4), booked("8.0"))
    capacity = queue(execution_api).json()["capacity"]
    assert capacity["booked_min"] == 480 and capacity["total_min"] == 378 and capacity["free_min"] == 0


def test_multi_vehicle_order_has_individual_loading_state_and_cutoff_flag(execution_api: Api) -> None:
    execute(
        execution_api.dsn,
        "UPDATE ops.delivery_trip SET status='loading' WHERE id=1",
        "UPDATE plan.plan_vehicle SET loading_start_at='2026-11-10T15:00Z' WHERE seq=2",
    )
    [order] = queue(execution_api).json()["orders"]
    first, second = order["loading"]
    assert (first["trip_id"], first["loaded"], first["after_cutoff"]) == (1, True, False)
    assert (second["trip_id"], second["loaded"], second["after_cutoff"]) == (2, False, True)
    assert first["vehicle_code"] == "V-EX-1" and second["vehicle_code"] == "V-EX-2"
    assert first["at"] == "2026-11-10T07:30:00+01:00"


def test_order_fields_types_and_next_action_follow_server_state(execution_api: Api) -> None:
    [order] = queue(execution_api).json()["orders"]
    assert (
        order["status"] == "APPROVED" and order["prep_state"] is None and order["next_action"] == "START_PREP"
    )
    assert order["lines"] == 0 and order["work_min"] == 90 and type(order["work_min"]) is int
    assert order["prep_window"]["start"] is None and order["prep_window"]["end"].endswith("+01:00")
    execute(
        execution_api.dsn,
        "UPDATE ops.customer_order SET status='PREPARING' WHERE id=1",
        rows.event_sql(1, "START_PREP", "k1"),
    )
    [order] = queue(execution_api).json()["orders"]
    assert (order["prep_state"], order["next_action"]) == ("running", "GOODS_READY")
    assert order["prep_window"]["start"] is not None
    execute(execution_api.dsn, rows.event_sql(1, "PREP_PAUSED", "k2"))
    [order] = queue(execution_api).json()["orders"]
    assert (order["prep_state"], order["next_action"]) == ("paused", "PREP_RESUMED")


def test_rbac_and_cross_warehouse_or_market_denial(execution_api: Api) -> None:
    assert_error(execution_api.get(PATH, None, **DAY), 401, "AUTH_INVALID")
    for actor in (DISPATCHER, DRIVER, SALES):
        assert_error(queue(execution_api, actor), 403, "FORBIDDEN")
    assert_error(queue(execution_api, ZZ_WAREHOUSE), 404, "NOT_FOUND")  # other market's manager
    assert_error(execution_api.get("/warehouses/3/prep-queue", WAREHOUSE, **DAY), 404, "NOT_FOUND")
    assert_error(queue(execution_api, date="2026-13-40"), 422, "VALIDATION_ERROR")


def test_legacy_alias_returns_exactly_the_canonical_response(execution_api: Api) -> None:
    execute(execution_api.dsn, TEMPLATE, *schedule(4), booked("1.0"))
    canonical = queue(execution_api)
    legacy = execution_api.get("/prep-queue", WAREHOUSE, warehouse_id=1, **DAY)
    assert canonical.status_code == legacy.status_code == 200
    assert legacy.json() == canonical.json()


@pytest.mark.parametrize(
    ("day", "start", "end"),
    [
        ("2026-10-24", "2026-10-24T22:00:00+02:00", "2026-10-25T06:00:00+01:00"),  # autumn DST change
        ("2026-03-28", "2026-03-28T22:00:00+01:00", "2026-03-29T06:00:00+02:00"),  # spring DST change
    ],
)
def test_overnight_shift_across_dst_boundaries_uses_market_offsets(
    execution_api: Api, day: str, start: str, end: str
) -> None:
    execute(
        execution_api.dsn,
        *schedule(4, day=day, template=False, start_time="'22:00'", end_time="'06:00'"),
    )
    response = execution_api.get(PATH, WAREHOUSE, date=day)
    assert response.status_code == 200, response.text
    capacity = response.json()["capacity"]
    [shift] = capacity["shifts"]
    assert (shift["start"], shift["end"]) == (start, end)
    assert shift["useful_hours"] == 8.0 and shift["minutes"] == 432 == capacity["total_min"]  # 8 h x 0.9 x 60


def test_missing_trip_for_an_approved_plan_is_an_error_not_a_fake_200(execution_api: Api) -> None:
    execute(execution_api.dsn, "DELETE FROM ops.trip_stop", "DELETE FROM ops.delivery_trip WHERE id=2")
    assert_error(queue(execution_api), 500, "INTERNAL_ERROR")


def test_default_date_is_the_market_local_today(execution_api: Api) -> None:
    clock.set_now(datetime(2026, 11, 9, 23, 30, tzinfo=UTC))  # already 2026-11-10 in Stockholm
    response = execution_api.get(PATH, WAREHOUSE)
    assert response.status_code == 200 and response.json()["date"] == "2026-11-10"


@pytest.mark.parametrize(
    ("code", "zone"), [("SE", "Europe/Stockholm"), ("DK", "Europe/Copenhagen"), ("NO", "Europe/Oslo")]
)
def test_locations_expose_the_market_iana_timezone_for_every_type(
    execution_api: Api, code: str, zone: str
) -> None:
    if code != "SE":
        execute(
            execution_api.dsn,
            "INSERT INTO ref.market (code, name, timezone, currency) "
            f"VALUES ('{code}', '{code}', '{zone}', 'SEK')",
        )
        market_id = f"(SELECT id FROM ref.market WHERE code='{code}')"
        execute(
            execution_api.dsn,
            "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) VALUES "
            f"({market_id}, 'warehouse', '{code}-W', 'W', 55, 12, '15:00'), "
            f"({market_id}, 'store', '{code}-S', 'S', 55, 12, NULL)",
        )
    listing = execution_api.get("/locations", SYSTEM_ADMIN, page_size=200)
    assert listing.status_code == 200, listing.text
    items = [i for i in listing.json()["items"] if i["market"] == code]
    assert items and all(i["timezone"] == zone for i in items)
    if code != "SE":
        assert {i["type"] for i in items} == {"warehouse", "store"}
    detail = execution_api.get(f"/locations/{items[0]['id']}", SYSTEM_ADMIN)
    assert detail.status_code == 200 and detail.json()["timezone"] == zone
