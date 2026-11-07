"""Migration 0006_plan, 0007 (trigger/view/chỉ mục), 0008 (seed tham chiếu) trên PostgreSQL trống."""

import json
from collections.abc import Iterator
from decimal import Decimal

import asyncpg
import pytest

from alembic import command
from app.core.config import MarketConfig
from app.domain.transitions import ALLOWED
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch, rejects, table_columns
from tests.integration.spec05 import COMMON_COLUMNS, spec_tables, spec_tables_in

pytestmark = pytest.mark.integration

UNIQUE = asyncpg.UniqueViolationError
CHECK = asyncpg.CheckViolationError
EXCL = asyncpg.ExclusionViolationError
ALL_SCHEMAS = ("ref", "hr", "stg", "ops", "plan", "audit")


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    yield empty_db


@pytest.fixture
def seeded(db: str) -> str:
    execute(db, *rows.REF_HR, rows.order_sql(1), rows.order_sql(2))
    return db


def _raises_append_only(dsn: str, statement: str) -> None:
    caught = rejects(dsn, asyncpg.RaiseError, None, statement)
    assert "append-only table" in str(caught)


# --- cấu trúc ----------------------------------------------------------------------------------------


def test_head_has_all_60_cfo_tables_matching_spec(db: str) -> None:
    actual = table_columns(db, *ALL_SCHEMAS)
    spec = spec_tables()
    assert len(spec) == 60 and set(actual) == set(spec)  # 57 + 3 bảng 0009
    for table, columns in spec_tables_in("plan", "audit").items():
        assert set(actual[table]) == columns | COMMON_COLUMNS, table
    # v1.2: fulfilment_plan không còn vehicle_id/driver_employee_id
    assert not {"vehicle_id", "driver_employee_id"} & set(actual["plan.fulfilment_plan"])
    assert not any("equipment" in t for t in actual)


def test_required_indexes_and_views_exist(db: str) -> None:
    names = {r["indexname"] for r in fetch(db, "SELECT indexname FROM pg_indexes")}
    expected = {
        "ux_one_approved_plan", "ux_stock_res", "ux_prep_res", "ix_decision_order", "ix_decision_action",
        "ix_order_status_delivered", "ix_order_store_status", "ix_order_status_committed",
        "ix_order_market_status", "ix_order_line_order", "ix_event_order_occurred", "ix_eta_order_version",
        "ix_notification_status_scheduled", "ix_alert_market_resolved", "ix_position_trip_recorded",
        "ix_inbound_atp", "ix_attendance_date_status", "ix_assignment_active_location",
        "ix_plan_order_status", "ix_vehicle_res_active",
    }  # fmt: skip
    assert expected <= names
    views = {r["v"] for r in fetch(db, "SELECT schemaname || '.' || viewname AS v FROM pg_views")}
    assert {"ref.v_product_local", "audit.v_revenue_daily", "audit.v_revenue_pending"} <= views


# --- ASM-001: trigger set_updated_at ----------------------------------------------------------------


def test_ASM_001_set_updated_at_attached_to_every_table(db: str) -> None:
    sql = """
    SELECT n.nspname || '.' || c.relname AS t FROM pg_trigger g
    JOIN pg_class c ON c.oid = g.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE g.tgname = 'trg_set_updated_at' AND NOT g.tgisinternal
    """
    assert {r["t"] for r in fetch(db, sql)} == set(spec_tables())


def test_ASM_001_update_bumps_updated_at_and_keeps_created_at(seeded: str) -> None:
    before = fetch(seeded, "SELECT created_at, updated_at FROM ref.location WHERE id = 1")[0]
    # client cố ghi updated_at cũ: trigger vẫn đặt thời điểm cập nhật thật
    execute(seeded, "UPDATE ref.location SET name = 'Renamed', updated_at = '2000-01-01Z' WHERE id = 1")
    after = fetch(seeded, "SELECT created_at, updated_at FROM ref.location WHERE id = 1")[0]
    assert after["created_at"] == before["created_at"]
    assert after["updated_at"] > before["updated_at"]


