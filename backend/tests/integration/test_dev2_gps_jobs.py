from datetime import UTC, datetime

import pytest

from alembic import command
from app.jobs.gps_lost import check_lost
from app.jobs.gps_retention import purge_positions
from tests.integration import rows
from tests.integration.conftest import alembic_config, execute, fetch
from tests.integration.dev2_helpers import transact

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 7, tzinfo=UTC)


def test_US_GPS_03_AC2_retention_uses_end_time_not_point_age(empty_db: str) -> None:
    command.upgrade(alembic_config(empty_db), "0007")
    execute(empty_db, *rows.REF_HR, rows.trip_sql(1), rows.trip_sql(2), rows.trip_sql(1))
    execute(
        empty_db,
        "UPDATE ops.delivery_trip SET status='completed',ended_at='2026-10-07T00:00Z' WHERE id=1",
        "UPDATE ops.delivery_trip SET status='completed',ended_at='2026-10-08T00:00Z' WHERE id=2",
        "UPDATE ops.delivery_trip SET status='on_road' WHERE id=3",
        "INSERT INTO ops.vehicle_position(trip_id,vehicle_id,lat,lon,recorded_at,source) "
        "SELECT id,vehicle_id,59,18,'2026-01-01T00:00Z','simulator' FROM ops.delivery_trip",
    )
    assert transact(empty_db, lambda s: purge_positions(s, now=NOW)) == 1
    assert [r[0] for r in fetch(empty_db, "SELECT trip_id FROM ops.vehicle_position ORDER BY trip_id")] == [
        2,
        3,
    ]
    assert transact(empty_db, lambda s: purge_positions(s, now=NOW)) == 0


def test_US_GPS_03_AC1_loss_check_is_scoped_deduplicated_and_respects_threshold(
    empty_db: str,
) -> None:
    command.upgrade(alembic_config(empty_db), "0007")
    execute(empty_db, *rows.REF_HR, rows.trip_sql(1), rows.trip_sql(2))
    execute(
        empty_db,
        "UPDATE ref.market SET gps_enabled=true",
        "UPDATE ops.delivery_trip SET status='on_road',depart_actual_at='2026-11-06T22:00Z'",
        "INSERT INTO ops.vehicle_position(trip_id,vehicle_id,lat,lon,recorded_at,source) "
        "VALUES (2,2,59,18,'2026-11-06T23:00Z','simulator')",
    )
    assert transact(empty_db, lambda s: check_lost(s, now=NOW)) == 1
    assert transact(empty_db, lambda s: check_lost(s, now=NOW)) == 0
    row = fetch(empty_db, "SELECT target_roles,message FROM ops.alert")[0]
    assert row[0] == ["dispatcher"]
    assert row[1] == "Trip GPS signal overdue."
    execute(empty_db, "UPDATE ref.market SET gps_enabled=false", "DELETE FROM ops.alert")
    assert transact(empty_db, lambda s: check_lost(s, now=NOW)) == 0
