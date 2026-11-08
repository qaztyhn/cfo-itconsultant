"""T25 Revenue HTTP contract and CSV audit against real PostgreSQL (US-REV-01).

Independent from ingestion or planning workers: create already-committed orders
and plans directly using the existing integration fixtures.
"""

import csv
from io import StringIO

import pytest

from tests.integration import rows
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute
from tests.integration.test_revenue_service import ORDERS, _order

pytestmark = pytest.mark.integration

SEED = (
    *rows.REF_HR,
    "INSERT INTO ref.location (market_id, type, code, name, lat, lon) "
    "VALUES (1, 'store', 'ST-022', 'Store 22', 59.5, 18.2)",
    "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) "
    "VALUES (1, 'warehouse', 'GBG', 'Göteborg DC', 57.7, 11.9, '15:00')",
    "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
    "VALUES (1, 'E3', 'Test', 'Three', 'TEST_POS', '2026-01-01'), "
    "(1, 'E4', 'Test', 'Four', 'TEST_POS', '2026-01-01')",
    "UPDATE ref.location SET owner_employee_id = 1 WHERE id = 2",
    "UPDATE ref.location SET owner_employee_id = 3 WHERE id = 4",
    "UPDATE ref.app_user SET roles='{sales}' WHERE id=1",
    "INSERT INTO ref.app_user (employee_id, email, password_hash, roles, kpi_scopes) VALUES "
    "(2, 'business@cfo.test', 'not-a-real-hash', '{viewer}', '{revenue_all}'), "
    "(3, 'warehouse@cfo.test', 'not-a-real-hash', '{warehouse}', '{ops}'), "
    "(4, 'dispatcher@cfo.test', 'not-a-real-hash', '{dispatcher}', '{ops}'), "
    "(NULL, 'admin@cfo.test', 'not-a-real-hash', '{admin}', '{}')",
)


def _seed_orders(dsn: str) -> None:
    statements: list[str] = []
    for no, status, amount, store, warehouse, delivered, committed in ORDERS:
        statements.extend(
            (
                _order(no, status, amount, store, delivered=delivered, committed=committed),
                rows.run_sql(no, 1),
                rows.plan_sql(no, no, 1, "approved"),
                f"UPDATE plan.fulfilment_plan SET warehouse_id = {warehouse} WHERE id = {no}",
                f"UPDATE ops.customer_order SET approved_plan_id = {no} WHERE id = {no}",
            )
        )
    execute(dsn, *statements)


@pytest.fixture
def rev(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SEED)
    _seed_orders(api.dsn)
    return api


PERIOD = {"from": "2026-11-01", "to": "2026-11-30"}


def test_US_REV_01_AC1_AC5_summary_and_daily_market_period(rev: Api) -> None:
    r = rev.get("/revenue/summary", 2, view="store", **PERIOD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == PERIOD
    assert body["recognised"] == "1850.50"
    assert body["booked_not_delivered"] == "500.00"
    assert body["orders_delivered"] == 4
    assert body["currency"] == "SEK"
    assert body["share_of_market_pct"] is None
    day = rev.get("/revenue/daily", 2, view="store", location_id=2, **PERIOD)
    assert day.status_code == 200, day.text
    pts = {p["day"]: p["recognised"] for p in day.json()["points"]}
    assert pts["2026-11-10"] == "1000.00"
    assert pts["2026-11-11"] == "500.50"
    assert len(pts) == 30


def test_US_REV_01_AC2_AC3_AC4_scope_views_and_errors(rev: Api) -> None:
    assert rev.get("/revenue/summary", 1, view="store", **PERIOD).json()["recognised"] == "1500.50"
    assert_error(rev.get("/revenue/summary", 1, view="store", location_id=3, **PERIOD), 404, "NOT_FOUND")
    assert_error(
        rev.get("/revenue/summary", 3, view="store", location_id=4, **PERIOD), 422, "VALIDATION_ERROR"
    )
    assert_error(rev.get("/revenue/summary", 3, view="store", **PERIOD), 403, "FORBIDDEN")
    assert_error(rev.get("/revenue/summary", 4, view="store", **PERIOD), 403, "FORBIDDEN")
    assert_error(rev.get("/revenue/summary", None, view="store", **PERIOD), 401, "AUTH_INVALID")
    assert_error(rev.get("/revenue/summary", 1, view="region", **PERIOD), 422, "VALIDATION_ERROR")
    assert_error(
        rev.get("/revenue/summary", 2, view="store", **{"from": "2026-12-01", "to": "2026-11-01"}),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(
        rev.get("/revenue/summary", 2, view="store", **{"from": "2025-01-01", "to": "2026-11-30"}),
        422,
        "VALIDATION_ERROR",
    )


def test_US_REV_01_AC7_market_share_includes_unassigned_store(rev: Api) -> None:
    r = rev.get("/revenue/by-location", 2, view="store", **PERIOD)
    assert r.status_code == 200, r.text
    data = r.json()
    assert sum(float(row["recognised"]) for row in data["rows"]) == 1850.5
    st1 = next(row for row in data["rows"] if row["location_id"] == 2)
    assert st1["share_pct"] == 81.1
    assert next(row for row in data["rows"] if row["location_id"] is None)["name"] == "Unassigned store"
    assert rev.get("/revenue/by-location", 3, view="warehouse", **PERIOD).status_code == 200


def test_US_REV_01_AC9_order_pagination_and_customer_redaction(rev: Api) -> None:
    r = rev.get("/revenue/orders", 2, view="store", location_id=2, page=1, page_size=1, **PERIOD)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 3  # delivered 1+2 and approved 7, not failed/cancelled/outside
    assert len(r.json()["items"]) == 1
    assert "customer_name" not in r.json()["items"][0]
    assert "contact_phone" not in r.text and "delivery_address" not in r.text
    allowed = rev.get("/revenue/orders", 1, view="store", location_id=2, **PERIOD)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["items"][0]["customer_name"] == "Test customer"
    assert_error(rev.get("/revenue/orders", 1, view="store", location_id=3, **PERIOD), 404, "NOT_FOUND")
    assert_error(rev.get("/revenue/orders", 4, view="store", location_id=2, **PERIOD), 403, "FORBIDDEN")
    assert_error(rev.get("/revenue/orders", 2, view="store", **PERIOD), 422, "VALIDATION_ERROR")


def test_US_REV_01_AC8_csv_bom_rows_and_audit(rev: Api) -> None:
    r = rev.get("/revenue/export.csv", 2, view="store", **PERIOD)
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"\xef\xbb\xbf")
    data = list(csv.DictReader(StringIO(r.content.decode("utf-8-sig"))))
    assert set(data[0]) == {
        "day",
        "view",
        "location_code",
        "location_name",
        "orders_delivered",
        "revenue_recognised",
        "revenue_booked",
        "currency",
    }
    assert sum(float(x["revenue_recognised"]) for x in data) == 1850.5
    assert all(x["currency"] == "SEK" and x["view"] == "store" for x in data)
    assert any(x["location_name"] == "Unassigned store" for x in data)
    assert "Test customer" not in r.text
    assert_error(rev.get("/revenue/export.csv", 4, view="store", **PERIOD), 403, "FORBIDDEN")
    import psycopg

    with psycopg.connect(rev.dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT action, snapshot->>'view', (snapshot->>'row_count')::int "
            "FROM audit.decision_log WHERE action = 'REVENUE_EXPORTED'"
        )
        assert cur.fetchall() == [("REVENUE_EXPORTED", "store", len(data))]
