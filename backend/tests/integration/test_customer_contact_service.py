"""BE-03 PostgreSQL integration: scoped, transactional CS contact log service.

No fake HTTP endpoint success: orders.py route remains a stub until #189 lands.
"""

from types import SimpleNamespace

import pytest

from app.core.errors import DomainError
from app.services import customer_contact_service
from tests.integration.api_harness import Api, api  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.dev2_helpers import transact
from tests.integration.hr_fixture import CS, DISPATCHER, DRIVER, SETUP, VIEWER
from tests.integration.test_orders_api import SEED

pytestmark = pytest.mark.integration


@pytest.fixture
def seeded(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SETUP, *SEED)
    return api


def actor(uid: int, role: str, market: str, employee: int | None) -> SimpleNamespace:
    return SimpleNamespace(id=uid, roles=(role,), market=market, employee_id=employee)


CS_ACTOR = actor(CS, "customer_service", "SE", 11)
DISPATCHER_ACTOR = actor(DISPATCHER, "dispatcher", "SE", 2)


def test_be03_cs_create_atomic_audit_and_privacy_safe_read(seeded: Api) -> None:
    saved = transact(
        seeded.dsn,
        lambda session: customer_contact_service.create(
            session,
            CS_ACTOR,
            1,
            channel="phone",
            reason_code="where_is_my_order",
            note="Private number +46701234567 and gate code 314159",
        ),
    )
    assert saved["order_id"] == 1
    assert saved["channel"] == "phone"
    assert saved["reason_code"] == "where_is_my_order"
    assert "note" not in saved
    row = fetch(
        seeded.dsn,
        "SELECT order_id,customer_id,employee_id,note,contacted_at FROM ops.customer_contact_log",
    )[0]
    assert row["order_id"] == 1 and row["customer_id"] == 1 and row["employee_id"] == 11
    assert "314159" in row["note"]
    assert row["contacted_at"] is not None
    audit = fetch(
        seeded.dsn,
        "SELECT action,actor_user_id,actor_employee_id,actor_role,snapshot::text AS snapshot,"
        "reason_text FROM audit.decision_log WHERE action='CUSTOMER_CONTACT_RECORDED'",
    )[0]
    assert audit["actor_user_id"] == CS and audit["actor_employee_id"] == 11
    assert audit["action"] == "CUSTOMER_CONTACT_RECORDED"
    assert audit["actor_role"] == "customer_service"
    assert "314159" not in audit["snapshot"]
    assert "46701234567" not in audit["snapshot"]
    assert audit["reason_text"] is None

    for reader in (CS_ACTOR, DISPATCHER_ACTOR):
        page = transact(
            seeded.dsn,
            lambda session, reader=reader: customer_contact_service.list_logs(session, reader, 1),
        )
        assert page["total"] == 1 and len(page["items"]) == 1
        assert set(page["items"][0]) == {"id", "order_id", "channel", "reason_code", "contacted_at"}
        assert "Private number" not in str(page)


def test_be03_rollback_removes_log_and_audit(seeded: Api) -> None:
    async def fail_after_write(session):
        await customer_contact_service.create(session, CS_ACTOR, 1, channel="email", reason_code="complaint")
        raise RuntimeError("force rollback")

    with pytest.raises(RuntimeError, match="force rollback"):
        transact(seeded.dsn, fail_after_write)
    assert fetch(seeded.dsn, "SELECT count(*) AS n FROM ops.customer_contact_log")[0]["n"] == 0
    assert fetch(
        seeded.dsn, "SELECT count(*) AS n FROM audit.decision_log WHERE action='CUSTOMER_CONTACT_RECORDED'"
    )[0]["n"] == 0


@pytest.mark.parametrize(
    ("person", "expected"),
    [
        (actor(VIEWER, "viewer", "SE", None), "FORBIDDEN"),
        (actor(DRIVER, "driver", "SE", 5), "FORBIDDEN"),
        (DISPATCHER_ACTOR, "FORBIDDEN"),
        (actor(CS, "customer_service", "ZZ", 11), "NOT_FOUND"),
        (actor(CS, "customer_service", "SE", None), "FORBIDDEN"),
    ],
)
def test_be03_create_negative_rbac_and_scope(seeded: Api, person, expected: str) -> None:
    with pytest.raises(DomainError) as caught:
        transact(
            seeded.dsn,
            lambda session: customer_contact_service.create(
                session, person, 1, channel="chat", reason_code="other"
            ),
        )
    assert caught.value.code == expected
    assert fetch(seeded.dsn, "SELECT count(*) AS n FROM ops.customer_contact_log")[0]["n"] == 0


@pytest.mark.parametrize(
    ("channel", "reason", "note"),
    [
        ("sms", "other", None),
        ("phone", "made_up_reason", None),
        ("email", "other", "X" * 2001),
    ],
)
def test_be03_reject_invalid_contact_record(seeded: Api, channel: str, reason: str, note: str | None) -> None:
    with pytest.raises(DomainError) as caught:
        transact(
            seeded.dsn,
            lambda session: customer_contact_service.create(
                session, CS_ACTOR, 1, channel=channel, reason_code=reason, note=note
            ),
        )
    assert caught.value.code == "VALIDATION_ERROR"


def test_be03_contact_read_negative_rbac_and_market(seeded: Api) -> None:
    transact(
        seeded.dsn,
        lambda session: customer_contact_service.create(
            session, CS_ACTOR, 1, channel="chat", reason_code="delay_inquiry"
        ),
    )
    for person, code in (
        (actor(VIEWER, "viewer", "SE", None), "FORBIDDEN"),
        (actor(CS, "customer_service", "ZZ", 11), "NOT_FOUND"),
    ):
        with pytest.raises(DomainError) as caught:
            transact(
                seeded.dsn,
                lambda session, person=person: customer_contact_service.list_logs(session, person, 1),
            )
        assert caught.value.code == code
    page = transact(
        seeded.dsn,
        lambda session: customer_contact_service.list_logs(session, CS_ACTOR, 1, page=2, page_size=1),
    )
    assert page["items"] == [] and page["total"] == 1
