from datetime import UTC, datetime

import pytest

from alembic import command
from app.jobs.stale_data import check_stale_stock
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, 9, tzinfo=UTC)


def test_US_INT_03_AC2_stale_threshold_dedupe_recovery_and_market_config(empty_db: str) -> None:
    command.upgrade(alembic_config(empty_db), "0007")
    execute(
        empty_db,
        *rows.REF_HR,
        "INSERT INTO ops.stock_snapshot(warehouse_id,global_product_id,on_hand,wms_reserved,as_of) "
        "VALUES (1,1,800,0,'2026-11-04T08:45Z')",
    )

    def check() -> int:
        return transact(empty_db, lambda s: check_stale_stock(s, now=NOW))

    assert check() == 0  # Exactly 15 minutes is not stale.
    execute(empty_db, "UPDATE ops.stock_snapshot SET as_of='2026-11-04T08:44:59Z'")
    assert check() == 1
    assert check() == 0
    assert fetch(empty_db, "SELECT target_roles FROM ops.alert")[0][0] == ["dispatcher"]
    execute(empty_db, "UPDATE ops.stock_snapshot SET as_of='2026-11-04T09:00Z'")
    assert check() == 0
    assert fetch(empty_db, "SELECT resolved_at FROM ops.alert")[0][0] == NOW
    execute(
        empty_db,
        "UPDATE ref.market SET config='{\"stale_stock_min\":5}'",
        "UPDATE ops.stock_snapshot SET as_of='2026-11-04T08:54Z'",
    )
    assert check() == 1
    assert fetch(empty_db, "SELECT on_hand FROM ops.stock_snapshot")[0][0] == 800
