import pytest

from alembic import command
from app.adapters.market_setup import add_market
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration


def test_US_INT_04_AC1_market_table_view_constraints_and_repeatability(
    empty_db: str,
) -> None:
    command.upgrade(alembic_config(empty_db), "head")
    for _ in range(2):
        transact(
            empty_db,
            lambda s: add_market(s, "DK", name="Denmark", timezone="Europe/Copenhagen", currency="DKK"),
        )
    assert fetch(empty_db, "SELECT shadow_mode FROM ref.market WHERE code='DK'")[0][0]
    execute(
        empty_db,
        "INSERT INTO ref.product_dk(local_sku,name,category,sale_unit,unit_price) "
        "VALUES ('A','A','A','pc',1)",
    )
    assert tuple(
        fetch(
            empty_db,
            "SELECT market_code,currency FROM ref.v_product_local WHERE market_code='DK'",
        )[0]
    ) == ("DK", "DKK")
    assert (
        fetch(
            empty_db,
            "SELECT count(*) FROM pg_constraint WHERE conrelid='ref.product_dk'::regclass AND contype='f'",
        )[0][0]
        == 2
    )
    assert (
        fetch(
            empty_db,
            "SELECT count(*) FROM pg_trigger WHERE tgrelid='ref.product_dk'::regclass AND NOT tgisinternal",
        )[0][0]
        == 1
    )
    with pytest.raises(ValueError):
        transact(
            empty_db,
            lambda s: add_market(s, "DK", name="Different", timezone="UTC", currency="EUR"),
        )
    assert fetch(empty_db, "SELECT name FROM ref.market WHERE code='DK'")[0][0] == "Denmark"
