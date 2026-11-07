"""Migration 0010: quyết định phân luồng ops.order_routing bất biến (Q14; 06 mục 5.0.2; 05 mục 6).

Regression PostgreSQL thật: không đổi route/reason_code/unmapped_skus/decided_*/khóa, không DELETE; vẫn cho
ghi riêng trường xác nhận bàn giao đúng một lần (cả hai trường cùng lúc); downgrade/upgrade sạch.
"""

from collections.abc import Iterator

import asyncpg
import pytest

from alembic import command
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch, rejects

pytestmark = pytest.mark.integration


def routing(ref: str, route: str = "legacy", reason: str = "unmapped_sku") -> str:
    return (
        "INSERT INTO ops.order_routing (market_id, external_ref, route, reason_code, unmapped_skus, "
        f"decided_at, decided_source_version) VALUES (1, '{ref}', '{route}', '{reason}', '{{SE-NEW-77}}', "
        "'2026-11-07T10:00Z', 1)"
    )


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(empty_db, *rows.REF_HR, routing("POS-1"), routing("POS-2", "cfo", "all_confirmed"))
    yield empty_db


def immutable(db: str, statement: str) -> None:
    err = rejects(db, asyncpg.IntegrityConstraintViolationError, None, statement)
    assert "immutable" in str(err) or "write-once" in str(err)


@pytest.mark.parametrize(
    "assignment",
    [
        "route = 'cfo', reason_code = 'all_confirmed'",  # đổi luồng legacy → cfo (dù hợp lệ theo CHECK)
        "reason_code = 'manual_started'",  # đổi lý do trong cùng luồng
        "unmapped_skus = '{}'",
        "decided_at = '2026-11-07T11:00Z'",
        "decided_source_version = 2",
        "decided_by_user_id = 1",
        "external_ref = 'POS-9'",
        "created_at = now() - interval '1 day'",
    ],
)
def test_decision_fields_cannot_change(db: str, assignment: str) -> None:
    immutable(db, f"UPDATE ops.order_routing SET {assignment} WHERE external_ref = 'POS-1'")
    row = fetch(
        db, "SELECT route, reason_code, unmapped_skus FROM ops.order_routing WHERE external_ref = 'POS-1'"
    )
    assert (row[0]["route"], row[0]["reason_code"], row[0]["unmapped_skus"]) == (
        "legacy",
        "unmapped_sku",
        ["SE-NEW-77"],
    )


def test_cfo_decision_cannot_be_flipped_to_legacy(db: str) -> None:
    immutable(
        db,
        "UPDATE ops.order_routing SET route = 'legacy', reason_code = 'manual_started' "
        "WHERE external_ref = 'POS-2'",
    )


def test_decision_cannot_be_deleted_and_rewritten(db: str) -> None:
    immutable(db, "DELETE FROM ops.order_routing WHERE external_ref = 'POS-1'")
    assert fetch(db, "SELECT count(*) AS n FROM ops.order_routing")[0]["n"] == 2


def test_acknowledgement_can_be_recorded_once(db: str) -> None:
    execute(
        db,
        "UPDATE ops.order_routing SET acknowledged_by_user_id = 1, acknowledged_at = '2026-11-07T10:05Z' "
        "WHERE external_ref = 'POS-1'",
    )
    row = fetch(
        db, "SELECT acknowledged_by_user_id, route FROM ops.order_routing WHERE external_ref = 'POS-1'"
    )[0]
    assert (row["acknowledged_by_user_id"], row["route"]) == (1, "legacy")
    immutable(
        db, "UPDATE ops.order_routing SET acknowledged_at = '2026-11-07T11:00Z' WHERE external_ref = 'POS-1'"
    )
    immutable(
        db,
        "UPDATE ops.order_routing SET acknowledged_by_user_id = NULL, acknowledged_at = NULL "
        "WHERE external_ref = 'POS-1'",
    )


def test_acknowledgement_fields_go_together(db: str) -> None:
    rejects(
        db,
        asyncpg.CheckViolationError,
        "ck_routing_ack",
        "UPDATE ops.order_routing SET acknowledged_at = now() WHERE external_ref = 'POS-1'",
    )
    rejects(
        db,
        asyncpg.CheckViolationError,
        "ck_routing_ack",
        "UPDATE ops.order_routing SET acknowledged_by_user_id = 1 WHERE external_ref = 'POS-1'",
    )


def test_ack_update_cannot_smuggle_a_decision_change(db: str) -> None:
    immutable(
        db,
        "UPDATE ops.order_routing SET acknowledged_by_user_id = 1, acknowledged_at = now(), route = 'cfo', "
        "reason_code = 'all_confirmed' WHERE external_ref = 'POS-1'",
    )
    assert (
        fetch(db, "SELECT acknowledged_at FROM ops.order_routing WHERE external_ref = 'POS-1'")[0][
            "acknowledged_at"
        ]
        is None
    )


def test_0010_downgrade_removes_guard_and_upgrade_restores_it(db: str) -> None:
    cfg = alembic_config(db)
    command.downgrade(cfg, "0009")
    execute(db, "UPDATE ops.order_routing SET decided_source_version = 2 WHERE external_ref = 'POS-1'")
    assert fetch(db, "SELECT to_regproc('ops.guard_order_routing') AS f")[0]["f"] is None
    command.upgrade(cfg, "head")
    immutable(db, "UPDATE ops.order_routing SET decided_source_version = 3 WHERE external_ref = 'POS-1'")
