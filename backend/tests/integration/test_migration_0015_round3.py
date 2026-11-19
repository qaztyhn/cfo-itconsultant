"""Round 3 schema migration on real PostgreSQL (DEC-R3, docs/05 §13)."""

import asyncio

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.domain.models.hr import Employee
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch, rejects, table_columns

pytestmark = pytest.mark.integration


def _revision(dsn: str) -> str:
    return fetch(dsn, "SELECT version_num FROM alembic_version")[0]["version_num"]


def _read_seed_employee_via_model(dsn: str) -> str:
    async def read() -> str:
        engine = create_async_engine(async_url(dsn))
        try:
            async with async_sessionmaker(engine)() as session:
                employee = await session.get(Employee, 1)
                assert employee is not None
                return employee.employee_no
        finally:
            await engine.dispose()

    return asyncio.run(read())


@pytest.mark.parametrize("seeded", [False, True])
def test_round3_upgrade_downgrade_upgrade_preserves_prior_data(empty_db: str, seeded: bool) -> None:
    cfg = alembic_config(empty_db)
    command.upgrade(cfg, "0014")
    if seeded:
        execute(empty_db, *rows.REF_HR, rows.order_sql(1))
    command.upgrade(cfg, "0015")
    assert _revision(empty_db) == "0015"
    assert len(table_columns(empty_db, "hr")) >= 3
    if seeded:
        assert fetch(empty_db, "SELECT order_no FROM ops.customer_order WHERE id = 1")[0][0] == "ZZ-000001"
        assert _read_seed_employee_via_model(empty_db) == "E1"
    command.downgrade(cfg, "0014")
    assert _revision(empty_db) == "0014"
    command.upgrade(cfg, "0015")
    assert _revision(empty_db) == "0015"
    if seeded:
        assert fetch(empty_db, "SELECT order_no FROM ops.customer_order WHERE id = 1")[0][0] == "ZZ-000001"
        assert _read_seed_employee_via_model(empty_db) == "E1"


def test_round3_preserves_old_sms_and_rejects_new_sms(empty_db: str) -> None:
    cfg = alembic_config(empty_db)
    command.upgrade(cfg, "0014")
    execute(
        empty_db,
        *rows.REF_HR,
        rows.order_sql(1),
        "INSERT INTO ops.notification (order_id, template, channel, recipient, body, dedupe_key) "
        "VALUES (1, 'CONFIRMED', 'sms_sim', 'demo', 'legacy', 'old-sms')",
    )
    command.upgrade(cfg, "0015")
    old_channel = fetch(empty_db, "SELECT channel::text FROM ops.notification WHERE dedupe_key = 'old-sms'")
    assert old_channel[0][0] == "sms_sim"
    rejects(
        empty_db,
        asyncpg.CheckViolationError,
        "ck_notification_email_only_r3",
        "INSERT INTO ops.notification (order_id, template, channel, recipient, body, dedupe_key) "
        "VALUES (1, 'CONFIRMED', 'sms_sim', 'demo', 'new', 'new-sms')",
    )
    execute(
        empty_db,
        "INSERT INTO ops.notification (order_id, template, channel, recipient, body, dedupe_key) "
        "VALUES (1, 'CONFIRMED', 'email', 'demo@example.test', 'new', 'new-email')",
    )


def test_round3_capacity_and_eligibility_constraints(empty_db: str) -> None:
    command.upgrade(alembic_config(empty_db), "0015")
    execute(
        empty_db,
        *rows.REF_HR,
        "INSERT INTO hr.warehouse_day_capacity "
        "(warehouse_id, work_date, shift_code, start_time, end_time, headcount, "
        "productive_hours, confirmed_by) "
        "VALUES (1, '2026-11-20', 'AM', '06:00', '14:00', 3, 7.50, 1)",
    )
    rejects(
        empty_db,
        asyncpg.UniqueViolationError,
        "ux_wdc_active",
        "INSERT INTO hr.warehouse_day_capacity "
        "(warehouse_id, work_date, shift_code, start_time, end_time, headcount, "
        "productive_hours, confirmed_by) "
        "VALUES (1, '2026-11-20', 'AM', '06:00', '14:00', 4, 7.50, 1)",
    )
    rejects(
        empty_db,
        asyncpg.CheckViolationError,
        None,
        "INSERT INTO hr.driver_vehicle_eligibility "
        "(driver_employee_id, vehicle_id, licence_class, verified_until, verified_by, "
        "verified_at, source, source_ref) "
        "VALUES (1, 1, 'C', '2026-12-01', 'fleet', now(), 'synthetic_demo', 'both')",
    )
    execute(
        empty_db,
        "INSERT INTO hr.driver_vehicle_eligibility "
        "(driver_employee_id, vehicle_id, verified_until, verified_by, verified_at, source, source_ref) "
        "VALUES (1, 1, '2026-12-01', 'fleet', now(), 'synthetic_demo', 'vehicle-only')",
    )
