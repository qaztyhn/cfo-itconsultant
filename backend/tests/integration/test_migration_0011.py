"""Migration 0011 — DEC-ROUTING-002: quyết định phân luồng chỉ do người kiểm tra (Sales check / Dispatcher).

Regression PostgreSQL: không lưu được quyết định "của hệ thống" (polling) — thiếu người hoặc vai trò
quyết định; vai trò chỉ sales/dispatcher; manual_started bắt buộc lý do không rỗng; người/vai trò/lý do đã ghi
bất biến;
xác nhận bàn giao vẫn ghi riêng được một lần; migration fail closed khi bảng có dữ liệu cũ; downgrade/upgrade.
"""

from collections.abc import Iterator

import asyncpg
import pytest
from sqlalchemy.exc import DBAPIError

from alembic import command
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch, rejects

pytestmark = pytest.mark.integration

COLUMNS = (
    "INSERT INTO ops.order_routing (market_id, external_ref, route, reason_code, decided_at, "
    "decided_source_version, decided_by_user_id, decided_by_role, reason_text) VALUES "
)


def decision(ref: str, route: str = "cfo", reason: str = "all_confirmed", *, user: str = "1",
             role: str = "'sales'", text: str = "NULL") -> str:  # fmt: skip
    return COLUMNS + f"(1, '{ref}', '{route}', '{reason}', now(), 1, {user}, {role}, {text})"


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(empty_db, *rows.REF_HR)
    yield empty_db


def test_sales_check_and_dispatcher_check_can_record_a_decision(db: str) -> None:
    execute(
        db,
        decision("POS-1"),
        decision("POS-2", "legacy", "unmapped_sku", role="'dispatcher'"),
        decision("POS-3", "legacy", "manual_started", text="'Dispatched by phone before the CFO check'"),
    )
    roles = {r["external_ref"]: r["decided_by_role"] for r in fetch(db, "SELECT * FROM ops.order_routing")}
    assert roles == {"POS-1": "sales", "POS-2": "dispatcher", "POS-3": "sales"}


@pytest.mark.parametrize(
    ("statement", "error"),
    [
        (decision("POS-9", user="NULL"), asyncpg.NotNullViolationError),  # polling/hệ thống: không có người
        (decision("POS-9", role="NULL"), asyncpg.NotNullViolationError),
        (decision("POS-9", role="'system'"), asyncpg.CheckViolationError),
        (decision("POS-9", role="'warehouse'"), asyncpg.CheckViolationError),
    ],
)
def test_no_system_or_unauthorised_decisions(
    db: str, statement: str, error: type[asyncpg.PostgresError]
) -> None:
    rejects(db, error, None, statement)


@pytest.mark.parametrize("text", ["NULL", "''", "'   '"])
def test_manual_started_requires_a_reason(db: str, text: str) -> None:
    rejects(
        db,
        asyncpg.CheckViolationError,
        "ck_routing_manual_reason",
        decision("POS-9", "legacy", "manual_started", text=text),
    )


@pytest.mark.parametrize(
    "assignment",
    ["decided_by_role = 'dispatcher'", "reason_text = 'changed later'", "decided_by_user_id = NULL"],
)
def test_who_decided_and_why_cannot_change(db: str, assignment: str) -> None:
    execute(db, decision("POS-1", "legacy", "manual_started", text="'Phone dispatch'"))
    err = rejects(
        db,
        asyncpg.IntegrityConstraintViolationError,
        None,
        f"UPDATE ops.order_routing SET {assignment} WHERE external_ref = 'POS-1'",
    )
    assert "immutable" in str(err)


def test_cfo_decision_is_never_flipped_by_a_manual_report(db: str) -> None:
    """DEC-ROUTING-002: đã có cfo mà Sales báo đã điều phối tay → không đổi luồng; chuyển Dispatcher."""
    execute(db, decision("POS-1"))
    rejects(
        db,
        asyncpg.IntegrityConstraintViolationError,
        None,
        "UPDATE ops.order_routing SET route = 'legacy', reason_code = 'manual_started', "
        "reason_text = 'Sales started by phone' WHERE external_ref = 'POS-1'",
    )
    rejects(db, asyncpg.UniqueViolationError, None, decision("POS-1", "legacy", "manual_started", text="'x'"))
    assert fetch(db, "SELECT route FROM ops.order_routing")[0]["route"] == "cfo"


def test_handoff_acknowledgement_still_writable_once(db: str) -> None:
    execute(
        db,
        decision("POS-2", "legacy", "unmapped_sku"),
        "UPDATE ops.order_routing SET acknowledged_by_user_id = 1, acknowledged_at = now() "
        "WHERE external_ref = 'POS-2'",
    )
    assert (
        fetch(db, "SELECT acknowledged_by_user_id FROM ops.order_routing")[0]["acknowledged_by_user_id"] == 1
    )


def test_0011_fails_closed_on_existing_rows_and_downgrades_cleanly(db: str) -> None:
    cfg = alembic_config(db)
    command.downgrade(cfg, "0010")
    assert fetch(db, "SELECT to_regclass('ops.order_routing') AS r")[0]["r"] is not None
    cols = fetch(
        db,
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'ops' "
        "AND table_name = 'order_routing' AND column_name IN ('decided_by_role', 'reason_text')",
    )
    assert cols == []
    execute(
        db,
        "INSERT INTO ops.order_routing (market_id, external_ref, route, reason_code, decided_at, "
        "decided_source_version) VALUES (1, 'POLL-1', 'cfo', 'all_confirmed', now(), 1)",  # kiểu cũ
    )
    with pytest.raises(DBAPIError, match="must be empty before 0011"):
        command.upgrade(cfg, "head")
    assert fetch(db, "SELECT version_num FROM alembic_version")[0]["version_num"] == "0010"