# --- US-LOG-01 AC2: chỉ thêm ------------------------------------------------------------------------


def test_US_LOG_01_AC2_decision_log_rejects_update_and_delete(seeded: str) -> None:
    execute(
        seeded,
        "INSERT INTO audit.decision_log (correlation_id, action, entity) "
        "VALUES ('6c0f6c0f-0000-4000-8000-000000000001', 'PLAN_PROPOSED', 'order')",
    )
    _raises_append_only(seeded, "UPDATE audit.decision_log SET reason_text = 'fix'")
    _raises_append_only(seeded, "DELETE FROM audit.decision_log")
    assert len(fetch(seeded, "SELECT 1 FROM audit.decision_log")) == 1


def test_US_LOG_01_AC2_milestone_event_rejects_update_and_delete(seeded: str) -> None:
    execute(seeded, rows.event_sql(1, "START_PREP", "k1"))
    _raises_append_only(seeded, "UPDATE ops.milestone_event SET occurred_at = now()")
    _raises_append_only(seeded, "DELETE FROM ops.milestone_event")
    assert len(fetch(seeded, "SELECT 1 FROM ops.milestone_event")) == 1


# --- trigger chuyển trạng thái + seed order_transition ----------------------------------------------


def test_order_transition_seed_matches_domain_table(db: str) -> None:
    seeded_rows = {
        (r["from_status"], r["to_status"]): (r["requires_reason"], tuple(r["allowed_roles"]))
        for r in fetch(
            db, "SELECT from_status, to_status, requires_reason, allowed_roles FROM ops.order_transition"
        )
    }
    expected = {
        (src.value, dst.value): (reason, () if roles == ("system",) else roles)
        for (src, dst), (reason, roles) in ALLOWED.items()
    }
    assert seeded_rows == expected
    statuses = {s for pair in seeded_rows for s in pair}
    assert not {"MANUAL_PLANNING", "HANDLED_EXTERNALLY"} & statuses


def test_check_transition_trigger_rejects_illegal_status_change(seeded: str) -> None:
    caught = rejects(seeded, asyncpg.RaiseError, None, "UPDATE ops.customer_order SET status = 'DELIVERED'")
    assert "illegal order transition SUBMITTED -> DELIVERED" in str(caught)
    execute(seeded, "UPDATE ops.customer_order SET status = 'PLANNED' WHERE id = 1")
    execute(seeded, "UPDATE ops.customer_order SET block_reason = NULL WHERE id = 1")  # không đổi status
    assert fetch(seeded, "SELECT status FROM ops.customer_order WHERE id = 1")[0]["status"] == "PLANNED"


# --- plan -------------------------------------------------------------------------------------------


def test_v12_planning_run_kind_and_result(seeded: str) -> None:
    execute(seeded, rows.run_sql(1, 1), rows.run_sql(1, 2, kind="replan_suggestion"))
    rejects(seeded, CHECK, "planning_run_kind_check", rows.run_sql(1, 3, kind="auto"))
    rejects(seeded, CHECK, "planning_run_result_check", rows.run_sql(1, 3, result="manual"))


def test_one_approved_or_manual_plan_per_order(seeded: str) -> None:
    execute(
        seeded, rows.run_sql(1, 1), rows.plan_sql(1, 1, 1, "approved"), rows.plan_sql(1, 1, 2, "proposed")
    )
    rejects(
        seeded,
        UNIQUE,
        "ux_one_approved_plan",
        "UPDATE plan.fulfilment_plan SET status = 'approved' WHERE id = 2",
    )
    # đóng kế hoạch cũ (superseded) thì duyệt được kế hoạch mới
    execute(
        seeded,
        "UPDATE plan.fulfilment_plan SET status = 'superseded' WHERE id = 1",
        "UPDATE plan.fulfilment_plan SET status = 'approved' WHERE id = 2",
    )
    rejects(seeded, CHECK, "ck_manual", rows.plan_sql(1, 1, 3, "manual"))
    rejects(seeded, UNIQUE, "ux_one_approved_plan", rows.plan_sql(1, 1, 3, "manual", manual="other"))


