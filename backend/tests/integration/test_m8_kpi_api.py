"""M8 real PostgreSQL KPI and read-only decision-log API integration tests.

Every test creates a fresh migrated database through the existing API harness.
All data is synthetic and uses the approved market/warehouse schema.
"""

import asyncpg
import pytest

from tests.integration import rows
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.hr_fixture import (
    ADMIN,
    CS,
    DISPATCHER,
    SALES,
    SETUP,
    SYSTEM_ADMIN,
    VIEWER,
    WAREHOUSE,
)

pytestmark = pytest.mark.integration
PERIOD = {"from": "2026-11-10", "to": "2026-11-11"}

SEED = (
    *SETUP,
    rows.order_sql(1),
    rows.order_sql(2),
    rows.order_sql(3),
    rows.order_sql(4),
    rows.run_sql(1, 1),
    rows.run_sql(2, 1),
    rows.run_sql(3, 1),
    rows.run_sql(4, 1),
    rows.plan_sql(1, 1, 1, "approved"),
    rows.plan_sql(2, 2, 2, "manual", manual="manual_exception"),
    rows.plan_sql(3, 3, 1, "approved"),
    rows.plan_sql(4, 4, 1, "approved"),
    "UPDATE ops.customer_order SET approved_plan_id=id, origin_store_id=2, "
    "submitted_at='2026-11-10T08:00Z', approved_at='2026-11-10T08:15Z', "
    "committed_date='2026-11-10', promise_end='2026-11-10T23:00Z' WHERE id IN (1,2,3,4)",
    "UPDATE ops.customer_order SET status='DELIVERED', delivered_at='2026-11-10T22:50Z', "
    "closed_at='2026-11-10T22:50Z' WHERE id=1",
    "UPDATE ops.customer_order SET status='DELIVERED', delivered_at='2026-11-10T23:50Z', "
    "closed_at='2026-11-10T23:50Z' WHERE id=2",
    "UPDATE ops.customer_order SET status='FAILED', closed_at='2026-11-11T10:00Z' WHERE id=3",
    "UPDATE ops.customer_order SET status='APPROVED' WHERE id=4",
    "INSERT INTO audit.improvement_log (order_id, warehouse_id, handling_groups, "
    "prep_error_min, eta_error_min, accepted_unchanged, delivered_at) VALUES "
    "(1, 1, '{N1}', 5, 10, true, '2026-11-10T22:50Z'), "
    "(2, 1, '{N1}', -15, -20, false, '2026-11-10T23:50Z')",
    "INSERT INTO hr.shift_template "
    "(warehouse_id, weekday, start_time, end_time, useful_hours_per_staff, expected_staff) "
    "VALUES (1, 2, '07:00', '15:00', 7, 1)",
    "INSERT INTO hr.attendance (employee_id, work_date, shift_template_id, status) "
    "VALUES (4, '2026-11-10', 1, 'present'), (4, '2026-11-11', 1, 'present')",
    "INSERT INTO plan.prep_reservation (run_id, order_id, warehouse_id, work_date, hours, status) "
    "VALUES (1, 1, 1, '2026-11-10', 3, 'committed'), "
    "(2, 2, 1, '2026-11-11', 1, 'committed')",
    "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, "
    "position_code, hire_date) "
    "VALUES (1,'OPS-VIEW-1','Synthetic','Viewer','DISPATCHER','2025-01-01')",
    "INSERT INTO ref.app_user (employee_id, email, password_hash, roles, kpi_scopes) "
    "VALUES (11,'ops-viewer@cfo.test','not-a-real-hash','{viewer}','{ops}')",
)


@pytest.fixture
def kpi(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SEED)
    return api


def test_US_KPI_01_AC1_AC2_AC3_metrics_use_approved_sources_without_costs(kpi: Api) -> None:
    response = kpi.get("/kpi/summary", DISPATCHER, **PERIOD)
    assert response.status_code == 200, response.text
    values = {key: row["value"] for key, row in response.json()["metrics"].items()}
    assert len(values) == 10
    assert values["planning_time_min"] == 15
    assert values["on_time_rate"] == 0.5
    assert values["labour_hours_per_delivery"] == 1.5
    assert values["km_per_delivery"] == 42
    assert values["prep_error_min"] == 10
    assert values["eta_error_min"] == 15
    assert values["failed_delivery_rate"] == pytest.approx(1 / 3)
    assert values["manual_plan_count"] == 1
    assert values["capacity_utilisation"] == pytest.approx(4 / 12.6)
    assert values["plan_acceptance_rate"] is None  # missing unchanged evidence is NOT zero
    assert "cost_per_delivery" not in response.text
    assert "revenue" not in response.text


