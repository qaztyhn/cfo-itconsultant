import secrets
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.seed.roster import seed_roster
from app.seed.workforce import seed_workforce
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration
START, END = date(2026, 11, 4), date(2026, 11, 5)
NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)


def prepare(dsn: str) -> None:
    command.upgrade(alembic_config(dsn), "head")
    password = secrets.token_urlsafe(24)
    transact(dsn, lambda s: seed_workforce(s, password))


def test_US_WH_06_AC1_demo_roster_is_explicit_repeatable_and_audited(empty_db: str) -> None:
    prepare(empty_db)
    execute(empty_db, "UPDATE hr.shift_template SET expected_staff=1")

    async def seed(session: AsyncSession) -> int:
        return await seed_roster(session, start=START, end=END, now=NOW)

    assert transact(empty_db, seed) == 78  # 13 fixed people x 3 warehouses x 2 weekdays.
    assert transact(empty_db, seed) == 0
    assert fetch(empty_db, "SELECT count(*) FROM audit.decision_log WHERE action='SHIFT_CHANGED'")[0][0] == 78
    assert fetch(empty_db, "SELECT count(*) FROM hr.attendance")[0][0] == 0
    assert fetch(empty_db, "SELECT count(*) FROM hr.driver_duty_log")[0][0] == 0
    assert fetch(empty_db, "SELECT count(*) FROM hr.shift_template WHERE expected_staff=1")[0][0] == 30
    assert (
        fetch(
            empty_db,
            """SELECT count(*) FROM hr.employee_shift_schedule s JOIN hr.location_manager m
        ON m.employee_id=s.assigned_by AND m.location_id=s.warehouse_id WHERE m.can_approve""",
        )[0][0]
        == 78
    )
    assert (
        fetch(
            empty_db,
            "SELECT count(*) FROM audit.decision_log "
            "WHERE actor_role='warehouse' AND reason_text IS NOT NULL",
        )[0][0]
        == 78
    )
    execute(
        empty_db,
        """UPDATE hr.employee_shift_schedule SET status='cancelled',cancelled_at='2026-11-04T09:05Z',
        cancelled_by=assigned_by WHERE id=(SELECT min(id) FROM hr.employee_shift_schedule)""",
    )
    assert transact(empty_db, seed) == 0
    assert (
        fetch(empty_db, "SELECT count(*) FROM hr.employee_shift_schedule WHERE status='cancelled'")[0][0] == 1
    )


def test_US_WH_06_AC2_unauthorized_manager_rolls_back_roster_and_audit(empty_db: str) -> None:
    prepare(empty_db)
    execute(
        empty_db,
        """UPDATE hr.location_manager SET can_approve=false WHERE location_id=
        (SELECT id FROM ref.location WHERE code='MLM')""",
    )
    with pytest.raises(ValueError, match="authorized"):
        transact(empty_db, lambda s: seed_roster(s, start=START, end=END, now=NOW))
    assert fetch(empty_db, "SELECT count(*) FROM hr.employee_shift_schedule")[0][0] == 0
    assert fetch(empty_db, "SELECT count(*) FROM audit.decision_log WHERE action='SHIFT_CHANGED'")[0][0] == 0


def test_US_WH_06_AC1_demo_roster_obeys_market_working_days_and_holidays(empty_db: str) -> None:
    prepare(empty_db)
    execute(
        empty_db,
        "INSERT INTO ref.market_holiday(market_id,holiday_date,name) "
        "SELECT id,'2026-11-05','Synthetic closure' FROM ref.market WHERE code='SE'",
    )
    assert transact(empty_db, lambda s: seed_roster(s, start=START, end=date(2026, 11, 8), now=NOW)) == 78
