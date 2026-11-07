"""GET /orders/{id}/timeline (06 v1.4 mục 5.5; US-ORD-03 AC1/AC2).

Dùng dữ liệu đơn của test_orders_api (SEED). Thêm cho đơn 3: một quyết định PLAN_APPROVED của dispatcher,
sự kiện START_PREP trên chuyến 1 (xe V-1), thông báo CONFIRMED đã gửi.
"""

import pytest

from tests.integration.api_harness import Api, api, assert_error  # noqa: F401  (fixture)
from tests.integration.conftest import execute
from tests.integration.hr_fixture import ADMIN, CS, DISPATCHER, DRIVER, SALES, SETUP, VIEWER, WAREHOUSE
from tests.integration.test_orders_api import SEED

pytestmark = pytest.mark.integration


@pytest.fixture
def tl(api: Api) -> Api:  # noqa: F811
    execute(
        api.dsn,
        *SETUP,
        *SEED,
        "INSERT INTO audit.decision_log (ts, correlation_id, actor_user_id, actor_employee_id, actor_role, "
        "action, entity, entity_id, order_id, plan_id, snapshot, before, after) VALUES "
        "('2026-11-02T09:00Z', gen_random_uuid(), 2, 2, 'dispatcher', 'PLAN_APPROVED', 'plan', '2', 3, 2, "
        '\'{"score": 0.25}\', \'{"status": "PLANNED"}\', \'{"status": "APPROVED"}\')',
        "INSERT INTO ops.milestone_event (order_id, trip_id, event_type, occurred_at, actor_user_id, "
        "idempotency_key, payload) VALUES (3, 1, 'START_PREP', '2026-11-13T05:00Z', 3, 'k-1', "
        '\'{"lat": 57.7, "lon": 11.9}\')',
        "INSERT INTO ops.notification (order_id, template, channel, recipient, body, status, sent_at, "
        "dedupe_key) VALUES (3, 'CONFIRMED', 'email', 'secret-recipient@example.test', 'Body', 'sent', "
        "'2026-11-02T09:05Z', '3:CONFIRMED:2:sent')",
    )
    return api


def kinds(response: object) -> list[str]:
    body = response.json()  # type: ignore[attr-defined]
    assert response.status_code == 200, body  # type: ignore[attr-defined]
    return [i["kind"] for i in body["items"]]


def test_US_ORD_03_AC1_dispatcher_sees_merged_history_in_time_order(tl: Api) -> None:
    r = tl.get("/orders/3/timeline", DISPATCHER)
    got = kinds(r)
    assert got[0] == "order_submitted"
    assert {"planning_run", "decision", "milestone", "notification", "eta"} <= set(got)
    ats = [i["at"] for i in r.json()["items"]]
    assert ats == sorted(ats)
    decision = next(i for i in r.json()["items"] if i["kind"] == "decision")
    assert decision["detail"]["action"] == "PLAN_APPROVED"
    assert decision["actor"] == {"role": "dispatcher", "employee_id": 2, "name": "Dan Dispatcher"}
    milestone = next(i for i in r.json()["items"] if i["kind"] == "milestone")
    assert milestone["detail"] == {"type": "START_PREP", "vehicle_code": "V-1"}
    for secret in ("secret-recipient", "score", "before", "snapshot", '"lat"', '"lon"', "57.7"):
        assert secret not in r.text


def test_US_ORD_03_AC2_cs_sees_status_eta_notifications_only(tl: Api) -> None:
    r = tl.get("/orders/3/timeline", CS)
    got = kinds(r)
    assert "decision" not in got and "planning_run" not in got
    assert {"order_submitted", "milestone", "notification", "eta"} <= set(got)
    for item in r.json()["items"]:
        if item["kind"] == "eta":
            assert set(item["detail"]) == {"forecast_eta", "risk_status"}
    assert "secret-recipient" not in r.text and "orange" not in r.text


@pytest.mark.parametrize("user_id", [SALES, DRIVER, VIEWER])
def test_timeline_forbidden_roles(tl: Api, user_id: int) -> None:
    assert_error(tl.get("/orders/3/timeline", user_id), 403, "FORBIDDEN")


def test_timeline_scope(tl: Api) -> None:
    assert_error(tl.get("/orders/3/timeline", WAREHOUSE), 404, "NOT_FOUND")  # kho khác
    assert kinds(tl.get("/orders/2/timeline", WAREHOUSE))[0] == "order_submitted"
    assert_error(tl.get("/orders/999/timeline", ADMIN), 404, "NOT_FOUND")
