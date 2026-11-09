"""Real PostgreSQL tests for manager-attributed, non-destructive driver shifts."""

import secrets
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.seed.driver_shifts import seed_driver_shifts
from app.seed.scenarios import generate
from app.seed.workforce import seed_workforce
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)


def prepare(dsn: str) -> None:
    command.upgrade(alembic_config(dsn), "head")
    transact(dsn, lambda s: seed_workforce(s, secrets.token_urlsafe(24)))


def test_US_WH_06_AC1_demo_driver_shifts_are_audited_and_idempotent(empty_db: str) -> None:
    prepare(empty_db)
    fixture = generate()

    async def seed(session: AsyncSession) -> int:
        return await seed_driver_shifts(session, shifts=fixture["driver_shifts"], now=NOW)

    assert transact(empty_db, seed) == 80
    assert transact(empty_db, seed) == 0
    assert fetch(empty_db, "SELECT count(*) FROM hr.employee_shift_schedule")[0][0] == 80
    assert fetch(empty_db, "SELECT count(*) FROM audit.decision_log WHERE action='SHIFT_CHANGED'")[0][0] == 80
    assert fetch(empty_db, "SELECT count(*) FROM hr.driver_duty_log")[0][0] == 0
    assert fetch(empty_db, "SELECT count(*) FROM hr.attendance")[0][0] == 0
    execute(
        empty_db,
        "UPDATE hr.employee_shift_schedule SET status='cancelled',cancelled_by=assigned_by, "
        "cancelled_at='2026-11-04T09:05:00Z' WHERE id=(SELECT min(id) FROM hr.employee_shift_schedule)",
    )
    assert transact(empty_db, seed) == 0
    assert (
        fetch(
            empty_db,
            "SELECT count(*) FROM hr.employee_shift_schedule WHERE status='cancelled'",
        )[
            0
        ][0]
        == 1
    )


def test_US_WH_06_AC2_demo_driver_roster_refuses_unauthorized_manager(empty_db: str) -> None:
    prepare(empty_db)
    execute(
        empty_db,
        "UPDATE hr.location_manager SET can_approve=false WHERE location_id="
        "(SELECT id FROM ref.location WHERE code='MLM')",
    )
    with pytest.raises(ValueError, match="not assigned"):
        transact(
            empty_db,
            lambda s: seed_driver_shifts(s, shifts=generate()["driver_shifts"], now=NOW),
        )
    assert fetch(empty_db, "SELECT count(*) FROM hr.employee_shift_schedule")[0][0] == 0
    assert fetch(empty_db, "SELECT count(*) FROM audit.decision_log WHERE action='SHIFT_CHANGED'")[0][0] == 0
