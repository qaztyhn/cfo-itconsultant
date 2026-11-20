"""R3 one-point GPS regressions migrated from the superseded D3 batch contract."""

from uuid import uuid4

import pytest

from tests.integration.api_harness import Api, assert_error
from tests.integration.conftest import execute, fetch
from tests.integration.test_t13_one_point_gps import POINT, prepared as gps, send  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("user_id", [1, 2, 3, 6, 10, 12, 13])
def test_US_GPS_01_AC2_other_roles_cannot_submit_point(gps: Api, user_id: int) -> None:
    assert_error(send(gps, key=str(uuid4()), user=user_id), 403, "FORBIDDEN")
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


def test_US_GPS_01_AC2_unauthenticated_driver_cannot_submit_point(gps: Api) -> None:
    response = gps.client.post(
        "/api/v1/trips/1/positions",
        headers={"Idempotency-Key": str(uuid4())},
        json=POINT,
    )
    assert_error(response, 401, "AUTH_INVALID")


def test_US_GPS_01_AC2_disabled_market_rejects_without_storing(gps: Api) -> None:
    execute(gps.dsn, "UPDATE ref.market SET gps_enabled=false WHERE id=1")
    assert_error(send(gps, key=str(uuid4())), 403, "GPS_DISABLED")
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


def test_US_GPS_01_AC3_privacy_notice_is_required(gps: Api) -> None:
    execute(gps.dsn, "UPDATE ref.compliance_record SET status='missing' WHERE type='GPS_NOTICE'")
    assert_error(send(gps, key=str(uuid4())), 403, "FORBIDDEN")
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


@pytest.mark.parametrize(
    "invalid",
    [
        {**POINT, "lat": 91},
        {**POINT, "lon": -181},
        {**POINT, "accuracy_m": -1},
        {**POINT, "recorded_at": "2026-11-10T08:05:00"},
        {**POINT, "source": "device"},
    ],
)
def test_US_GPS_01_AC2_invalid_point_rejected_without_write(gps: Api, invalid: dict[str, object]) -> None:
    assert_error(send(gps, invalid, key=str(uuid4())), 422, "VALIDATION_ERROR")
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


def test_US_GPS_01_AC1_new_key_same_timestamp_is_not_a_second_point(gps: Api) -> None:
    assert send(gps, key=str(uuid4())).status_code == 202
    assert_error(send(gps, key=str(uuid4())), 409, "DUPLICATE_EVENT")
    assert fetch(gps.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 1


@pytest.mark.parametrize("user_id", [1, 3, 5, 6, 10, 12, 13])
def test_US_GPS_02_AC2_other_roles_cannot_read_live(gps: Api, user_id: int) -> None:
    assert_error(gps.get("/gps/live", user_id), 403, "FORBIDDEN")


def test_US_GPS_02_AC1_unassigned_dispatcher_gets_empty_live_list(gps: Api) -> None:
    execute(gps.dsn, "UPDATE ops.delivery_trip SET assigned_dispatcher_employee_id=NULL WHERE id=1")
    response = gps.get("/gps/live", 2)
    assert response.status_code == 200 and response.json() == []


def test_US_GPS_02_AC4_historical_position_route_is_unmounted(gps: Api) -> None:
    assert_error(gps.get("/trips/1/positions", 2), 405, "VALIDATION_ERROR")