def test_US_KPI_01_AC1_market_local_midnight_determines_daily_bucket(kpi: Api) -> None:
    result = kpi.get("/kpi/daily", DISPATCHER, metric="on_time_rate", **PERIOD)
    assert result.status_code == 200, result.text
    assert result.json()["points"] == [
        {"day": "2026-11-10", "value": 1.0},
        {"day": "2026-11-11", "value": 0.0},
    ]
    labour = kpi.get("/kpi/daily", DISPATCHER, metric="labour_hours_per_delivery", **PERIOD)
    assert [day["value"] for day in labour.json()["points"]] == [1.5, 1.5]


def test_US_KPI_01_AC4_operational_scope_excludes_revenue_owner(kpi: Api) -> None:
    for user_id in (VIEWER, SALES, CS):
        assert_error(kpi.get("/kpi/summary", user_id, **PERIOD), 403, "FORBIDDEN")
        assert_error(kpi.get("/kpi/daily", user_id, metric="on_time_rate", **PERIOD), 403, "FORBIDDEN")
        assert_error(kpi.get("/kpi/diagnostics", user_id), 403, "FORBIDDEN")
    assert_error(kpi.get("/kpi/summary", None, **PERIOD), 401, "AUTH_INVALID")
    assert_error(kpi.get("/kpi/summary", SYSTEM_ADMIN, **PERIOD), 403, "FORBIDDEN")
    assert kpi.get("/kpi/summary", WAREHOUSE, **PERIOD).status_code == 200
    assert kpi.get("/kpi/summary", ADMIN, **PERIOD).status_code == 200
    assert kpi.get("/kpi/summary", 14, **PERIOD).status_code == 200


def test_US_KPI_01_AC4_warehouse_location_and_market_filters(kpi: Api) -> None:
    assert kpi.get("/kpi/summary", WAREHOUSE, warehouse_id=1, **PERIOD).status_code == 200
    assert_error(kpi.get("/kpi/summary", WAREHOUSE, warehouse_id=3, **PERIOD), 404, "NOT_FOUND")
    assert_error(kpi.get("/kpi/summary", WAREHOUSE, warehouse_id=4, **PERIOD), 404, "NOT_FOUND")
    assert_error(kpi.get("/kpi/summary", DISPATCHER, warehouse_id=2, **PERIOD), 422, "VALIDATION_ERROR")
    result = kpi.get("/kpi/summary", DISPATCHER, warehouse_id=3, **PERIOD)
    assert result.status_code == 200
    assert result.json()["metrics"]["on_time_rate"]["value"] is None
    assert_error(kpi.get("/kpi/summary", DISPATCHER, store_id=99, **PERIOD), 404, "NOT_FOUND")


def test_US_KPI_01_AC1_empty_period_and_validation_are_not_fabricated(kpi: Api) -> None:
    empty = {"from": "2027-02-10", "to": "2027-02-10"}
    response = kpi.get("/kpi/summary", ADMIN, **empty)
    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["on_time_rate"]["value"] is None
    assert response.json()["metrics"]["capacity_utilisation"]["value"] is None
    assert response.json()["metrics"]["manual_plan_count"]["value"] == 0
    assert_error(kpi.get("/kpi/daily", ADMIN, metric="unknown_metric", **PERIOD), 422, "VALIDATION_ERROR")
    assert_error(
        kpi.get("/kpi/summary", ADMIN, **{"from": "2026-12-01", "to": "2026-11-01"}), 422, "VALIDATION_ERROR"
    )


def test_US_KPI_02_AC1_admin_baseline_write_compare_and_audit(kpi: Api) -> None:
    for role in (DISPATCHER, WAREHOUSE, VIEWER):
        assert_error(
            kpi.send("PUT", "/kpi/baseline/planning_time_min", role, {"value": "15"}),
            403,
            "FORBIDDEN",
        )
    response = kpi.send("PUT", "/kpi/baseline/planning_time_min", ADMIN, {"value": "15"})
    assert response.status_code == 200, response.text
    assert response.json()["value"] == 15
    report = kpi.get("/kpi/summary", ADMIN, **PERIOD)
    assert report.status_code == 200
    assert report.json()["metrics"]["planning_time_min"] == {"value": 15, "baseline": 15.0, "change": 0.0}
    baselines = fetch(kpi.dsn, "SELECT metric,value::text,source FROM audit.kpi_baseline")
    assert [tuple(record) for record in baselines] == [("planning_time_min", "15", "manual")]
    audit = fetch(kpi.dsn, "SELECT action,entity,correlation_id FROM audit.decision_log")
    assert [(record["action"], record["entity"]) for record in audit] == [("CONFIG_CHANGED", "kpi_baseline")]
    assert str(audit[0]["correlation_id"]) == response.headers["X-Correlation-ID"]


