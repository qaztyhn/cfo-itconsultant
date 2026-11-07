"""M0 account bootstrap: real PostgreSQL, repeatability and preservation of existing users."""

import asyncio
import secrets

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.core.db import to_async_url
from app.core.security import verify_password
from app.seed.m0_accounts import seed_accounts
from tests.integration.conftest import alembic_config, execute, fetch

pytestmark = pytest.mark.integration


def seed(dsn: str, password: str) -> None:
    async def go() -> None:
        engine = create_async_engine(to_async_url(dsn), hide_parameters=True)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                await seed_accounts(session, password)
        finally:
            await engine.dispose()

    asyncio.run(go())


def test_US_EMP_03_AC1_m0_accounts_match_positions_and_repeat_safely(
    empty_db: str,
) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    password = secrets.token_urlsafe(24)
    seed(empty_db, password)
    before = fetch(empty_db, "SELECT id, password_hash FROM ref.app_user ORDER BY id")
    assert len(before) == 5
    assert all(verify_password(password, r["password_hash"]) for r in before)
    assert (
        fetch(
            empty_db,
            """SELECT u.id FROM ref.app_user u JOIN hr.employee e ON e.id=u.employee_id
        JOIN hr.position p ON p.code=e.position_code
        WHERE u.roles <> p.default_roles OR u.kpi_scopes <> p.default_kpi_scopes""",
        )
        == []
    )
    assert len(fetch(empty_db, "SELECT id FROM hr.employee_assignment WHERE end_date IS NULL")) == 5
    execute(
        empty_db,
        "UPDATE ref.app_user SET is_active=false WHERE email='dispatcher@cfo.demo'",
    )
    seed(empty_db, secrets.token_urlsafe(24))
    assert fetch(empty_db, "SELECT id, password_hash FROM ref.app_user ORDER BY id") == before
    assert not fetch(empty_db, "SELECT is_active FROM ref.app_user WHERE email='dispatcher@cfo.demo'")[0][0]
    assert len(fetch(empty_db, "SELECT id FROM hr.employee_assignment")) == 5


def test_m0_seed_requires_password_before_writing(empty_db: str) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    with pytest.raises(ValueError, match="SEED_DEMO_PASSWORD"):
        seed(empty_db, "")
    assert fetch(empty_db, "SELECT id FROM ref.location") == []


def test_m0_seed_rolls_back_on_conflicting_assignment(empty_db: str) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    seed(empty_db, secrets.token_urlsafe(24))
    execute(
        empty_db,
        """UPDATE hr.employee_assignment SET location_id=(
        SELECT id FROM ref.location WHERE code='HQ') WHERE employee_id=(
        SELECT id FROM hr.employee WHERE employee_no='DEMO-DISPATCHER')""",
    )
    with pytest.raises(ValueError, match="different active assignment"):
        seed(empty_db, secrets.token_urlsafe(24))
    assert len(fetch(empty_db, "SELECT id FROM ref.app_user")) == 5
