"""BE-03: real PostgreSQL contract/RBAC/transaction tests for customer contact logs."""

import pytest

from app.core.errors import DomainError
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.hr_fixture import ADMIN, CS, DISPATCHER, SALES, SETUP, VIEWER
from tests.integration.test_orders_api import SEED

pytestmark = pytest.mark.integration


@pytest.fixture
def contact_api(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SETUP, *SEED)
    return api


BODY = {
    "channel": "phone",
    "reason_code": "where_is_my_order",
    "note": "Synthetic conversation summary, no customer phone or email",
}


def test_BE_03_cs_creates_real_contact_log_with_actor_timestamp_and_safe_audit(contact_api: Api) -> None:
    first = contact_api.send("POST", "/orders/3/contact-logs", CS, BODY)
    assert first.status_code == 201, first.text
    item = first.json()
    assert item["id"] > 0
    assert item["order_id"] == 3
    assert item["employee_id"] == 11
    assert item["channel"] == "phone"
    assert item["reason_code"] == "where_is_my_order"
    assert item["note"] == BODY["note"]
    assert item["contacted_at"].endswith("Z") or "+" in item["contacted_at"]
    assert set(item) == {
        "id",
        "order_id",
        "channel",
        "reason_code",
        "note",
        "employee_id",
        "contacted_at",
    }
    recorded = fetch(
        contact_api.dsn,
        "SELECT order_id, customer_id, employee_id, reason_code FROM ops.customer_contact_log",
    )
    assert recorded[0]["order_id"] == 3
    assert recorded[0]["customer_id"] == 1
    assert recorded[0]["employee_id"] == 11
    assert recorded[0]["reason_code"] == "where_is_my_order"
    audit = fetch(
        contact_api.dsn,
        "SELECT actor_user_id, actor_employee_id, actor_role, action, snapshot "
        "FROM audit.decision_log WHERE action='CUSTOMER_CONTACT_RECORDED'",
    )
    assert len(audit) == 1
    assert audit[0]["actor_user_id"] == 12
    assert audit[0]["actor_employee_id"] == 11
    assert audit[0]["actor_role"] == "customer_service"
    assert "Synthetic conversation" not in str(audit[0]["snapshot"])


def test_BE_03_contact_history_has_pagination_and_correct_market_scope(contact_api: Api) -> None:
    for reason in ("first_call", "second_call", "third_call"):
        response = contact_api.send(
            "POST", "/orders/3/contact-logs", CS, {**BODY, "reason_code": reason}
        )
        assert response.status_code == 201, response.text
    page = contact_api.get("/orders/3/contact-logs", CS, page=1, page_size=2)
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 3 and len(body["items"]) == 2
    assert body["page"] == 1 and body["page_size"] == 2
    assert body["items"][0]["id"] > body["items"][1]["id"]
    dispatcher = contact_api.get("/orders/3/contact-logs", DISPATCHER, page=2, page_size=2)
    assert dispatcher.status_code == 200
    assert dispatcher.json()["total"] == 3
    assert len(dispatcher.json()["items"]) == 1
    for secret in ("delivery_lat", "contact_phone", "approved_plan_id", "GPS"):
        assert secret not in page.text
    assert_error(contact_api.get("/orders/6/contact-logs", CS), 404, "NOT_FOUND")
    assert_error(contact_api.get("/orders/6/contact-logs", DISPATCHER), 404, "NOT_FOUND")


@pytest.mark.parametrize("actor", [ADMIN, SALES, VIEWER, None])
def test_BE_03_only_cs_may_write_and_only_dispatcher_cs_may_read(
    contact_api: Api, actor: int | None
) -> None:
    response = contact_api.send("POST", "/orders/3/contact-logs", actor, BODY)
    expected_status = 401 if actor is None else 403
    expected_code = "AUTH_INVALID" if actor is None else "FORBIDDEN"
    assert_error(response, expected_status, expected_code)
    if actor is not None:
        assert_error(contact_api.get("/orders/3/contact-logs", actor), 403, "FORBIDDEN")
    assert fetch(contact_api.dsn, "SELECT count(*) AS n FROM ops.customer_contact_log")[0]["n"] == 0


def test_BE_03_dispatcher_cannot_write_even_with_read_access(contact_api: Api) -> None:
    assert_error(
        contact_api.send("POST", "/orders/3/contact-logs", DISPATCHER, BODY),
        403, "FORBIDDEN",
    )
    response = contact_api.get("/orders/3/contact-logs", DISPATCHER)
    assert response.status_code == 200 and response.json()["items"] == []


def test_BE_03_invalid_input_never_creates_log_or_audit(contact_api: Api) -> None:
    for payload in (
        {**BODY, "reason_code": ""},
        {**BODY, "channel": "phone;DROP TABLE"},
        {**BODY, "note": "s" * 1001},
        {**BODY, "phone": "+460001"},
    ):
        response = contact_api.send("POST", "/orders/3/contact-logs", CS, payload)
        assert_error(response, 422, "VALIDATION_ERROR")
    assert fetch(contact_api.dsn, "SELECT count(*) AS n FROM ops.customer_contact_log")[0]["n"] == 0
    assert fetch(
        contact_api.dsn,
        "SELECT count(*) AS n FROM audit.decision_log WHERE action='CUSTOMER_CONTACT_RECORDED'",
    )[0]["n"] == 0


def test_BE_03_failed_audit_rolls_back_contact_log(contact_api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    async def audit_failure(*_args: object, **_kwargs: object) -> int:
        raise DomainError("PLAN_NOT_APPROVABLE", "Simulated audit persistence failure.")

    from app.services import contact_log_service

    monkeypatch.setattr(contact_log_service, "record_decision", audit_failure)
    response = contact_api.send("POST", "/orders/3/contact-logs", CS, BODY)
    assert_error(response, 409, "PLAN_NOT_APPROVABLE")
    assert fetch(contact_api.dsn, "SELECT count(*) AS n FROM ops.customer_contact_log")[0]["n"] == 0