def test_v12_plan_with_several_vehicles(seeded: str) -> None:
    execute(
        seeded,
        rows.run_sql(1, 1),
        rows.plan_sql(1, 1, 1),
        rows.plan_vehicle_sql(1, 1, 1, driver_id=1),
        rows.plan_vehicle_sql(1, 2, 2, driver_id=2),
    )
    rejects(seeded, UNIQUE, "plan_vehicle_plan_id_vehicle_id_key", rows.plan_vehicle_sql(1, 3, 1))


def test_vehicle_reservation_exclude_other_orders_only(seeded: str) -> None:
    execute(
        seeded,
        rows.run_sql(1, 1),
        rows.plan_sql(1, 1, 1),
        rows.plan_sql(1, 1, 2),
        rows.plan_vehicle_sql(1, 1, 1),
        rows.plan_vehicle_sql(2, 1, 1),
        rows.run_sql(2, 1),
        rows.plan_sql(2, 2, 1),
        rows.plan_vehicle_sql(3, 1, 1),
        # cùng đơn, 2 phương án dùng cùng xe/tài xế: được phép (09 bất biến 11)
        rows.vehicle_res_sql(1, 1, 1, 1, vehicle_id=1, driver_id=1),
        rows.vehicle_res_sql(1, 2, 2, 1, vehicle_id=1, driver_id=1),
    )
    rejects(seeded, EXCL, "ex_vehicle_res", rows.vehicle_res_sql(2, 3, 3, 2, vehicle_id=1, driver_id=2))
    rejects(seeded, EXCL, "ex_driver_res", rows.vehicle_res_sql(2, 3, 3, 2, vehicle_id=2, driver_id=1))
    # giữ chỗ đã released không chặn đơn khác
    execute(seeded, rows.vehicle_res_sql(2, 3, 3, 2, vehicle_id=1, driver_id=1, status="released"))


def test_stock_reservation_once_per_order_warehouse_product(seeded: str) -> None:
    sql = (
        "INSERT INTO plan.stock_reservation (run_id, order_id, warehouse_id, global_product_id, qty, status) "
        "VALUES (1, {order}, 1, 1, 5, '{status}')"
    )
    execute(
        seeded, rows.run_sql(1, 1), sql.format(order=1, status="held"), sql.format(order=2, status="held")
    )
    rejects(seeded, UNIQUE, "ux_stock_res", sql.format(order=1, status="committed"))
    execute(seeded, sql.format(order=1, status="released"))


# --- view doanh thu ---------------------------------------------------------------------------------


def test_revenue_views_use_market_timezone_and_approved_plan(db: str) -> None:
    execute(db, *rows.REF_HR)  # market id 1 = SE (Europe/Stockholm) từ seed 0008
    execute(
        db,
        rows.order_sql(1),
        rows.order_sql(2),
        rows.run_sql(1, 1),
        rows.plan_sql(1, 1, 1, "approved"),
        rows.run_sql(2, 1),
        rows.plan_sql(2, 2, 1, "approved"),
    )
    # đơn 1 giao 23:30 UTC ngày 10/11 = 00:30 ngày 11/11 giờ Stockholm; đơn 2 đã duyệt chưa giao
    for sql in (
        "UPDATE ops.customer_order SET approved_plan_id = id, total_amount = 1000.50 WHERE id IN (1, 2)",
        "UPDATE ops.customer_order SET committed_date = '2026-11-12' WHERE id = 2",
    ):
        execute(db, sql)
    for status in ("PLANNED", "APPROVED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED"):
        execute(db, f"UPDATE ops.customer_order SET status = '{status}' WHERE id = 1")
    execute(db, "UPDATE ops.customer_order SET status = 'PLANNED' WHERE id = 2")
    execute(db, "UPDATE ops.customer_order SET status = 'APPROVED' WHERE id = 2")
    execute(
        db,
        "UPDATE ops.customer_order SET status = 'DELIVERED', delivered_at = '2026-11-10T23:30Z' WHERE id = 1",
    )
    daily = fetch(db, "SELECT day::text, orders_delivered, revenue_recognised FROM audit.v_revenue_daily")
    assert [tuple(r) for r in daily] == [("2026-11-11", 1, Decimal("1000.50"))]
    pending = fetch(db, "SELECT day::text, orders_pending, revenue_booked FROM audit.v_revenue_pending")
    assert [tuple(r) for r in pending] == [("2026-11-12", 1, Decimal("1000.50"))]


