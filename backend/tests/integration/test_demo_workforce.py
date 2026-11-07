import secrets
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.seed.catalog import seed_catalog
from app.seed.fleet import seed_fleet
from app.seed.workforce import seed_workforce
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration


def test_US_SRC_01_AC1_workforce_and_fleet_preserve_accounts_and_assignments(
    empty_db: str,
) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    password = secrets.token_urlsafe(24)

    async def seed(session: AsyncSession) -> None:
        await seed_workforce(session, password)
        await seed_fleet(session)
        await seed_catalog(session, now=datetime(2026, 11, 4, tzinfo=UTC))

    transact(empty_db, seed)
    users = fetch(empty_db, "SELECT id,password_hash FROM ref.app_user ORDER BY id")
    assert fetch(empty_db, "SELECT count(*) FROM ref.location WHERE type='store'")[0][0] == 25
    assert fetch(empty_db, "SELECT count(*) FROM hr.employee")[0][0] == 163
    assert fetch(empty_db, "SELECT count(*) FROM ref.vehicle")[0][0] == 9
    assert fetch(empty_db, "SELECT capacity_kg FROM ref.vehicle WHERE code='STO-CR-01'")[0][0] == 8000
    assert (
        fetch(
            empty_db,
            "SELECT count(*) FROM hr.driver_staff WHERE licence_expires_on < '2026-11-04'",
        )[
            0
        ][0]
        == 1
    )
    assert (
        fetch(
            empty_db,
            """SELECT u.id FROM ref.app_user u JOIN hr.employee e ON e.id=u.employee_id
        WHERE e.position_code IN ('WAREHOUSE_OPERATOR','FORKLIFT_OPERATOR')""",
        )
        == []
    )
    assert fetch(empty_db, "SELECT count(*) FROM hr.location_manager WHERE level='primary'")[0][0] == 28
    execute(empty_db, "UPDATE ref.app_user SET is_active=false WHERE email='sales@cfo.demo'")
    transact(empty_db, seed)
    assert users == fetch(empty_db, "SELECT id,password_hash FROM ref.app_user ORDER BY id")
    assert not fetch(empty_db, "SELECT is_active FROM ref.app_user WHERE email='sales@cfo.demo'")[0][0]
    assert fetch(empty_db, "SELECT count(*) FROM hr.employee_assignment")[0][0] == 163
    assert fetch(empty_db, "SELECT count(*) FROM ref.product_se")[0][0] == 100
    assert (
        fetch(
            empty_db,
            "SELECT count(*) FROM ref.product_se WHERE mapping_status='pending'",
        )[
            0
        ][0]
        == 3
    )
    assert fetch(empty_db, "SELECT count(*) FROM ref.product_global")[0][0] == 97
