import pytest

from alembic import command
from app.seed.infrastructure import seed_infrastructure
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration


def test_US_SRC_01_AC1_infrastructure_seed_is_repeatable_and_preserves_edits(
    empty_db: str,
) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    transact(empty_db, lambda s: seed_infrastructure(s, year=2026))
    execute(empty_db, "UPDATE hr.shift_template SET expected_staff=9")
    transact(empty_db, lambda s: seed_infrastructure(s, year=2026))
    assert fetch(empty_db, "SELECT count(*) FROM ref.location WHERE type='warehouse'")[0][0] == 3
    assert fetch(empty_db, "SELECT count(*) FROM hr.shift_template WHERE expected_staff=9")[0][0] == 30
    assert (
        fetch(
            empty_db,
            "SELECT count(*) FROM ref.market_holiday WHERE holiday_date='2026-12-25'",
        )[
            0
        ][0]
        == 1
    )
