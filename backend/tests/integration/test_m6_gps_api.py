"""D3 GPS API: real PostgreSQL duty, privacy, cadence, replay and retention tests."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.errors import DomainError
from app.deps import CurrentUser
from app.domain.models.ops import DeliveryTrip
from app.services import gps_service
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import async_url, execute, fetch
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
        "lat": lat,
        "lon": lon,
        "accuracy_m": 12.5,
        "recorded_at": at,
        "source": "device",
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
    points = fetch(gps.dsn, "SELECT trip_id,vehicle_id,lat,lon,source FROM ops.vehicle_position")
    assert len(points) == 1
    assert tuple(points[0][:2]) == (1, 1)
    assert points[0]["source"] == "device"


def test_US_GPS_01_AC1_offline_points_can_arrive_out_of_order_in_current_shift(gps: Api) -> None:
    response = submit(gps, [position("2026-11-10T08:00:00Z"), position("2026-11-10T07:00:00Z")])
    assert response.status_code == 202 and response.json()["accepted"] == 2
    times = fetch(gps.dsn, "SELECT recorded_at FROM ops.vehicle_position ORDER BY recorded_at")
    assert [r["recorded_at"].hour for r in times] == [7, 8]


def test_US_GPS_01_AC4_simulator_cadence_does_not_change_device_policy(gps: Api) -> None:
    # Existing trusted simulator rows may be sampled at 1–2 minute intervals.
    # The authenticated driver endpoint must still enforce 30 minutes on device points only.
    execute(
        gps.dsn,
        "INSERT INTO ops.vehicle_position (trip_id,vehicle_id,lat,lon,recorded_at,source) "
        "VALUES (1,1,59.3,18.1,'2026-11-10T07:10:00Z','simulator'),"
        "(1,1,59.3,18.1,'2026-11-10T07:12:00Z','simulator')",
    )
    result = submit(gps, [position("2026-11-10T07:00:00Z"), position("2026-11-10T07:30:00Z")])
    assert result.status_code == 202, result.text
    assert result.json()["accepted"] == 2
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position WHERE source='simulator'")[0][0] == 2


def test_US_GPS_01_AC1_replay_is_idempotent_and_conflict_is_atomic(gps: Api) -> None:
    p = position("2026-11-10T07:00:00Z")
    assert submit(gps, [p]).json()["accepted"] == 1
    assert submit(gps, [p]).json()["accepted"] == 0
    assert_error(submit(gps, [position("2026-11-10T07:00:00Z", lat=59.4)]), 409, "DUPLICATE_EVENT")
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 1


def test_US_GPS_01_AC1_duplicate_timestamp_within_batch_rolls_back(gps: Api) -> None:
    first = position("2026-11-10T07:00:00Z")
    conflicting = position("2026-11-10T07:00:00Z", lat=59.4)
    assert_error(submit(gps, [first, conflicting]), 409, "DUPLICATE_EVENT")
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


def test_US_GPS_01_AC1_large_history_preserves_bounded_replay_and_cadence(gps: Api) -> None:
    # Adversarial historical residue: upload must look up exact timestamps and nearby
    # device points rather than materializing every old position into application memory.
    execute(
        gps.dsn,
        "INSERT INTO ops.vehicle_position (trip_id,vehicle_id,lat,lon,recorded_at,source) "
        "SELECT 1,1,59.3,18.1,'2026-10-01T00:00:00Z'::timestamptz "
        "+ n * interval '30 minutes','device' FROM generate_series(0,1499) AS n",
    )
    first = position("2026-11-10T07:00:00Z")
    assert submit(gps, [first]).json() == {"accepted": 1, "eta": None}
    assert submit(gps, [first]).json() == {"accepted": 0, "eta": None}
    assert_error(submit(gps, [position("2026-11-10T07:29:59Z")]), 422, "VALIDATION_ERROR")
    assert submit(gps, [position("2026-11-10T07:30:00Z")]).json() == {"accepted": 1, "eta": None}
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 1502


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
    assert (
        submit(gps, [position("2026-11-10T07:00:00Z"), position("2026-11-10T07:30:00Z")]).json()["accepted"]
        == 2
    )


@pytest.mark.parametrize(
    "gps_config",
    ['{"interval_min":1,"lost_min":60}', '{"interval_min":30,"lost_min":1}'],
)
def test_US_GPS_01_AC1_unapproved_gps_cadence_fails_closed(gps: Api, gps_config: str) -> None:
    execute(
        gps.dsn,
        "UPDATE ref.market SET config=jsonb_build_object('gps', " f"'{gps_config}'::jsonb) WHERE id=1",
    )
    assert_error(
        submit(gps, [position("2026-11-10T07:00:00Z")]),
        422,
        "VALIDATION_ERROR",
    )
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


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


def test_US_GPS_01_AC2_two_markets_never_share_driver_trip_scope(gps: Api) -> None:
    execute(
        gps.dsn,
        "UPDATE ref.app_user SET roles='{driver}' WHERE id=10",
        "INSERT INTO hr.driver_staff(employee_id,home_warehouse_id,licence_class,"
        "licence_expires_on) VALUES (10,4,'C','2027-12-01')",
        "INSERT INTO ref.vehicle (home_warehouse_id,code,plate,name,capacity_kg,"
        "capacity_m3,required_licence) VALUES (4,'GPS-ZZ','ZZ-GPS','Synthetic',1000,10,'C')",
        "INSERT INTO ops.delivery_trip(warehouse_id,vehicle_id,driver_employee_id,"
        "depart_planned_at,status,depart_actual_at) VALUES "
        "(4,3,10,'2026-11-10T07:00Z','on_road','2026-11-10T07:00Z')",
        "INSERT INTO hr.employee_shift_schedule(employee_id,warehouse_id,work_date,"
        "start_time,end_time,assigned_by,assigned_at) VALUES "
        "(10,4,'2026-11-10','07:00','17:00',10,'2026-11-08T09:00Z')",
        "UPDATE ref.market SET gps_enabled=true WHERE id=2",
        "INSERT INTO ref.compliance_record(market_id,type,status,approved_on) "
        "VALUES(2,'GPS_NOTICE','approved','2026-11-01')",
    )
    point = position("2026-11-10T07:00:00Z")
    assert_error(submit(gps, [point], user=10, trip=1), 404, "NOT_FOUND")
    assert_error(submit(gps, [point], user=DRIVER, trip=4), 404, "NOT_FOUND")
    result = submit(gps, [point], user=10, trip=4)
    assert result.status_code == 202 and result.json()["accepted"] == 1


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


def _count(gps: Api) -> int:
    return fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0]


async def _finish_trip(session, at=NOW):
    trip = await session.get(DeliveryTrip, 1)
    assert trip is not None
    trip.status = "completed"
    trip.ended_at = at
    await session.flush()


def test_DEC_GPS_RET_terminal_hook_keeps_valid_points_and_stops_collection(gps: Api) -> None:
    """Valid collected points survive the terminal transaction (7-day retention); collection stops at once."""
    assert submit(gps, [position("2026-11-10T07:00:00Z")]).status_code == 202

    async def finish_and_close(session):
        await _finish_trip(session)
        return await gps_service.close_trip_collection(session, 1, now=NOW)

    assert transact(gps.dsn, finish_and_close) == 0  # nothing invalid to remove
    assert _count(gps) == 1
    assert transact(gps.dsn, lambda s: gps_service.close_trip_collection(s, 1, now=NOW)) == 0  # idempotent
    assert_error(submit(gps, [position("2026-11-10T07:30:00Z")]), 409, "NOT_ON_TRIP")  # no late upload
    assert _count(gps) == 1


def test_DEC_GPS_RET_terminal_hook_removes_only_invalid_points(gps: Api) -> None:
    execute(
        gps.dsn,
        "INSERT INTO ops.vehicle_position (trip_id, vehicle_id, lat, lon, recorded_at, source) VALUES "
        "(1, 1, 59, 18, '2026-11-10T07:00Z', 'device'), "  # valid: after departure, before terminal
        "(1, 1, 59, 18, '2026-11-10T06:30Z', 'device'), "  # before actual departure
        "(1, 1, 59, 18, '2026-11-10T09:00Z', 'device')",  # after the trip ended at 08:30Z
    )

    async def finish_and_close(session):
        await _finish_trip(session)
        return await gps_service.close_trip_collection(session, 1, now=NOW)

    assert transact(gps.dsn, finish_and_close) == 2
    kept = fetch(gps.dsn, "SELECT recorded_at FROM ops.vehicle_position")
    assert [r["recorded_at"] for r in kept] == [datetime(2026, 11, 10, 7, 0, tzinfo=UTC)]


def test_DEC_GPS_RET_close_refuses_an_active_trip(gps: Api) -> None:
    assert submit(gps, [position("2026-11-10T07:00:00Z")]).status_code == 202
    with pytest.raises(Exception, match="active GPS"):
        transact(gps.dsn, lambda s: gps_service.close_trip_collection(s, 1, now=NOW))
    assert _count(gps) == 1


def test_DEC_GPS_RET_valid_points_survive_shift_end_cleanup_but_not_seven_days(gps: Api) -> None:
    assert submit(gps, [position("2026-11-10T07:00:00Z")]).status_code == 202
    transact(gps.dsn, _finish_trip)
    after_shift = datetime(2026, 11, 10, 17, 0, tzinfo=UTC)
    assert transact(gps.dsn, lambda s: gps_service.purge_expired(session=s, now=after_shift)) == 0
    assert _count(gps) == 1
    six_days = datetime(2026, 11, 16, 23, 59, tzinfo=UTC)
    assert transact(gps.dsn, lambda s: gps_service.purge_expired(session=s, now=six_days)) == 0
    seven_days = datetime(2026, 11, 17, 7, 0, tzinfo=UTC)  # exactly recorded_at + 7 x 24 h
    assert transact(gps.dsn, lambda s: gps_service.purge_expired(session=s, now=seven_days)) == 0
    after = datetime(2026, 11, 17, 7, 1, tzinfo=UTC)
    assert transact(gps.dsn, lambda s: gps_service.purge_expired(session=s, now=after)) == 1
    assert _count(gps) == 0
    assert transact(gps.dsn, lambda s: gps_service.purge_expired(session=s, now=after)) == 0  # idempotent
    assert fetch(gps.dsn, "SELECT count(*) FROM hr.driver_staff")[0][0] == 1  # duty evidence untouched


def test_DEC_GPS_RET_invalid_points_of_finished_trips_are_purged_immediately(gps: Api) -> None:
    execute(
        gps.dsn,
        "INSERT INTO ops.vehicle_position (trip_id, vehicle_id, lat, lon, recorded_at, source) VALUES "
        "(1, 1, 59, 18, '2026-11-10T07:00Z', 'device'), "
        "(1, 1, 59, 18, '2026-11-10T05:00Z', 'device'), "  # before the official shift
        "(1, 1, 59, 18, '2026-11-10T17:00Z', 'device'), "  # after the official shift (16:00Z)
        "(2, 2, 59, 18, '2026-11-10T07:00Z', 'device')",  # trip without actual departure
    )
    transact(gps.dsn, _finish_trip)
    when = datetime(2026, 11, 10, 18, 0, tzinfo=UTC)
    assert transact(gps.dsn, lambda s: gps_service.purge_expired(session=s, now=when)) == 3
    kept = fetch(gps.dsn, "SELECT trip_id FROM ops.vehicle_position")
    assert [r["trip_id"] for r in kept] == [1]


def test_DEC_GPS_RET_seven_days_is_absolute_across_the_dst_change(gps: Api) -> None:
    """Stockholm changes to winter time on 2026-10-25: 7 x 24 h is an instant, not 7 wall-clock days."""
    execute(
        gps.dsn,
        "UPDATE ops.delivery_trip SET depart_actual_at='2026-10-20T08:00Z' WHERE id=1",
        "INSERT INTO hr.employee_shift_schedule (employee_id,warehouse_id,work_date,start_time,end_time,"
        "assigned_by,assigned_at) VALUES (5,1,'2026-10-20','09:00','17:00',3,'2026-10-18T09:00Z')",
        "INSERT INTO ops.vehicle_position (trip_id, vehicle_id, lat, lon, recorded_at, source) "
        "VALUES (1, 1, 59, 18, '2026-10-20T12:00Z', 'device')",
    )
    transact(gps.dsn, lambda s: _finish_trip(s, datetime(2026, 10, 20, 14, 0, tzinfo=UTC)))
    before = datetime(2026, 10, 27, 11, 59, tzinfo=UTC)
    assert transact(gps.dsn, lambda s: gps_service.purge_expired(session=s, now=before)) == 0
    at = datetime(2026, 10, 27, 12, 1, tzinfo=UTC)
    assert transact(gps.dsn, lambda s: gps_service.purge_expired(session=s, now=at)) == 1


def test_DEC_GPS_RET_history_is_denied_by_default_and_needs_case_reason_and_audit(gps: Api) -> None:
    assert submit(gps, [position("2026-11-10T07:00:00Z")]).status_code == 202
    transact(gps.dsn, _finish_trip)
    dispatcher = CurrentUser(id=DISPATCHER, employee_id=2, roles=("dispatcher",), market="SE")

    async def read(session, actor=dispatcher, **kw):
        return await gps_service.read_history(
            session,
            actor,
            1,
            case_ref=kw.pop("case_ref", "CASE-1"),
            reason=kw.pop("reason", "Complaint"),
            now=NOW,
            **kw,
        )

    with pytest.raises(DomainError) as denied:
        transact(gps.dsn, read)
    assert denied.value.code == "FORBIDDEN"  # no reviewer authority source is approved: deny by default
    assert (
        fetch(gps.dsn, "SELECT count(*) FROM audit.decision_log WHERE action='GPS_HISTORY_ACCESSED'")[0][0]
        == 0
    )

    async def allow(_s, _a, _t):
        return True

    with pytest.raises(DomainError) as bad:
        transact(gps.dsn, lambda s: read(s, authorizer=allow, case_ref=" "))
    assert bad.value.code == "VALIDATION_ERROR"
    other_market = CurrentUser(id=DISPATCHER, employee_id=2, roles=("dispatcher",), market="ZZ")
    with pytest.raises(DomainError) as cross:
        transact(gps.dsn, lambda s: read(s, other_market, authorizer=allow))
    assert cross.value.code == "NOT_FOUND"
    points = transact(gps.dsn, lambda s: read(s, authorizer=allow))
    assert len(points) == 1
    audit = fetch(
        gps.dsn,
        "SELECT reason_text, snapshot::text AS snap FROM audit.decision_log "
        "WHERE action='GPS_HISTORY_ACCESSED'",
    )
    assert len(audit) == 1 and audit[0]["reason_text"] == "Complaint"
    assert "59" not in audit[0]["snap"] and "CASE-1" in audit[0]["snap"]  # no coordinates in the audit
    # beyond 7 days nothing is returned (already purged or excluded)
    late = datetime(2026, 11, 20, tzinfo=UTC)
    assert (
        transact(
            gps.dsn,
            lambda s: gps_service.read_history(
                s, dispatcher, 1, case_ref="C", reason="r", authorizer=allow, now=late
            ),
        )
        == []
    )


def test_US_GPS_03_AC1_lost_signal_dedupes_and_resolves_after_recovery(gps: Api) -> None:
    assert transact(gps.dsn, lambda s: gps_service.lost_check(session=s, now=NOW)) == 1
    assert transact(gps.dsn, lambda s: gps_service.lost_check(session=s, now=NOW)) == 0
    assert (
        fetch(gps.dsn, "SELECT count(*) FROM ops.alert WHERE type='GPS_LOST' AND resolved_at IS NULL")[0][0]
        == 1
    )
    assert submit(gps, [position("2026-11-10T08:25:00Z")]).status_code == 202
    assert transact(gps.dsn, lambda s: gps_service.lost_check(session=s, now=NOW)) == 0
    assert (
        fetch(gps.dsn, "SELECT count(*) FROM ops.alert WHERE type='GPS_LOST' AND resolved_at IS NULL")[0][0]
        == 0
    )
    alert = fetch(gps.dsn, "SELECT message FROM ops.alert WHERE type='GPS_LOST'")[0]
    assert "59" not in alert["message"] and "driver" not in alert["message"].lower()


def test_US_GPS_03_AC2_concurrent_terminal_commit_prevents_late_offline_upload(gps: Api) -> None:
    """The trip row lock serializes the terminal hook and device write."""

    async def scenario() -> tuple[int, str]:
        engine = create_async_engine(async_url(gps.dsn), poolclass=NullPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        locked, release = asyncio.Event(), asyncio.Event()
        actor = CurrentUser(id=DRIVER, employee_id=DRIVER, roles=("driver",), market="SE")

        async def finish() -> int:
            async with maker() as session, session.begin():
                trip = await session.scalar(
                    select(DeliveryTrip).where(DeliveryTrip.id == 1).with_for_update()
                )
                assert trip is not None
                trip.status = "completed"
                trip.ended_at = NOW
                await session.flush()
                locked.set()
                await release.wait()
                return await gps_service.close_trip_collection(session, 1, now=NOW)

        async def upload() -> str:
            await locked.wait()
            try:
                async with maker() as session, session.begin():
                    await gps_service.ingest_positions(
                        1,
                        actor,
                        [
                            {
                                "lat": Decimal("59.30000"),
                                "lon": Decimal("18.10000"),
                                "accuracy_m": Decimal("12.5"),
                                "recorded_at": datetime(2026, 11, 10, 7, tzinfo=UTC),
                                "source": "device",
                            }
                        ],
                        session=session,
                        now=NOW,
                    )
            except DomainError as exc:
                return exc.code
            return "unexpected_acceptance"

        try:
            completion = asyncio.create_task(finish())
            await locked.wait()
            upload_task = asyncio.create_task(upload())
            await asyncio.sleep(0)
            release.set()
            return await completion, await upload_task
        finally:
            await engine.dispose()

    purged, result = asyncio.run(scenario())
    assert purged == 0
    assert result == "NOT_ON_TRIP"
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0
