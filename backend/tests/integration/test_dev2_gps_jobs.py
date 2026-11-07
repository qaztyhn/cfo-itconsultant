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


def _on_road_with_old_signal(db: str) -> None:
    command.upgrade(alembic_config(db), "0007")
    execute(db, *rows.REF_HR, rows.trip_sql(1))
    execute(
        db,
        "UPDATE ref.market SET gps_enabled=true",
        "UPDATE ops.delivery_trip SET status='on_road',depart_actual_at='2026-11-06T22:00Z'",
        "INSERT INTO ops.vehicle_position(trip_id,vehicle_id,lat,lon,recorded_at,source) "
        "VALUES (1,1,59,18,'2026-11-06T22:30Z','simulator')",
    )


def _open_gps_lost(db: str) -> list[object]:
    return [r[0] for r in fetch(db, "SELECT id FROM ops.alert WHERE type='GPS_LOST' AND resolved_at IS NULL")]


def test_US_GPS_03_AC1_alert_resolves_when_signal_recovers(empty_db: str) -> None:
    _on_road_with_old_signal(empty_db)
    assert transact(empty_db, lambda s: check_lost(s, now=NOW)) == 1
    assert len(_open_gps_lost(empty_db)) == 1
    execute(
        empty_db,
        "INSERT INTO ops.vehicle_position(trip_id,vehicle_id,lat,lon,recorded_at,source) "
        "VALUES (1,1,59,18,'2026-11-06T23:58Z','simulator')",  # tín hiệu mới, trong ngưỡng
    )
    assert transact(empty_db, lambda s: check_lost(s, now=NOW)) == 0
    assert _open_gps_lost(empty_db) == []
    resolved = fetch(empty_db, "SELECT resolved_at FROM ops.alert WHERE type='GPS_LOST'")[0][0]
    assert resolved == NOW
    # mất tín hiệu lần nữa → cảnh báo MỚI (dedupe chỉ áp với cảnh báo đang mở)
    later = datetime(2026, 11, 7, 2, 0, tzinfo=UTC)
    assert transact(empty_db, lambda s: check_lost(s, now=later)) == 1
    assert fetch(empty_db, "SELECT count(*) FROM ops.alert WHERE type='GPS_LOST'")[0][0] == 2


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE ops.delivery_trip SET status='completed',ended_at='2026-11-06T23:59Z'",
        "UPDATE ops.delivery_trip SET status='cancelled'",
        "UPDATE ref.market SET gps_enabled=false",
    ],
)
def test_US_GPS_03_AC1_alert_resolves_when_trip_is_no_longer_tracked(empty_db: str, change: str) -> None:
    _on_road_with_old_signal(empty_db)
    assert transact(empty_db, lambda s: check_lost(s, now=NOW)) == 1
    execute(empty_db, change)
    assert transact(empty_db, lambda s: check_lost(s, now=NOW)) == 0
    assert _open_gps_lost(empty_db) == []


@pytest.mark.parametrize("status", ["cancelled", "completed"])
def test_US_GPS_03_AC2_finished_trip_without_end_time_does_not_keep_gps_forever(
    empty_db: str, status: str
) -> None:
    command.upgrade(alembic_config(empty_db), "0007")
    execute(empty_db, *rows.REF_HR, rows.trip_sql(1))
    execute(
        empty_db,
        f"UPDATE ops.delivery_trip SET status='{status}',ended_at=NULL",
        "INSERT INTO ops.vehicle_position(trip_id,vehicle_id,lat,lon,recorded_at,source) VALUES "
        "(1,1,59,18,'2026-01-01T00:00Z','simulator'), "  # quá thời hạn (mặc định 30 ngày)
        "(1,1,59,18,'2026-11-01T00:00Z','simulator')",  # còn trong thời hạn
    )
    assert transact(empty_db, lambda s: purge_positions(s, now=NOW)) == 1
    remaining = [r[0] for r in fetch(empty_db, "SELECT recorded_at FROM ops.vehicle_position")]
    assert remaining == [datetime(2026, 11, 1, tzinfo=UTC)]
    later = datetime(2026, 12, 15, tzinfo=UTC)
    assert transact(empty_db, lambda s: purge_positions(s, now=later)) == 1
    assert fetch(empty_db, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0
