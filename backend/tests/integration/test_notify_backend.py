"""Real PostgreSQL N1-N5 tests: transactional outbox, RBAC, replay and privacy."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.core.errors import DomainError
from app.providers.sms_sim import SimulatedSmsProvider
from app.services import notify_service
from app.services.notification_delivery import deliver_queued
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 9, 10, tzinfo=UTC)
NIGHT = datetime(2026, 11, 9, 21, 30, tzinfo=UTC)  # 22:30 Stockholm
WINDOW = {"start": "2026-11-10T09:00:00+01:00", "end": "2026-11-10T11:00:00+01:00"}
LATER = {"start": "2026-11-11T09:00:00+01:00", "end": "2026-11-11T11:00:00+01:00"}


def actor(role: str = "dispatcher", market: str = "ZZ") -> SimpleNamespace:
    return SimpleNamespace(id=1, employee_id=1, roles=(role,), market=market)


def _order(no: int, status: str) -> str:
    sql = rows.order_sql(no)
    return sql.replace("currency, submitted_at) VALUES", "currency, submitted_at, status) VALUES").replace(
        "'EUR', '2026-11-04T09:00Z')",
        f"'EUR', '2026-11-04T09:00Z', '{status}')",
    )


def prepare(dsn: str, *, status: str = "APPROVED") -> None:
    command.upgrade(alembic_config(dsn), "0007")
    execute(
        dsn,
        *rows.REF_HR,
        "UPDATE ref.customer SET email='demo@cfo.test',preferred_channel='email'",
        "UPDATE ref.market SET timezone='Europe/Stockholm', locale='en'",
        _order(1, status),
        rows.run_sql(1, 1),
        rows.plan_sql(1, 1, 1, status="approved"),
        "UPDATE ops.customer_order SET approved_plan_id=1,committed_date='2026-11-10',"
        "promise_start='2026-11-10T08:00Z',promise_end='2026-11-10T10:00Z' WHERE id=1",
        "INSERT INTO ops.alert(order_id,market_id,type,level,message,target_roles,dedupe_key) "
        "VALUES (1,1,'PREDICTED_LATE','critical','Synthetic late signal',"
        "'{dispatcher}','risk:1:PREDICTED_LATE')",
    )


def run[T](dsn: str, fn):
    return transact(dsn, fn)


def _draft(session: AsyncSession) -> object:
    return notify_service.create_delay_draft(1, {**WINDOW, "version": 1}, session=session, actor=actor())


def test_US_NOT_01_AC1_automatic_queue_is_deduped_and_transactional(empty_db: str) -> None:
    prepare(empty_db)

    async def action(session: AsyncSession) -> tuple[int, int]:
        first = await notify_service.enqueue(1, "CONFIRMED", 1, session=session)
        second = await notify_service.enqueue(1, "CONFIRMED", 1, session=session)
        return first, second

    with patch("app.services.notify_service.clock.now", return_value=NOW):
        first, second = run(empty_db, action)
    assert first == second
    assert fetch(empty_db, "SELECT template,status,attempts FROM ops.notification")[0] == (
        "CONFIRMED",
        "queued",
        0,
    )
    assert fetch(empty_db, "SELECT count(*) FROM ops.notification")[0][0] == 1

    async def rollback(session: AsyncSession) -> None:
        await notify_service.enqueue(1, "DISPATCHED", 1, session=session)

    # Wrong order state aborts before write, never leaves a second notification.
    with pytest.raises(DomainError) as error:
        run(empty_db, rollback)
    assert error.value.code == "ILLEGAL_TRANSITION"
    assert fetch(empty_db, "SELECT count(*) FROM ops.notification")[0][0] == 1


def test_US_NOT_01_AC1_failure_after_queue_rolls_back_outbox(empty_db: str) -> None:
    prepare(empty_db)

    async def abandon(session: AsyncSession) -> None:
        await notify_service.enqueue(1, "CONFIRMED", 1, session=session)
        raise RuntimeError("synthetic caller rollback")

    with pytest.raises(RuntimeError):
        run(empty_db, abandon)
    assert fetch(empty_db, "SELECT count(*) FROM ops.notification")[0][0] == 0


def test_US_NOT_03_AC1_market_quiet_hours_and_post_commit_delivery(empty_db: str) -> None:
    prepare(empty_db)
    with patch("app.services.notify_service.clock.now", return_value=NIGHT):
        run(empty_db, lambda s: notify_service.enqueue(1, "CONFIRMED", 1, session=s))
    row = fetch(empty_db, "SELECT status,scheduled_for FROM ops.notification")[0]
    assert row["status"] == "queued"
    assert row["scheduled_for"] == datetime(2026, 11, 10, 6, tzinfo=UTC)
    email = AsyncMock()
    sms = SimulatedSmsProvider()
    assert (
        run(
            empty_db,
            lambda s: deliver_queued(s, now=NIGHT, email=email, sms=sms),
        )
        == 0
    )
    email.send.assert_not_called()
    assert (
        run(
            empty_db,
            lambda s: deliver_queued(s, now=datetime(2026, 11, 10, 6, tzinfo=UTC), email=email, sms=sms),
        )
        == 1
    )
    email.send.assert_awaited_once()
    assert fetch(empty_db, "SELECT status,attempts FROM ops.notification")[0] == ("sent", 1)


def test_US_NOT_02_AC1_draft_and_send_are_separate_with_idempotency(empty_db: str) -> None:
    prepare(empty_db)
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        draft = run(empty_db, _draft)
        assert draft is not None
        assert run(empty_db, _draft) == draft
    record = fetch(empty_db, "SELECT status,created_by_employee_id FROM ops.notification")[0]
    assert record == ("draft", None)
    key = str(uuid4())
    payload = {"eta_window": WINDOW, "version": 1}
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        result = run(
            empty_db,
            lambda s: notify_service.send_draft(draft, actor(), payload, key, session=s),
        )
        replay = run(
            empty_db,
            lambda s: notify_service.send_draft(draft, actor(), payload, key, session=s),
        )
    assert replay == result and result["status"] == "queued"
    assert fetch(empty_db, "SELECT status,created_by_employee_id FROM ops.notification")[0] == (
        "queued",
        1,
    )
    with pytest.raises(DomainError) as error:
        run(
            empty_db,
            lambda s: notify_service.send_draft(
                draft, actor(), {"eta_window": WINDOW, "version": 2}, key, session=s
            ),
        )
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    assert fetch(empty_db, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 1
    assert (
        fetch(empty_db, "SELECT count(*) FROM audit.decision_log WHERE action='NOTIFICATION_SENT'")[0][0] == 0
    )


def test_US_NOT_02_AC5_cross_market_and_non_dispatcher_cannot_send(empty_db: str) -> None:
    prepare(empty_db)
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        draft = run(empty_db, _draft)
    assert draft is not None
    for bad in (actor("customer_service"), actor("admin"), actor("dispatcher", market="NO")):
        with pytest.raises(DomainError) as error:
            run(
                empty_db,
                lambda s, person=bad: notify_service.send_draft(
                    draft, person, {"eta_window": WINDOW, "version": 1}, str(uuid4()), session=s
                ),
            )
        assert error.value.code in ("FORBIDDEN", "NOT_FOUND")
    assert fetch(empty_db, "SELECT status FROM ops.notification")[0][0] == "draft"
    assert fetch(empty_db, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 0


def test_US_NOT_02_AC3_discard_requires_reason_and_audits_once(empty_db: str) -> None:
    prepare(empty_db)
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        draft = run(empty_db, _draft)
    with pytest.raises(DomainError) as error:
        run(empty_db, lambda s: notify_service.discard_draft(draft, actor(), " ", session=s))
    assert error.value.code == "REASON_REQUIRED"
    first = run(empty_db, lambda s: notify_service.discard_draft(draft, actor(), "Not approved", session=s))
    second = run(empty_db, lambda s: notify_service.discard_draft(draft, actor(), "Not approved", session=s))
    assert first == second == {"id": draft, "status": "suppressed"}
    assert (
        fetch(empty_db, "SELECT count(*) FROM audit.decision_log WHERE action='NOTIFICATION_SUPPRESSED'")[0][
            0
        ]
        == 1
    )


def test_US_NOT_02_AC1_changed_date_requires_customer_agreement(empty_db: str) -> None:
    prepare(empty_db)
    with pytest.raises(DomainError) as error:
        run(
            empty_db,
            lambda s: notify_service.create_delay_draft(1, {**LATER, "version": 1}, session=s, actor=actor()),
        )
    assert error.value.code == "DATE_AGREEMENT_REQUIRED"
    execute(
        empty_db,
        "INSERT INTO ops.date_negotiation(order_id,proposed_date,outcome,channel,"
        "contacted_at,recorded_by) VALUES "
        "(1,'2026-11-11','agreed','phone','2026-11-09T09:00Z',1)",
    )
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        draft = run(
            empty_db,
            lambda s: notify_service.create_delay_draft(
                1,
                {**LATER, "version": 1, "date_negotiation_id": 1},
                session=s,
                actor=actor(),
            ),
        )
    assert draft is not None
    with pytest.raises(DomainError) as error:
        run(
            empty_db,
            lambda s: notify_service.send_draft(
                draft,
                actor(),
                {"eta_window": LATER, "version": 1},
                str(uuid4()),
                session=s,
            ),
        )
    assert error.value.code == "DATE_AGREEMENT_REQUIRED"
    queued = run(
        empty_db,
        lambda s: notify_service.send_draft(
            draft,
            actor(),
            {"eta_window": LATER, "version": 1, "date_negotiation_id": 1},
            str(uuid4()),
            session=s,
        ),
    )
    assert queued["status"] == "queued"


def test_US_NOT_03_AC4_snapshot_does_not_follow_later_order_eta_or_pii(empty_db: str) -> None:
    prepare(empty_db)
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        run(empty_db, lambda s: notify_service.enqueue(1, "CONFIRMED", 1, session=s))
    execute(
        empty_db,
        "UPDATE ops.customer_order SET promise_start='2026-11-12T08:00Z',"
        "promise_end='2026-11-12T10:00Z',contact_name='Private test contact',"
        "delivery_address='Private test address' WHERE id=1",
    )
    email = AsyncMock()
    run(
        empty_db,
        lambda s: deliver_queued(s, now=NOW, email=email, sms=SimulatedSmsProvider()),
    )
    message = email.send.call_args.kwargs["text"]
    assert "2026-11-10" in message
    assert "2026-11-12" not in message
    assert "Private" not in message
    preview = run(empty_db, lambda s: notify_service.get_notification(s, 1, actor("customer_service")))
    assert preview["recipient_masked"].endswith("@cfo.test")
    assert "demo@" not in preview["recipient_masked"]
    assert "Private" not in str(preview)


def test_US_NOT_01_AC4_shadow_mode_suppresses_and_audits(empty_db: str) -> None:
    prepare(empty_db)
    execute(empty_db, "UPDATE ref.market SET shadow_mode=true")
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        run(empty_db, lambda s: notify_service.enqueue(1, "CONFIRMED", 1, session=s))
    assert fetch(empty_db, "SELECT status,suppressed_reason FROM ops.notification")[0] == (
        "suppressed",
        "shadow_mode",
    )
    assert fetch(empty_db, "SELECT action FROM audit.decision_log")[0][0] == "NOTIFICATION_SUPPRESSED"


@pytest.mark.parametrize("template", ["DISPATCHED", "DELIVERED", "FAILED"])
def test_US_NOT_01_AC1_status_queues_are_idempotent(empty_db: str, template: str) -> None:
    prepare(empty_db, status=template)
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        first = run(empty_db, lambda session: notify_service.enqueue(1, template, 1, session=session))
        second = run(empty_db, lambda session: notify_service.enqueue(1, template, 1, session=session))
    assert first == second
    assert fetch(empty_db, "SELECT template,status FROM ops.notification")[0] == (template, "queued")


def test_US_NOT_02_AC5_cached_send_never_bypasses_current_market_scope(empty_db: str) -> None:
    prepare(empty_db)
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        draft = run(empty_db, _draft)
        assert draft is not None
        key = str(uuid4())
        payload = {"eta_window": WINDOW, "version": 1}
        run(
            empty_db,
            lambda session: notify_service.send_draft(draft, actor(), payload, key, session=session),
        )
    with pytest.raises(DomainError) as error:
        run(
            empty_db,
            lambda session: notify_service.send_draft(
                draft, actor(market="NO"), payload, key, session=session
            ),
        )
    assert error.value.code == "NOT_FOUND"


def test_US_NOT_01_AC2_recipient_with_display_name_never_leaks_into_queue(empty_db: str) -> None:
    prepare(empty_db)
    execute(
        empty_db,
        "UPDATE ref.customer SET email='Customer Name <demo@cfo.test>'",
    )
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        run(empty_db, lambda session: notify_service.enqueue(1, "CONFIRMED", 1, session=session))
    result = fetch(empty_db, "SELECT status,recipient,suppressed_reason FROM ops.notification")[0]
    assert result == ("suppressed", "suppressed@cfo.test", "recipient_not_allowed")


def test_US_NOT_02_AC4_delay_draft_threshold_uses_market_configuration(empty_db: str) -> None:
    prepare(empty_db)
    with patch("app.services.notify_service.clock.now", return_value=NOW):
        first = run(empty_db, _draft)
        assert first is not None
        run(
            empty_db,
            lambda session: notify_service.send_draft(
                first, actor(), {"eta_window": WINDOW, "version": 1}, str(uuid4()), session=session
            ),
        )
        too_small = run(
            empty_db,
            lambda session: notify_service.create_delay_draft(
                1,
                {
                    "start": "2026-11-10T09:15:00+01:00",
                    "end": "2026-11-10T11:15:00+01:00",
                    "version": 2,
                },
                session=session,
                actor=actor(),
            ),
        )
        assert too_small is None
        enough = run(
            empty_db,
            lambda session: notify_service.create_delay_draft(
                1,
                {
                    "start": "2026-11-10T09:30:00+01:00",
                    "end": "2026-11-10T11:30:00+01:00",
                    "version": 2,
                },
                session=session,
                actor=actor(),
            ),
        )
        assert enough is not None and enough != first
