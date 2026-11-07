"""Migration 0009: lịch ca, nhật ký làm việc tài xế, phân luồng đơn, phạm vi 561/2006 (Q12/Q12b/Q14).

Ràng buộc DB thật (09 mục 11): 1 ca/người/ngày chỉ với dòng `scheduled`, nguồn giờ ca, cặp giờ/giờ nghỉ,
trạng thái hủy; khoảng làm việc hợp lệ; luồng cfo ⇔ all_confirmed; `unresolved` không lưu được; xe mặc
định `unknown`.
"""

from collections.abc import Iterator

import asyncpg
import pytest

from alembic import command
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch, rejects

pytestmark = pytest.mark.integration

SHIFT_TEMPLATE = (
    "INSERT INTO hr.shift_template (warehouse_id, weekday, start_time, end_time, useful_hours_per_staff, "
    "expected_staff) VALUES (1, 4, '07:00', '15:00', 7, 3)"
)


def schedule(
    emp: int,
    day: str = "2026-11-12",
    *,
    template: str = "1",
    times: str = "NULL, NULL",
    status: str = "'scheduled'",
    cancelled: str = "NULL",
    breaks: str = "NULL, NULL",
) -> str:
    return (
        "INSERT INTO hr.employee_shift_schedule (employee_id, warehouse_id, work_date, shift_template_id, "
        "start_time, end_time, break_start, break_end, status, assigned_by, assigned_at, cancelled_at) "
        f"VALUES ({emp}, 1, '{day}', {template}, {times}, {breaks}, {status}, 1, now(), {cancelled})"
    )


def routing(ref: str, route: str, reason: str) -> str:
    # 0011: quyết định luôn có người/vai trò quyết định; manual_started bắt buộc lý do
    text = "'Dispatched by phone before CFO check'" if reason == "manual_started" else "NULL"
    return (
        "INSERT INTO ops.order_routing (market_id, external_ref, route, reason_code, decided_at, "
        "decided_source_version, decided_by_user_id, decided_by_role, reason_text) VALUES "
        f"(1, '{ref}', '{route}', '{reason}', now(), 1, 1, 'sales', {text})"
    )


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(empty_db, *rows.REF_HR, SHIFT_TEMPLATE)
    yield empty_db


def test_vehicle_driving_rule_scope_defaults_to_unknown(db: str) -> None:
    row = fetch(db, "SELECT regulation_561_scope, max_permissible_mass_kg FROM ref.vehicle WHERE id = 1")[0]
    assert (row["regulation_561_scope"], row["max_permissible_mass_kg"]) == ("unknown", None)
    rejects(db, asyncpg.CheckViolationError, None, "UPDATE ref.vehicle SET regulation_561_scope = 'maybe'")
    execute(db, "UPDATE ref.vehicle SET regulation_561_scope = 'in_scope', max_permissible_mass_kg = 18000")


def test_Q12a_one_scheduled_shift_per_person_per_day(db: str) -> None:
    execute(db, schedule(1))
    rejects(db, asyncpg.UniqueViolationError, "ux_shift_one_per_day", schedule(1, times="'15:00', '22:00'"))
    # dòng đã hủy không chặn dòng mới (đổi ca = hủy + thêm)
    execute(
        db,
        "UPDATE hr.employee_shift_schedule SET status = 'cancelled', cancelled_at = now() WHERE id = 1",
        schedule(1, template="NULL", times="'22:00', '06:00'"),  # ca qua nửa đêm, giờ riêng
    )
    assert fetch(db, "SELECT count(*) AS n FROM hr.employee_shift_schedule")[0]["n"] == 2


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        (schedule(1, template="NULL"), "ck_shift_source"),
        (schedule(1, times="'07:00', NULL"), "ck_shift_times"),
        (schedule(1, breaks="'11:00', NULL"), "ck_shift_break"),
        (schedule(1, status="'cancelled'"), "ck_shift_cancelled"),
        (schedule(1, cancelled="now()"), "ck_shift_cancelled"),
    ],
)
def test_shift_schedule_checks(db: str, statement: str, constraint: str) -> None:
    rejects(db, asyncpg.CheckViolationError, constraint, statement)


def test_driver_duty_log_interval(db: str) -> None:
    ok = (
        "INSERT INTO hr.driver_duty_log (employee_id, duty_start, duty_end, driving_min, source) "
        "VALUES (1, '2026-11-11T14:00Z', '2026-11-11T22:30Z', 240, 'trip')"
    )
    execute(db, ok)
    rejects(db, asyncpg.CheckViolationError, "ck_duty_interval", ok.replace("22:30Z", "13:00Z"))
    rejects(db, asyncpg.CheckViolationError, None, ok.replace("240", "-1"))
    rejects(db, asyncpg.CheckViolationError, None, ok.replace("'trip'", "'guess'"))


def test_Q14_routing_is_one_decision_per_source_order(db: str) -> None:
    execute(db, routing("POS-1", "cfo", "all_confirmed"), routing("POS-2", "legacy", "unmapped_sku"))
    execute(db, routing("POS-3", "legacy", "manual_started"))
    rejects(db, asyncpg.UniqueViolationError, None, routing("POS-1", "legacy", "unmapped_sku"))
    rejects(
        db, asyncpg.CheckViolationError, None, routing("POS-4", "unresolved", "all_confirmed")
    )  # không lưu
    rejects(db, asyncpg.CheckViolationError, "ck_routing_reason", routing("POS-5", "cfo", "unmapped_sku"))
    rejects(db, asyncpg.CheckViolationError, "ck_routing_reason", routing("POS-6", "legacy", "all_confirmed"))


def test_new_tables_maintain_updated_at(db: str) -> None:
    execute(db, routing("POS-1", "cfo", "all_confirmed"))
    before = fetch(db, "SELECT updated_at FROM ops.order_routing")[0]["updated_at"]
    execute(
        db,
        "UPDATE ops.order_routing SET acknowledged_by_user_id = 1, "
        "acknowledged_at = now() + interval '1 second'",
    )
    assert fetch(db, "SELECT updated_at FROM ops.order_routing")[0]["updated_at"] >= before
    triggers = fetch(
        db,
        "SELECT event_object_schema || '.' || event_object_table AS t FROM information_schema.triggers "
        "WHERE trigger_name = 'trg_set_updated_at' AND event_object_table IN "
        "('employee_shift_schedule', 'driver_duty_log', 'order_routing')",
    )
    assert {r["t"] for r in triggers} == {
        "hr.employee_shift_schedule",
        "hr.driver_duty_log",
        "ops.order_routing",
    }


def test_0009_downgrades_cleanly(db: str) -> None:
    cfg = alembic_config(db)
    command.downgrade(cfg, "0008")
    tables = fetch(
        db, "SELECT to_regclass('ops.order_routing') AS r, to_regclass('hr.driver_duty_log') AS d"
    )[0]
    assert tables["r"] is None and tables["d"] is None
    cols = fetch(
        db,
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'ref' "
        "AND table_name = 'vehicle' AND column_name IN ('regulation_561_scope', 'max_permissible_mass_kg')",
    )
    assert cols == []
    command.upgrade(cfg, "head")
