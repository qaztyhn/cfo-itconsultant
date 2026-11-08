"""D3 GPS API: real PostgreSQL duty, privacy, cadence, replay and retention tests."""

from datetime import UTC, datetime

import pytest

from app.domain.models.ops import DeliveryTrip
from app.services import gps_service
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.dev2_helpers import transact
from tests.integration.hr_fixture import (
    ADMIN,
    CS,
    DISPATCHER,
    DRIVER,
    SALES,
    SETUP,
    VIEWER,
    WAREHOUSE,
    ZZ_WAREHOUSE,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 10, 8, 30, tzinfo=UTC)


def position(at: str, *, lat: float = 59.3, lon: float = 18.1) -> dict[str, object]:
    return {
        "lat": lat, "lon": lon, "accuracy_m": 12.5,
        "recorded_at": at, "source": "device",
    }


def submit(client: Api, positions: list[dict[str, object]], user: int | None = DRIVER, trip: int = 1):
    return client.send("POST", f"/trips/{trip}/positions", user, {"positions": positions})


@pytest.fixture
def gps(api: Api, monkeypatch: pytest.MonkeyPatch) -> Api:  # noqa: F811
    execute(
        api.dsn,
        *SETUP,
        "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, "
        "capacity_m3, required_licence) VALUES "
        "(1,'GPS-V1','GPS-1','Synthetic vehicle 1',1000,10,'B'),"
        "(1,'GPS-V2','GPS-2','Synthetic vehicle 2',1000,10,'B')",
        "INSERT INTO ops.delivery_trip (warehouse_id,vehicle_id,driver_employee_id, "
        "depart_planned_at,status,depart_actual_at) VALUES "
        "(1,1,5,'2026-11-10T07:00Z','on_road','2026-11-10T07:00Z'),"
        "(1,2,5,'2026-11-10T09:00Z','planned',NULL),"
        "(1,2,2,'2026-11-10T07:00Z','on_road','2026-11-10T07:00Z')",
        "INSERT INTO hr.employee_shift_schedule (employee_id,warehouse_id,work_date,"
        "start_time,end_time,assigned_by,assigned_at) VALUES "
        "(5,1,'2026-11-10','07:00','17:00',3,'2026-11-08T09:00Z')",
        "UPDATE ref.market SET gps_enabled=true WHERE id=1",
        "INSERT INTO ref.compliance_record (market_id,type,status,approved_on,reference) "
        "VALUES (1,'GPS_NOTICE','approved','2026-11-01','SYNTHETIC-NOTICE')",
    )
    monkeypatch.setattr(gps_service.clock, "now", lambda: NOW)
    return api


def test_US_GPS_01_AC1_device_gps_is_accepted_without_echoing_coordinates(gps: Api) -> None:
    response = submit(gps, [position("2026-11-10T07:00:00Z")])
    assert response.status_code == 202, response.text
    assert response.json() == {"accepted": 1, "eta": None}
    assert "lat" not in response.text.lower() and "59.3" not in response.text
    points = fetch(
        gps.dsn, "SELECT trip_id,vehicle_id,lat,lon,source FROM ops.vehicle_position"
    )
    assert len(points) == 1
    assert tuple(points[0][:2]) == (1, 1)
    assert points[0]["source"] == "device"


def test_US_GPS_01_AC1_offline_points_can_arrive_out_of_order_in_current_shift(gps: Api) -> None:
    response = submit(
        gps, [position("2026-11-10T08:00:00Z"), position("2026-11-10T07:00:00Z")]
    )
    assert response.status_code == 202 and response.json()["accepted"] == 2
    times = fetch(gps.dsn, "SELECT recorded_at FROM ops.vehicle_position ORDER BY recorded_at")
    assert [r["recorded_at"].hour for r in times] == [7, 8]