# --- seed tham chiếu 0008 ---------------------------------------------------------------------------


def test_seed_market_se_with_default_market_config(db: str) -> None:
    (market,) = fetch(
        db, "SELECT code, timezone, currency, locale, gps_enabled, shadow_mode, config FROM ref.market"
    )
    assert (market["code"], market["timezone"], market["currency"], market["locale"]) == (
        "SE",
        "Europe/Stockholm",
        "SEK",
        "en",
    )
    assert market["gps_enabled"] is False and market["shadow_mode"] is False  # ASM-002
    assert MarketConfig.model_validate(json.loads(market["config"])) == MarketConfig.model_validate({})


def test_seed_handling_groups_and_flags(db: str) -> None:
    groups = {
        r["code"]: r
        for r in fetch(
            db,
            "SELECT code, name, prep_unit::text AS unit, fixed_hours, labour_hours_per_unit AS per_unit, "
            "vehicle_requirement FROM ref.handling_group",
        )
    }
    assert sorted(groups) == ["N1", "N2", "N3", "N4", "N5", "N6"]
    assert groups["N3"]["unit"] == "pallet" and groups["N3"]["per_unit"] == Decimal("0.150")
    assert groups["N4"]["vehicle_requirement"] == ["dump"]
    assert groups["N6"]["name"] == "Large & fragile items"
    flags = {r["code"]: r["multiplier"] for r in fetch(db, "SELECT code, multiplier FROM ref.special_flag")}
    assert flags == {
        "FRAGILE": Decimal("1.25"),
        "SPECIAL_STORAGE": Decimal("1.15"),
        "HAZARDOUS": Decimal("1.30"),
        "FAR_OR_OUTDOOR": Decimal("1.20"),
    }


def test_seed_positions_roles_and_kpi_scopes(db: str) -> None:
    pos = {
        r["code"]: (list(r["default_roles"]), list(r["default_kpi_scopes"]))
        for r in fetch(
            db, "SELECT code, default_roles::text[] AS default_roles, default_kpi_scopes FROM hr.position"
        )
    }
    assert len(pos) == 14
    assert pos["BUSINESS_OWNER"] == (["viewer"], ["revenue_all"])
    assert pos["PROJECT_LEAD"] == (["viewer"], ["ops"])
    assert pos["IT_INTEGRATION"] == (["admin"], [])
    for code in ("DISPATCHER", "WAREHOUSE_MANAGER", "WAREHOUSE_DEPUTY"):
        assert pos[code][1] == ["ops"], code
    # công nhân kho không có tài khoản → không có vai trò mặc định (09 bất biến 18)
    assert pos["WAREHOUSE_OPERATOR"][0] == [] and pos["FORKLIFT_OPERATOR"][0] == []
    assert fetch(db, "SELECT 1 FROM ref.app_user") == []  # không seed tài khoản/mật khẩu


def test_migration_head_downgrade_to_base_and_back(db: str) -> None:
    cfg = alembic_config(db)
    command.downgrade(cfg, "base")
    assert table_columns(db, *ALL_SCHEMAS) == {}
    assert fetch(db, "SELECT 1 FROM pg_proc WHERE proname IN ('set_updated_at','forbid_mutation')") == []
    command.upgrade(cfg, "head")
    assert len(table_columns(db, *ALL_SCHEMAS)) == 60