def test_US_LOG_01_AC1_AC3_redacts_raw_decisions_and_respects_market(kpi: Api) -> None:
    execute(
        kpi.dsn,
        "INSERT INTO audit.decision_log "
        "(correlation_id, actor_employee_id, actor_role, action, entity, entity_id, order_id, "
        "reason_code, reason_text, snapshot, before, after, ts) VALUES "
        "('00000000-0000-0000-0000-000000000001', 2, 'dispatcher', "
        "'PLAN_APPROVED', 'order', 'SECRET-ADDRESS', 1, 'RULE_APPROVED', "
        "'PRIVATE CUSTOMER PHONE', '{\"recipient\":\"PRIVATE-EMAIL\"}', "
        '\'{"phone":"PRIVATE-BEFORE"}\', \'{"address":"PRIVATE-AFTER"}\', '
        "'2026-11-10T10:00Z')",
        "INSERT INTO audit.decision_log "
        "(correlation_id, actor_employee_id, actor_role, action, entity, order_id, ts) VALUES "
        "('00000000-0000-0000-0000-000000000002', 10, 'warehouse', "
        "'PLAN_PROPOSED', 'plan', NULL, '2026-11-10T10:00Z')",
    )
    result = kpi.get("/audit/decisions", DISPATCHER, **PERIOD)
    assert result.status_code == 200, result.text
    assert result.json()["total"] == 1
    assert result.json()["items"][0]["action"] == "PLAN_APPROVED"
    assert result.json()["items"][0]["correlation_id"] == "00000000-0000-0000-0000-000000000001"
    for forbidden in (
        "SECRET-ADDRESS",
        "PRIVATE CUSTOMER PHONE",
        "PRIVATE-EMAIL",
        "PRIVATE-BEFORE",
        "PRIVATE-AFTER",
    ):
        assert forbidden not in result.text
    assert_error(kpi.get("/audit/decisions", VIEWER, **PERIOD), 403, "FORBIDDEN")
    assert_error(kpi.get("/audit/decisions", WAREHOUSE, **PERIOD), 403, "FORBIDDEN")
    assert_error(kpi.get("/audit/decisions", CS, **PERIOD), 403, "FORBIDDEN")
    assert kpi.get("/audit/decisions", 14, **PERIOD).status_code == 200


def test_US_LOG_01_AC1_filters_sort_and_paginate(kpi: Api) -> None:
    for suffix in (1, 2):
        execute(
            kpi.dsn,
            "INSERT INTO audit.decision_log "
            "(correlation_id,actor_employee_id,actor_role,action,entity,order_id,ts) "
            f"VALUES ('00000000-0000-0000-0000-00000000000{suffix}',"
            "2,'dispatcher','PLAN_APPROVED','order',1,"
            f"'2026-11-10T10:0{suffix}Z')",
        )
    page = kpi.get("/audit/decisions", ADMIN, page=1, page_size=1, **PERIOD)
    assert page.status_code == 200
    assert page.json()["total"] == 2 and len(page.json()["items"]) == 1
    assert page.json()["items"][0]["ts"].startswith("2026-11-10T10:02")
    filtered = kpi.get("/audit/decisions", ADMIN, order_id=1, action="PLAN_APPROVED", **PERIOD)
    assert filtered.json()["total"] == 2
    assert_error(
        kpi.get("/audit/decisions", ADMIN, action="a@example.test", **PERIOD), 422, "VALIDATION_ERROR"
    )


def test_US_KPI_01_AC1_diagnostics_do_not_fabricate_missing_source_metrics(kpi: Api) -> None:
    response = kpi.get("/kpi/diagnostics", ADMIN)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "hard_constraint_violations": None,
        "event_to_alert_latency_s_median": None,
    }


def test_US_LOG_01_AC2_decisions_and_milestones_remain_immutable(kpi: Api) -> None:
    execute(
        kpi.dsn,
        "INSERT INTO audit.decision_log "
        "(correlation_id,actor_employee_id,actor_role,action,entity,order_id) VALUES "
        "('00000000-0000-0000-0000-000000000021',2,'dispatcher',"
        "'PLAN_APPROVED','order',1)",
        rows.event_sql(1, "START_PREP", "immutable-kpi-1"),
    )
    with pytest.raises(asyncpg.RaiseError):
        execute(kpi.dsn, "UPDATE audit.decision_log SET action='PLAN_PROPOSED' WHERE id=1")
    with pytest.raises(asyncpg.RaiseError):
        execute(kpi.dsn, "DELETE FROM audit.decision_log WHERE id=1")
    with pytest.raises(asyncpg.RaiseError):
        execute(kpi.dsn, "DELETE FROM ops.milestone_event WHERE order_id=1")
