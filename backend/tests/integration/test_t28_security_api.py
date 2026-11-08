"""T28: live-JWT RBAC, object-scope and planning-response privacy regressions.

Real API dependencies and PostgreSQL: no service mocking, no production edits.
"""

import pytest

from app.core.security import issue_token
from tests.integration import rows
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401 (fixture)
from tests.integration.conftest import execute, fetch
from tests.integration.hr_fixture import (
    CS,
    DISPATCHER,
    DRIVER,
    SALES,
    SETUP,
    VIEWER,
)
from tests.integration.test_orders_api import SEED

pytestmark = pytest.mark.integration


@pytest.fixture
def secured(api: Api) -> Api:  # noqa: F811
    execute(
        api.dsn,
        *SETUP,
        *SEED,
        # Unlike order 3, order 2 belongs to the Sales user's store.
        "UPDATE ops.customer_order SET origin_store_id=2 WHERE id=2",
        # One alternative for the same run must remain invisible to Sales.
        rows.plan_sql(1, 2, 2),
        # Seed a synthetic diagnostic marker; it must not leak via compact responses.
        'UPDATE plan.fulfilment_plan SET checks=\'{"safety":{"detail":'
        '{"private_marker":"RESTRICTED_TEST_ONLY"}}}\'::jsonb WHERE id=1',
        'UPDATE plan.planning_run SET input_snapshot=\'{"rejected_candidates":'
        '[{"detail":{"private_marker":"RESTRICTED_TEST_ONLY"}}]}\'::jsonb WHERE id=1',
    )
    return api


@pytest.mark.parametrize(
    ("user_id", "status", "code"),
    [(CS, 403, "FORBIDDEN"), (DRIVER, 403, "FORBIDDEN"), (VIEWER, 404, "NOT_FOUND")],
)
def test_T28_planning_details_forbidden_for_non_planning_roles(
    secured: Api, user_id: int, status: int, code: str
) -> None:
    # A viewer without market scope gets a privacy-preserving 404, not 403.
    for url in ("/planning-runs/1", "/orders/2/planning-runs", "/plans/1"):
        assert_error(secured.get(url, user_id), status, code)


def test_T28_sales_compact_plan_does_not_leak_alternatives_or_diagnostics(secured: Api) -> None:
    run = secured.get("/planning-runs/1", SALES)
    assert run.status_code == 200, run.text
    assert [p["rank"] for p in run.json()["plans"]] == [1]
    assert [p["id"] for p in run.json()["plans"]] == [1]
    assert "RESTRICTED_TEST_ONLY" not in run.text
    for disallowed in ("driver_employee_id", "score", "checks", "rejected_candidates", "load_lines", "gps"):
        assert disallowed not in run.text.lower()
    assert_error(secured.get("/plans/3", SALES), 404, "NOT_FOUND")
    assert secured.get("/plans/3", DISPATCHER).status_code == 200


def test_T28_sales_cannot_enumerate_out_of_scope_planning_objects(secured: Api) -> None:
    # Order 3 was created without origin_store_id; Sales never learns plan or run existence.
    for path in ("/planning-runs/2", "/plans/2", "/orders/3/planning-runs"):
        assert_error(secured.get(path, SALES), 404, "NOT_FOUND")
    assert_error(secured.get("/planning-runs/1", None), 401, "AUTH_INVALID")


def test_T28_old_jwt_cannot_keep_dispatcher_permissions_after_db_downgrade(secured: Api) -> None:
    # Claims are deliberately over-privileged; live DB role must remain authoritative.
    token = issue_token(
        DISPATCHER, {"roles": ["admin", "dispatcher"], "location_ids": [1, 2, 3], "kpi_scopes": ["ops"]}
    )
    headers = {"Authorization": f"Bearer {token}"}
    allowed = secured.client.get("/api/v1/planning-runs/1", headers=headers)
    assert allowed.status_code == 200, allowed.text

    execute(secured.dsn, "UPDATE ref.app_user SET roles='{viewer}', kpi_scopes='{}' WHERE id=2")
    denied = secured.client.get("/api/v1/planning-runs/1", headers=headers)
    assert_error(denied, 403, "FORBIDDEN")
    assert "RESTRICTED_TEST_ONLY" not in denied.text
    assert denied.json()["error"]["correlation_id"]
    # No audit and no plan mutation from a read-only authorization attempt.
    assert fetch(secured.dsn, "SELECT count(*) FROM audit.decision_log")[0][0] == 0


def test_T28_sales_cannot_read_dispatcher_date_negotiation_history(secured: Api) -> None:
    assert_error(secured.get("/orders/2/date-negotiations", SALES), 403, "FORBIDDEN")
    response = secured.get("/orders/2/date-negotiations", DISPATCHER)
    assert response.status_code == 200 and response.json()["items"] == []
