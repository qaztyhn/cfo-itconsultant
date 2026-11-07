"""Migration 0004_stg + 0005_ops trên PostgreSQL trống: cột khớp 05, ASM-001, ràng buộc v1.1/v1.2."""

from collections.abc import Iterator

import asyncpg
import pytest

from alembic import command
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch, rejects, table_columns
from tests.integration.spec05 import COMMON_COLUMNS, spec_tables_in

pytestmark = pytest.mark.integration

UNIQUE = asyncpg.UniqueViolationError
CHECK = asyncpg.CheckViolationError


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "0005")
    yield empty_db


@pytest.fixture
def seeded(db: str) -> str:
    execute(db, *rows.REF_HR, rows.order_sql(1), rows.order_sql(2))
    return db


def test_migration_0004_0005_tables_and_columns_match_spec(db: str) -> None:
    spec = spec_tables_in("stg", "ops")
    actual = table_columns(db, "stg", "ops")
    assert len(spec) == 21 and set(actual) == set(spec)
    for table, columns in spec.items():
        assert set(actual[table]) == columns | COMMON_COLUMNS, table


def test_ASM_001_common_columns_stg_ops(db: str) -> None:
    for table, cols in table_columns(db, "stg", "ops").items():
        for name in COMMON_COLUMNS:
            assert cols[name]["data_type"] == "timestamp with time zone", (table, name)
            assert cols[name]["is_nullable"] == "NO", (table, name)
            assert cols[name]["column_default"] == "now()", (table, name)


def test_ASM_001_business_timestamps_kept_separate(db: str) -> None:
    """Mốc nghiệp vụ không bị thay bằng created_at (ASM-001)."""
    cols = table_columns(db, "ops")
    assert {"occurred_at", "received_at", "created_at"} <= set(cols["ops.milestone_event"])
    assert {"completed_at", "created_at"} <= set(cols["ops.proof_of_delivery"])
    assert {"computed_at", "created_at"} <= set(cols["ops.eta_forecast"])
    assert {"contacted_at", "created_at"} <= set(cols["ops.customer_contact_log"])
    assert set(cols["ops.idempotency_key"]) >= {"created_at", "updated_at"}


def test_order_status_has_no_removed_v12_values(seeded: str) -> None:
    rejects(
        seeded,
        asyncpg.InvalidTextRepresentationError,
        None,
        "UPDATE ops.customer_order SET status = 'MANUAL_PLANNING' WHERE id = 1",
    )


def test_customer_order_date_mode_checks(seeded: str) -> None:
    execute(
        seeded,
        rows.order_sql(10, date_mode="range", date_from="2026-11-10", date_to="2026-11-12"),
        rows.order_sql(11, date_mode="latest", date_from=None, date_to="2026-11-18"),
    )
    rejects(seeded, CHECK, "ck_dates", rows.order_sql(12, date_mode="exact", date_to="2026-11-11"))
    rejects(seeded, CHECK, "ck_dates", rows.order_sql(13, date_mode="range", date_to="2026-11-10"))
    rejects(seeded, CHECK, "ck_dates", rows.order_sql(14, date_mode="latest"))
    rejects(seeded, CHECK, "ck_window", rows.order_sql(15, window=("12:00", "08:00")))


def test_v12_one_order_on_several_trips_allowed(seeded: str) -> None:
    """v1.2: bỏ ux_stop_active_order — một đơn nhiều xe có nhiều trip_stop pending."""
    execute(seeded, rows.trip_sql(1), rows.trip_sql(2), rows.stop_sql(1, 1), rows.stop_sql(2, 1))
    assert len(fetch(seeded, "SELECT 1 FROM ops.trip_stop WHERE order_id = 1 AND status = 'pending'")) == 2
    rejects(seeded, UNIQUE, "trip_stop_trip_id_order_id_key", rows.stop_sql(1, 1, seq=2))
    rejects(seeded, UNIQUE, "trip_stop_trip_id_seq_key", rows.stop_sql(1, 2))