def test_US_GPS_01_AC1_replay_is_idempotent_and_conflict_is_atomic(gps: Api) -> None:
    p = position("2026-11-10T07:00:00Z")
    assert submit(gps, [p]).json()["accepted"] == 1
    assert submit(gps, [p]).json()["accepted"] == 0
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z", lat=59.4)]), 409, "DUPLICATE_EVENT")
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 1


def test_US_GPS_01_AC1_rejects_high_frequency_sampling_without_partial_insert(gps: Api) -> None:
    assert_error(
        submit(
            gps,
            [position("2026-11-10T07:00:00Z"), position("2026-11-10T07:29:59Z")],
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0
    assert submit(
        gps, [position("2026-11-10T07:00:00Z"), position("2026-11-10T07:30:00Z")]
    ).json()["accepted"] == 2


def test_US_GPS_01_AC2_disabled_market_rejects_without_storing(gps: Api) -> None:
    execute(gps.dsn, "UPDATE ref.market SET gps_enabled=false WHERE id=1")
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z")]), 403, "GPS_DISABLED")
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


@pytest.mark.parametrize("user_id", [ADMIN, DISPATCHER, WAREHOUSE, SALES, CS, VIEWER, ZZ_WAREHOUSE])
def test_US_GPS_01_AC2_wrong_roles_never_submit_gps(gps: Api, user_id: int) -> None:
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z")], user=user_id), 403, "FORBIDDEN")


def test_US_GPS_01_AC2_unauthenticated_and_other_drivers_trip_are_denied(gps: Api) -> None:
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z")], user=None), 401, "AUTH_INVALID")
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z")], trip=3), 404, "NOT_FOUND")
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z")], trip=999), 404, "NOT_FOUND")


def test_US_GPS_01_AC5_no_collection_before_departure_or_after_completion(gps: Api) -> None:
    assert_error(submit(gps, [position("2026-11-10T08:00:00Z")], trip=2), 409, "NOT_ON_TRIP")
    execute(
        gps.dsn,
        "UPDATE ops.delivery_trip SET status='completed',ended_at='2026-11-10T08:00Z' WHERE id=1",
    )
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z")]), 409, "NOT_ON_TRIP")


def test_US_GPS_01_AC5_no_collection_outside_shift_or_original_duty_window(gps: Api) -> None:
    assert_error(submit(gps, [position("2026-11-10T05:59:00Z")]), 409, "NOT_ON_TRIP")
    assert_error(submit(gps, [position("2026-11-10T09:00:00Z")]), 409, "NOT_ON_TRIP")
    execute(
        gps.dsn,
        "UPDATE hr.employee_shift_schedule SET end_time='09:00' WHERE employee_id=5",
    )
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z")]), 409, "NOT_ON_TRIP")


def test_US_GPS_01_AC3_privacy_notice_is_required(gps: Api) -> None:
    execute(
        gps.dsn,
        "UPDATE ref.compliance_record SET status='missing' WHERE type='GPS_NOTICE'",
    )
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z")]), 403, "FORBIDDEN")
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


@pytest.mark.parametrize(
    "invalid",
    [
        {"lat": 91, "lon": 18, "recorded_at": "2026-11-10T07:00:00Z", "source": "device"},
        {"lat": 59, "lon": 181, "recorded_at": "2026-11-10T07:00:00Z", "source": "device"},
        {"lat": 59, "lon": 18, "accuracy_m": -1, "recorded_at": "2026-11-10T07:00:00Z", "source": "device"},
        {"lat": 59, "lon": 18, "recorded_at": "2026-11-10T07:00:00", "source": "device"},
        {"lat": 59, "lon": 18, "recorded_at": "2026-11-10T07:00:00Z", "source": "simulator"},
        {"lat": 59, "lon": 18, "recorded_at": "2026-11-10T07:00:00Z", "source": "device", "driver_id": 5},
    ],
)
def test_US_GPS_01_AC2_untrusted_input_rejected_without_echo(gps: Api, invalid: dict[str, object]) -> None:
    response = submit(gps, [invalid])
    assert_error(response, 422, "VALIDATION_ERROR")
    assert all("input" not in error for error in response.json()["error"]["details"]["errors"])
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


@pytest.mark.parametrize("user_id", [None, ADMIN, WAREHOUSE, SALES, CS, VIEWER, DRIVER])
def test_US_GPS_02_AC1_private_trip_coordinates_cannot_be_read_by_other_roles(
    gps: Api, user_id: int | None
) -> None:
    assert submit(gps, [position("2026-11-10T07:00:00Z")]).status_code == 202
    expected = (401, "AUTH_INVALID") if user_id is None else (403, "FORBIDDEN")
    assert_error(gps.get("/trips/1/positions", user_id), *expected)
    assert_error(gps.get("/gps/live", user_id), *expected)


def test_US_GPS_02_AC1_dispatcher_without_explicit_trip_mapping_is_denied(gps: Api) -> None:
    assert submit(gps, [position("2026-11-10T07:00:00Z")]).status_code == 202
    assert_error(gps.get("/trips/1/positions", DISPATCHER), 403, "FORBIDDEN")
    assert_error(gps.get("/trips/999/positions", DISPATCHER), 403, "FORBIDDEN")
    assert_error(gps.get("/gps/live", DISPATCHER), 403, "FORBIDDEN")


def test_US_GPS_03_AC2_terminal_hook_erases_points_in_same_transaction(gps: Api) -> None:
    assert submit(gps, [position("2026-11-10T07:00:00Z")]).status_code == 202

    async def finish_and_purge(session):
        trip = await session.get(DeliveryTrip, 1)
        assert trip is not None
        trip.status = "completed"
        trip.ended_at = NOW
        await session.flush()
        return await gps_service.purge_trip_on_terminal(session, 1, now=NOW)

    assert transact(gps.dsn, finish_and_purge) == 1
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0
    assert transact(
        gps.dsn, lambda s: gps_service.purge_trip_on_terminal(s, 1, now=NOW)
    ) == 0
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z")]), 409, "NOT_ON_TRIP")


def test_US_GPS_03_AC2_terminal_hook_refuses_to_purge_active_trip(gps: Api) -> None:
    assert submit(gps, [position("2026-11-10T07:00:00Z")]).status_code == 202
    with pytest.raises(Exception, match="active GPS"):
        transact(gps.dsn, lambda s: gps_service.purge_trip_on_terminal(s, 1, now=NOW))
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 1


def test_US_GPS_03_AC2_shift_end_cleanup_does_not_touch_duty_history(gps: Api) -> None:
    assert submit(gps, [position("2026-11-10T07:00:00Z")]).status_code == 202
    when = datetime(2026, 11, 10, 17, 0, tzinfo=UTC)
    assert transact(gps.dsn, lambda s: gps_service.purge_expired(session=s, now=when)) == 1
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0
    assert fetch(gps.dsn, "SELECT count(*) FROM hr.driver_staff")[0][0] == 1


def test_US_GPS_03_AC1_lost_signal_dedupes_and_resolves_after_recovery(gps: Api) -> None:
    assert transact(gps.dsn, lambda s: gps_service.lost_check(session=s, now=NOW)) == 1
    assert transact(gps.dsn, lambda s: gps_service.lost_check(session=s, now=NOW)) == 0
    assert fetch(
        gps.dsn, "SELECT count(*) FROM ops.alert WHERE type='GPS_LOST' AND resolved_at IS NULL"
    )[0][0] == 1
    assert submit(gps, [position("2026-11-10T08:25:00Z")]).status_code == 202
    assert transact(gps.dsn, lambda s: gps_service.lost_check(session=s, now=NOW)) == 0
    assert fetch(
        gps.dsn, "SELECT count(*) FROM ops.alert WHERE type='GPS_LOST' AND resolved_at IS NULL"
    )[0][0] == 0
    alert = fetch(gps.dsn, "SELECT message FROM ops.alert WHERE type='GPS_LOST'")[0]
    assert "59" not in alert["message"] and "driver" not in alert["message"].lower()
