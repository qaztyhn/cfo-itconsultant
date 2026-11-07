"""Migration 0001 trên PostgreSQL trống: extension, 6 schema, enum đúng 05 mục 2 (v1.2)."""

from enum import StrEnum

import pytest

from alembic import command
from app.domain import enums
from tests.integration.conftest import alembic_config, fetch

pytestmark = pytest.mark.integration

ENUM_SQL = """
SELECT n.nspname || '.' || t.typname AS name, array_agg(e.enumlabel ORDER BY e.enumsortorder) AS labels
FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid JOIN pg_namespace n ON n.oid = t.typnamespace
GROUP BY 1
"""

# Enum Python (app.domain.enums) phải khớp 1-1 với enum DB tương ứng.
PY_TO_DB: dict[type[StrEnum], str] = {
    enums.UserRole: "ref.user_role",
    enums.PrepUnit: "ref.prep_unit",
    enums.OrderStatus: "ops.order_status",
    enums.DateMode: "ops.date_mode",
    enums.EventType: "ops.event_type",
    enums.RiskStatus: "ops.risk_status",
    enums.RiskColor: "ops.risk_color",
    enums.NotifTemplate: "ops.notif_template",
    enums.NotifStatus: "ops.notif_status",
    enums.TransferStatus: "ops.transfer_status",
    enums.PlanStatus: "plan.plan_status",
    enums.ResStatus: "plan.res_status",
}


def _db_enums(dsn: str) -> dict[str, list[str]]:
    return {r["name"]: list(r["labels"]) for r in fetch(dsn, ENUM_SQL)}


def test_migration_0001_creates_extensions_schemas_enums(empty_db: str) -> None:
    command.upgrade(alembic_config(empty_db), "0001")

    exts = {r["extname"] for r in fetch(empty_db, "SELECT extname FROM pg_extension")}
    assert {"pgcrypto", "btree_gist", "pg_trgm"} <= exts

    schemas = {r["nspname"] for r in fetch(empty_db, "SELECT nspname FROM pg_namespace")}
    assert {"ref", "hr", "stg", "ops", "plan", "audit"} <= schemas

    db = _db_enums(empty_db)
    assert len(db) == 27
    for py_enum, db_name in PY_TO_DB.items():
        assert db[db_name] == [m.value for m in py_enum], db_name


def test_migration_0001_v12_order_status_and_events(empty_db: str) -> None:
    command.upgrade(alembic_config(empty_db), "0001")
    db = _db_enums(empty_db)

    # v1.2: bỏ MANUAL_PLANNING / HANDLED_EXTERNALLY (09 bất biến 10)
    assert "MANUAL_PLANNING" not in db["ops.order_status"]
    assert "HANDLED_EXTERNALLY" not in db["ops.order_status"]
    # v1.2: tạm dừng / tiếp tục chuẩn bị
    assert {"PREP_PAUSED", "PREP_RESUMED"} <= set(db["ops.event_type"])
    # v1.1: không có enum/mã thiết bị kho (09 bất biến 23)
    assert not any("equipment" in name for name in db)


def test_migration_0001_downgrade_to_base_is_clean(empty_db: str) -> None:
    cfg = alembic_config(empty_db)
    command.upgrade(cfg, "0001")
    command.downgrade(cfg, "base")

    assert _db_enums(empty_db) == {}
    schemas = {r["nspname"] for r in fetch(empty_db, "SELECT nspname FROM pg_namespace")}
    assert not ({"ref", "hr", "stg", "ops", "plan", "audit"} & schemas)
    # chạy lại được sau khi gỡ (migration lặp lại được)
    command.upgrade(cfg, "0001")
    assert len(_db_enums(empty_db)) == 27
