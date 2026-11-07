import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alembic import command
from app.providers.email_smtp import EmailDeliveryError
from app.providers.sms_sim import SimulatedSmsProvider
from app.services.notification_delivery import deliver_queued, delivery_time
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, 21, 30, tzinfo=UTC)  # 22:30 Stockholm


def add_notification(
    dsn: str, template: str = "DISPATCHED", channel: str = "email", actor: str = "NULL"
) -> None:
    execute(
        dsn,
        "INSERT INTO ops.notification(order_id,template,channel,recipient,body,scheduled_for,"
        "created_by_employee_id,dedupe_key) "
        f"VALUES (1,'{template}','{channel}','synthetic@cfo.test',"
        f"'Status and ETA','2026-11-04T00:00Z',{actor},'test')",
    )


def prepare(dsn: str) -> None:
    command.upgrade(alembic_config(dsn), "0007")
    execute(dsn, *rows.REF_HR, rows.order_sql(1), "UPDATE ref.market SET timezone='Europe/Stockholm'")


def test_US_NOT_03_AC1_quiet_hours_and_AC2_explicit_delay_exemption(empty_db: str) -> None:
    prepare(empty_db)
    add_notification(empty_db)
    email, sms = AsyncMock(), SimulatedSmsProvider()
    assert transact(empty_db, lambda s: deliver_queued(s, now=NOW, email=email, sms=sms)) == 0
    assert fetch(empty_db, "SELECT scheduled_for,attempts FROM ops.notification")[0] == (
        datetime(2026, 11, 5, 6, tzinfo=UTC),
        0,
    )
    email.send.assert_not_called()
    execute(empty_db, "DELETE FROM ops.notification")
    add_notification(empty_db, "DELAY", actor="1")
    assert transact(empty_db, lambda s: deliver_queued(s, now=NOW, email=email, sms=sms)) == 1
    assert fetch(empty_db, "SELECT status,attempts FROM ops.notification")[0] == ("sent", 1)
    email.send.assert_awaited_once()
    assert fetch(empty_db, "SELECT action FROM audit.decision_log")[0][0] == "NOTIFICATION_SENT"


def test_US_NOT_03_AC3_attempt_cap_and_sanitized_errors(empty_db: str) -> None:
    prepare(empty_db)
    add_notification(empty_db, "DELAY", actor="1")
    email = AsyncMock()
    email.send.side_effect = EmailDeliveryError("private-body")
    sms = SimulatedSmsProvider()
    for _ in range(4):
        transact(empty_db, lambda s: deliver_queued(s, now=NOW, email=email, sms=sms))
    assert email.send.await_count == 3
    assert fetch(empty_db, "SELECT status,attempts,last_error FROM ops.notification")[0] == (
        "failed",
        3,
        "Delivery failed.",
    )


def test_US_NOT_01_AC4_shadow_mode_suppresses_without_delivery(empty_db: str) -> None:
    prepare(empty_db)
    add_notification(empty_db)
    execute(empty_db, "UPDATE ref.market SET shadow_mode=true")
    email, sms = AsyncMock(), SimulatedSmsProvider()
    transact(empty_db, lambda s: deliver_queued(s, now=NOW, email=email, sms=sms))
    assert fetch(empty_db, "SELECT status,suppressed_reason,attempts FROM ops.notification")[0] == (
        "suppressed",
        "shadow_mode",
        0,
    )
    assert fetch(empty_db, "SELECT action FROM audit.decision_log")[0][0] == "NOTIFICATION_SUPPRESSED"
    email.send.assert_not_called()


def test_US_NOT_01_AC3_sms_persists_sent_status_and_draft_is_never_sent(empty_db: str) -> None:
    prepare(empty_db)
    add_notification(empty_db, "DELAY", "sms_sim", "1")
    email, sms = AsyncMock(), SimulatedSmsProvider()
    assert transact(empty_db, lambda s: deliver_queued(s, now=NOW, email=email, sms=sms)) == 1
    assert len(sms.messages) == 1
    assert transact(empty_db, lambda s: deliver_queued(s, now=NOW, email=email, sms=sms)) == 0
    execute(empty_db, "DELETE FROM ops.notification")
    add_notification(empty_db, "DELAY", "sms_sim")
    assert transact(empty_db, lambda s: deliver_queued(s, now=NOW, email=email, sms=sms)) == 0
    assert len(sms.messages) == 1


def test_US_NOT_03_AC1_quiet_boundaries_and_dst_end() -> None:
    for instant in (datetime(2026, 11, 4, 6, tzinfo=UTC), datetime(2026, 11, 4, 19, 59, tzinfo=UTC)):
        assert (
            delivery_time(instant, timezone="Europe/Stockholm", quiet_hours=("21:00", "07:00"), delay=False)
            == instant
        )
    assert delivery_time(
        datetime(2026, 10, 24, 20, tzinfo=UTC),
        timezone="Europe/Stockholm",
        quiet_hours=("21:00", "07:00"),
        delay=False,
    ) == datetime(2026, 10, 25, 6, tzinfo=UTC)


def test_US_NOT_03_AC4_concurrent_outbox_workers_send_one_queued_row_once(empty_db: str) -> None:
    prepare(empty_db)
    add_notification(empty_db, "DELAY", actor="1")
    email, sms = AsyncMock(), SimulatedSmsProvider()

    async def race(session: AsyncSession) -> tuple[int, int]:
        entered, release = asyncio.Event(), asyncio.Event()

        async def send(**kwargs: object) -> None:
            entered.set()
            await release.wait()

        email.send.side_effect = send
        factory = async_sessionmaker(session.bind)

        async def worker() -> int:
            async with factory() as other, other.begin():
                return await deliver_queued(other, now=NOW, email=email, sms=sms)

        first = asyncio.create_task(worker())
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            second = await asyncio.wait_for(worker(), timeout=5)
        finally:
            release.set()
            first_result = await first
        return first_result, second

    assert transact(empty_db, race) == (1, 0)
    email.send.assert_awaited_once()