def test_US_EXE_04_AC3_failed_then_delivered_two_pods_per_trip_stop(seeded: str) -> None:
    """POD theo từng lần giao (trip_stop_id), không theo đơn (09 bất biến 22)."""
    execute(seeded, rows.trip_sql(1), rows.trip_sql(2), rows.stop_sql(1, 1), rows.stop_sql(2, 1))
    execute(seeded, rows.pod_sql(1, 1, "failed", "customer_absent"), rows.pod_sql(2, 1, "delivered"))
    assert [r["result"] for r in fetch(seeded, "SELECT result FROM ops.proof_of_delivery ORDER BY id")] == [
        "failed",
        "delivered",
    ]
    # một lần giao chỉ có một POD
    rejects(seeded, UNIQUE, "proof_of_delivery_trip_stop_id_key", rows.pod_sql(1, 1, "delivered"))
    # một đơn chỉ được giao thành công một lần
    execute(seeded, rows.trip_sql(1), rows.stop_sql(3, 1))
    rejects(seeded, UNIQUE, "ux_pod_one_delivered", rows.pod_sql(3, 1, "delivered"))


def test_pod_failure_reason_required_iff_failed(seeded: str) -> None:
    execute(seeded, rows.trip_sql(1), rows.stop_sql(1, 1))
    rejects(seeded, CHECK, "proof_of_delivery_check", rows.pod_sql(1, 1, "failed"))
    rejects(seeded, CHECK, "proof_of_delivery_check", rows.pod_sql(1, 1, "delivered", "refused"))
    rejects(seeded, CHECK, "proof_of_delivery_failure_reason_check", rows.pod_sql(1, 1, "failed", "rain"))


def test_milestone_event_v12_prep_pause_resume_and_idempotency(seeded: str) -> None:
    execute(
        seeded,
        rows.event_sql(1, "START_PREP", "k1"),
        rows.event_sql(1, "PREP_PAUSED", "k2"),
        rows.event_sql(1, "PREP_RESUMED", "k3"),
    )
    rejects(seeded, UNIQUE, "milestone_event_idempotency_key_key", rows.event_sql(1, "GOODS_READY", "k1"))


def test_US_RSK_03_AC3_alert_dedupe_only_while_open(seeded: str) -> None:
    execute(seeded, rows.alert_sql("order:1:RISK_ORANGE"))
    rejects(seeded, UNIQUE, "ux_alert_open_dedupe", rows.alert_sql("order:1:RISK_ORANGE"))
    execute(
        seeded,
        "UPDATE ops.alert SET resolved_at = '2026-11-10T10:00Z' WHERE dedupe_key = 'order:1:RISK_ORANGE'",
        rows.alert_sql("order:1:RISK_ORANGE"),
    )
    assert len(fetch(seeded, "SELECT 1 FROM ops.alert")) == 2


def test_notification_dedupe_key_unique(seeded: str) -> None:
    sql = (
        "INSERT INTO ops.notification (order_id, template, channel, recipient, body, plan_id, dedupe_key) "
        "VALUES (1, 'CONFIRMED', 'email', 'r@cfo.test', 'Body', {plan}, '1:CONFIRMED:{plan}:queued')"
    )
    execute(seeded, sql.format(plan=7), sql.format(plan=8))  # lập lại kế hoạch → CONFIRMED mới
    rejects(seeded, UNIQUE, "notification_dedupe_key_key", sql.format(plan=7))


def test_sync_file_dedupe_only_for_successful_runs(seeded: str) -> None:
    sql = (
        "INSERT INTO stg.sync_run (market_id, entity, kind, file_sha256, status) "
        "VALUES (1, 'orders', 'csv', 'abc', '{status}')"
    )
    execute(seeded, sql.format(status="failed"), sql.format(status="ok"))
    rejects(seeded, UNIQUE, "ux_sync_file", sql.format(status="partial"))


def test_order_transition_roles_use_user_role_enum(seeded: str) -> None:
    execute(
        seeded,
        "INSERT INTO ops.order_transition (from_status, to_status, allowed_roles) "
        "VALUES ('SUBMITTED', 'PLANNED', '{}')",
    )
    rejects(
        seeded,
        asyncpg.InvalidTextRepresentationError,
        None,
        "INSERT INTO ops.order_transition (from_status, to_status, allowed_roles) "
        "VALUES ('PLANNED', 'APPROVED', '{system}')",
    )


def test_migration_0005_downgrade_to_0003_is_clean(db: str) -> None:
    command.downgrade(alembic_config(db), "0003")
    assert table_columns(db, "stg", "ops") == {}
    command.upgrade(alembic_config(db), "0005")
    assert len(table_columns(db, "stg", "ops")) == 21
