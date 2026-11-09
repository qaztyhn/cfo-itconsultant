# ruff: noqa: F811
"""Dispatcher Keep Current (06 §6.6, REPLAN_KEPT): mandatory reason, audit, no plan/reservation change."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.integration import rows
from tests.integration.api_harness import assert_error
from tests.integration.conftest import execute, fetch
from tests.integration.hr_fixture import ADMIN, DISPATCHER, SALES, WAREHOUSE, ZZ_WAREHOUSE
from tests.integration.test_execution_api import api, execution_api  # noqa: F401

pytestmark = pytest.mark.integration


def suggestion(run_no: int = 2) -> tuple[str, ...]:
    return (
        rows.run_sql(1, run_no, "replan_suggestion"),
        "INSERT INTO ops.alert (market_id, order_id, level, type, message, target_roles, dedupe_key) VALUES "
        f"(1, 1, 'warning', 'REPLAN_SUGGESTED', 'A replacement plan is available', '{{dispatcher}}', "
        f"'replan:1:{run_no}')",
    )


def keep(client, run_id: int, actor: int = DISPATCHER, body=None):
    return client.send(
        "POST",
        f"/planning-runs/{run_id}/keep-current",
        actor,
        {"reason_text": "Keep"} if body is None else body,
    )


def snapshot(db: str):
    return {
        "order": [
            tuple(r)
            for r in fetch(db, "SELECT status::text, approved_plan_id, version FROM ops.customer_order")
        ],
        "plans": [
            tuple(r) for r in fetch(db, "SELECT id, status::text FROM plan.fulfilment_plan ORDER BY id")
        ],
        "trips": fetch(db, "SELECT count(*) AS n FROM ops.delivery_trip")[0]["n"],
    }


def count_audit(db: str) -> int:
    return fetch(db, "SELECT count(*) AS n FROM audit.decision_log WHERE action='REPLAN_KEPT'")[0]["n"]


def test_keep_current_audits_closes_the_alert_and_changes_nothing_else(execution_api) -> None:
    execute(execution_api.dsn, *suggestion())
    before = snapshot(execution_api.dsn)
    response = keep(execution_api, 2, body={"reason_text": "Customer confirmed the current date"})
    assert response.status_code == 200, response.text
    assert response.json() == {"run_id": 2, "status": "kept"}
    assert snapshot(execution_api.dsn) == before  # approved plan, order, trips untouched; nothing approved
    audit = fetch(
        execution_api.dsn,
        "SELECT reason_text, plan_id, actor_role FROM audit.decision_log WHERE action='REPLAN_KEPT'",
    )
    assert [(a["reason_text"], a["plan_id"], a["actor_role"]) for a in audit] == [
        ("Customer confirmed the current date", 1, "dispatcher")
    ]
    assert (
        fetch(execution_api.dsn, "SELECT resolved_at IS NOT NULL AS done FROM ops.alert")[0]["done"] is True
    )


@pytest.mark.parametrize("body", [{}, {"reason_text": ""}, {"reason_text": "   "}, {"reason_text": 5}])
def test_reason_is_mandatory(execution_api, body) -> None:
    execute(execution_api.dsn, *suggestion())
    assert_error(keep(execution_api, 2, body=body), 422, "REASON_REQUIRED")
    assert count_audit(execution_api.dsn) == 0


def test_only_an_in_market_dispatcher_may_keep(execution_api) -> None:
    execute(execution_api.dsn, *suggestion())
    for actor in (SALES, WAREHOUSE, ADMIN):
        assert_error(keep(execution_api, 2, actor), 403, "FORBIDDEN")
    assert_error(keep(execution_api, 999), 404, "NOT_FOUND")
    assert count_audit(execution_api.dsn) == 0
    assert fetch(execution_api.dsn, "SELECT resolved_at IS NULL AS open FROM ops.alert")[0]["open"] is True
    assert ZZ_WAREHOUSE  # other-market users are not dispatchers either


def test_only_a_replan_suggestion_run_can_be_kept(execution_api) -> None:
    assert_error(keep(execution_api, 1), 409, "ILLEGAL_TRANSITION")  # run 1 is the initial planning run


def test_a_decided_suggestion_cannot_be_decided_again(execution_api) -> None:
    execute(execution_api.dsn, *suggestion())
    assert keep(execution_api, 2).status_code == 200
    assert_error(keep(execution_api, 2), 409, "ILLEGAL_TRANSITION")
    assert count_audit(execution_api.dsn) == 1


def test_a_stale_suggestion_cannot_be_kept(execution_api) -> None:
    execute(execution_api.dsn, *suggestion(2), rows.run_sql(1, 3, "replan_suggestion"))
    assert_error(keep(execution_api, 2), 409, "ILLEGAL_TRANSITION")
    assert keep(execution_api, 3).status_code == 200


def test_no_active_plan_or_dispatched_order_cannot_keep(execution_api) -> None:
    execute(execution_api.dsn, *suggestion())
    execute(execution_api.dsn, "UPDATE ops.customer_order SET approved_plan_id=NULL")
    assert_error(keep(execution_api, 2), 409, "ILLEGAL_TRANSITION")
    assert count_audit(execution_api.dsn) == 0


def test_concurrent_keeps_record_exactly_one_decision(execution_api) -> None:
    execute(execution_api.dsn, *suggestion())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: keep(execution_api, 2), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    assert count_audit(execution_api.dsn) == 1
