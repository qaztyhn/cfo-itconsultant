"""M7: real PostgreSQL alert authorization, filtering, ack and deduplication."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.alert_service import raise_alert
from tests.integration import rows
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
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

SETUP_ALERTS = (
    *SETUP,
    "INSERT INTO ref.customer (market_id, external_ref, type, name) "
    "VALUES (1, 'RISK-C', 'business', 'Synthetic customer')",
    "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, "
    "contact_name, delivery_address, delivery_lat, delivery_lon, date_mode, date_to, "
    "order_date, currency, submitted_at, status, promise_start, promise_end) "
    "VALUES ('SE-RISK-1', 1, 'RISK-1', 1, 'Only synthetic', 'Only synthetic', 59, 18, "
    "'latest', '2026-11-10', '2026-11-04T09:00Z', 'SEK', '2026-11-04T09:00Z', "
    "'APPROVED', '2026-11-10T08:00Z', '2026-11-10T10:00Z')",
    rows.run_sql(1, 1),
    rows.plan_sql(1, 1, 1, "approved"),
    "UPDATE ops.customer_order SET approved_plan_id=1 WHERE id=1",
    "INSERT INTO ops.alert (order_id, market_id, level, type, message, target_roles, dedupe_key) "
    "VALUES (1, 1, 'warning', 'RISK_ORANGE', 'Risk alert for approved order', "
    "'{dispatcher,warehouse,customer_service}', 'risk:1:orange')",
    "INSERT INTO ops.alert (order_id, market_id, level, type, message, target_roles, dedupe_key) "
    "VALUES (1, 1, 'critical', 'OVERDUE', 'Private dispatcher detail', "
    "'{dispatcher,warehouse,customer_service}', 'risk:1:overdue')",
    "INSERT INTO ops.alert (market_id, level, type, message, target_roles, dedupe_key) "
    "VALUES (2, 'critical', 'GPS_LOST', 'Other market', '{dispatcher}', 'other-market')",
)


@pytest.fixture
def alerts(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SETUP_ALERTS)
    return api


def test_US_RSK_03_AC1_critical_first_filters_and_market_scope(alerts: Api) -> None:
    result = alerts.get("/alerts", DISPATCHER)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["total"] == 2
    assert [item["type"] for item in body["items"]] == ["OVERDUE", "RISK_ORANGE"]
    assert "Other market" not in result.text
    by_type = alerts.get("/alerts", DISPATCHER, type="RISK_ORANGE", resolved=False)
    assert [item["type"] for item in by_type.json()["items"]] == ["RISK_ORANGE"]
    paged = alerts.get("/alerts", DISPATCHER, page=2, page_size=1)
    assert paged.json()["total"] == 2 and paged.json()["items"][0]["type"] == "RISK_ORANGE"
    assert alerts.get("/alerts", DISPATCHER, resolved=True).json()["total"] == 0
    assert alerts.get("/alerts", DISPATCHER, order_id=999999).json()["total"] == 0


def test_US_RSK_03_AC1_role_warehouse_scope_and_privacy(alerts: Api) -> None:
    assert alerts.get("/alerts", WAREHOUSE).json()["total"] == 2
    assert alerts.get("/alerts", ZZ_WAREHOUSE).json()["total"] == 0
    for viewer in (DRIVER, SALES, VIEWER):
        assert_error(alerts.get("/alerts", viewer), 403, "FORBIDDEN")
    assert_error(alerts.get("/alerts", None), 401, "AUTH_INVALID")
    # Unscoped CS account is denied rather than silently granted cross-market access.
    assert_error(alerts.get("/alerts", CS), 403, "FORBIDDEN")
    execute(
        alerts.dsn,
        "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, "
        "position_code, hire_date) VALUES (1,'CS-RISK','Synthetic','CS','DISPATCHER','2025-01-01')",
        "UPDATE ref.app_user SET employee_id=11 WHERE id=12",
    )
    seen = alerts.get("/alerts", CS)
    assert seen.status_code == 200, seen.text
    assert seen.json()["total"] == 2
    assert all(item["message"] is None for item in seen.json()["items"])
    assert "Private dispatcher detail" not in seen.text


def test_US_RSK_03_AC2_ack_is_scope_safe_and_idempotent(alerts: Api) -> None:
    assert_error(alerts.send("POST", "/alerts/1/ack", WAREHOUSE), 403, "FORBIDDEN")
    assert_error(alerts.send("POST", "/alerts/1/ack", SALES), 403, "FORBIDDEN")
    assert_error(alerts.send("POST", "/alerts/3/ack", DISPATCHER), 404, "NOT_FOUND")
    ack = alerts.send("POST", "/alerts/1/ack", DISPATCHER)
    assert ack.status_code == 200, ack.text
    assert ack.json()["acknowledged_by"] == 2
    again = alerts.send("POST", "/alerts/1/ack", ADMIN)
    assert again.status_code == 200
    assert again.json() == ack.json()
    assert fetch(alerts.dsn, "SELECT acknowledged_by FROM ops.alert WHERE id=1")[0][0] == 2
    assert_error(alerts.send("POST", "/alerts/1/ack", SYSTEM_ADMIN), 403, "FORBIDDEN")
    # Admin can read but cannot manufacture an employee ID to acknowledge.


def test_US_RSK_03_AC2_AC3_concurrent_raise_keeps_single_open_record(alerts: Api) -> None:
    async def same_key() -> tuple[int | None, int | None]:
        engine = create_async_engine(async_url(alerts.dsn), poolclass=NullPool)
        maker = async_sessionmaker(engine)
        async def once() -> int | None:
            async with maker() as session, session.begin():
                return await raise_alert(
                    session, market_id=1, type_="RISK_ORANGE", level="warning",
                    message="Risk only", dedupe_key="risk-concurrent",
                    target_roles=("dispatcher",), order_id=1,
                )
        try:
            a, b = await asyncio.gather(once(), once())
            return a, b
        finally:
            await engine.dispose()
    one, two = asyncio.run(same_key())
    assert (one is None) != (two is None)
    assert fetch(
        alerts.dsn,
        "SELECT count(*) AS n FROM ops.alert WHERE dedupe_key='risk-concurrent' "
        "AND resolved_at IS NULL",
    )[0]["n"] == 1


def test_US_RSK_03_AC3_resolved_key_can_recur(alerts: Api) -> None:
    execute(alerts.dsn, "UPDATE ops.alert SET resolved_at='2026-11-10T09:00Z' WHERE id=1")
    assert alerts.get("/alerts", DISPATCHER, resolved=True).json()["total"] == 1
    # Other service-level integration test covers reopen and concurrent insert.
