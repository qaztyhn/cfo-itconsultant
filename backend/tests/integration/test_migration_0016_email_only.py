"""Upgrade a real Round 3 database to email-only notification storage."""

import pytest

from alembic import command
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch, table_columns

pytestmark = pytest.mark.integration


def test_round3_drops_channels_and_suppresses_legacy_sms_without_losing_email(empty_db: str) -> None:
    cfg = alembic_config(empty_db)
    command.upgrade(cfg, "0014")
    execute(
        empty_db,
        *rows.REF_HR,
        rows.order_sql(1),
        "UPDATE ref.customer SET preferred_channel = 'sms_sim' WHERE id = 1",
        "INSERT INTO ops.notification (order_id, template, channel, recipient, body, status, dedupe_key) "
        "VALUES (1, 'CONFIRMED', 'sms_sim', 'sms-simulator', 'legacy', 'queued', 'queued-sms'), "
        "(1, 'DELAY', 'sms_sim', 'sms-simulator', 'legacy', 'draft', 'draft-sms'), "
        "(1, 'DELIVERED', 'sms_sim', 'sms-simulator', 'history', 'sent', 'sent-sms'), "
        "(1, 'CONFIRMED', 'email', 'demo@example.test', 'email', 'queued', 'queued-email')",
    )
    command.upgrade(cfg, "0015")
    command.upgrade(cfg, "0016")
    assert "preferred_channel" not in table_columns(empty_db, "ref")["ref.customer"]
    assert "channel" not in table_columns(empty_db, "ops")["ops.notification"]
    assert [
        tuple(row)
        for row in fetch(
            empty_db,
            "SELECT recipient, status::text, suppressed_reason FROM ops.notification ORDER BY id",
        )
    ] == [
        (None, "suppressed", "legacy_sms"),
        (None, "suppressed", "legacy_sms"),
        (None, "sent", None),
        ("demo@example.test", "queued", None),
    ]
    command.downgrade(cfg, "0015")
    assert fetch(empty_db, "SELECT preferred_channel::text FROM ref.customer WHERE id = 1")[0][0] == "email"
    assert fetch(
        empty_db, "SELECT status::text, channel::text FROM ops.notification WHERE dedupe_key = 'queued-sms'"
    )[0][:] == ("suppressed", "email")
