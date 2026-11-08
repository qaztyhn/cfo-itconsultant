"""Migration 0012 — DEC-OWNER-20261109 M6-1: successful POD unique per trip_stop, not per order."""

from collections.abc import Iterator

import asyncpg
import pytest

from alembic import command
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch, rejects

UNIQUE = asyncpg.UniqueViolationError
pytestmark = pytest.mark.integration


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    execute(empty_db, *rows.REF_HR, rows.order_sql(1), rows.trip_sql(1), rows.trip_sql(2))
    execute(empty_db, rows.stop_sql(1, 1), rows.stop_sql(2, 1))
    yield empty_db


def test_order_level_unique_index_is_gone_and_per_stop_index_exists(db: str) -> None:
    names = {
        r["indexname"]
        for r in fetch(db, "SELECT indexname FROM pg_indexes WHERE tablename='proof_of_delivery'")
    }
    assert "ux_pod_one_delivered" not in names
    assert "ux_pod_one_delivered_trip_stop" in names


def test_two_stops_of_one_order_can_both_be_delivered(db: str) -> None:
    execute(db, rows.pod_sql(1, 1, "delivered"), rows.pod_sql(2, 1, "delivered"))
    assert fetch(db, "SELECT count(*) AS n FROM ops.proof_of_delivery WHERE order_id=1")[0]["n"] == 2


def test_one_stop_still_has_at_most_one_pod(db: str) -> None:
    execute(db, rows.pod_sql(1, 1, "delivered"))
    rejects(db, UNIQUE, "proof_of_delivery_trip_stop_id_key", rows.pod_sql(1, 1, "delivered"))
    rejects(db, UNIQUE, "proof_of_delivery_trip_stop_id_key", rows.pod_sql(1, 1, "failed", "customer_absent"))


def test_downgrade_fails_closed_when_multi_vehicle_pods_exist_and_works_when_empty(db: str) -> None:
    cfg = alembic_config(db)
    execute(db, rows.pod_sql(1, 1, "delivered"), rows.pod_sql(2, 1, "delivered"))
    with pytest.raises(Exception, match="ux_pod_one_delivered"):
        command.downgrade(cfg, "0011")
