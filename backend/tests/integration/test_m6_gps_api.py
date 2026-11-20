"""R3 one-point GPS regressions migrated from the superseded D3 batch contract."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.security import issue_token
from app.services import gps_service
from tests.integration import rows
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.hr_fixture import SETUP

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 10, 8, 30, tzinfo=UTC)
POINT = {"lat": 59.30, "lon": 18.10, "accuracy_m": 12.5, "recorded_at": "2026-11-10T08:05:00Z"}


@pytest.fixture(name="gps")
def _gps_fixture(api: Api, monkeypatch: pytest.MonkeyPatch) -> Api:  # noqa: F811
    execute(
        api.dsn,
        *SETUP,
        "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, "
        "capacity_m3, required_licence) VALUES "
        "(1,'GPS-1','GPS-1','Synthetic GPS vehicle',10000,20,'B')",
        "INSERT INTO ref.customer (market_id,external_ref,type,name) "
        "VALUES (1,'T13-C1','business','Synthetic T13 customer')",
        rows.order_sql(1),
        rows.run_sql(1, 1),
        rows.plan_sql(1, 1, 1, status="approved"),
        rows.plan_vehicle_sql(1, 1, 1, driver_id=5),
        "INSERT INTO ops.delivery_trip (plan_vehicle_id,warehouse_id,vehicle_id,"
        "driver_employee_id,assigned_dispatcher_employee_id,depart_planned_at,"
        "status,depart_actual_at) VALUES "
        "(1,1,1,5,2,'2026-11-10T07:00Z','on_road','2026-11-10T07:00Z')",
        rows.stop_sql(1, 1),
        "UPDATE ops.customer_order SET status='PLANNED' WHERE id=1",
        "UPDATE ops.customer_order SET status='APPROVED',approved_plan_id=1,"
        "approved_at='2026-11-10T06:45Z',committed_date='2026-11-10',"
        "promise_start='2026-11-10T08:00Z',promise_end='2026-11-10T12:00Z' WHERE id=1",
        "UPDATE ops.customer_order SET status='PREPARING' WHERE id=1",
        "UPDATE ops.customer_order SET status='GOODS_READY' WHERE id=1",
        "UPDATE ops.customer_order SET status='LOADED' WHERE id=1",
        "UPDATE ops.customer_order SET status='DISPATCHED' WHERE id=1",
        "UPDATE ref.market SET gps_enabled=true, timezone='Europe/Stockholm' WHERE id=1",
        "INSERT INTO ref.compliance_record (market_id,type,status,approved_on,reference) "
        "VALUES(1,'GPS_NOTICE','approved','2026-11-01','SYNTHETIC-T13')",
        "INSERT INTO hr.employee_shift_schedule "
        "(employee_id,warehouse_id,work_date,start_time,end_time,assigned_by,assigned_at) "
        "VALUES(5,1,'2026-11-10','07:00','17:00',3,'2026-11-08T09:00Z')",
        "INSERT INTO hr.driver_availability "
        "(driver_employee_id,work_date,available_from,available_to,max_driving_min,"
        "verified_by,verified_at,source,source_ref) VALUES "
        "(5,'2026-11-10','2026-11-10T07:00Z','2026-11-10T17:00Z',540,"
        "'synthetic-demo','2026-11-08T09:00Z','synthetic_demo','t13-avail-1')",
    )
    monkeypatch.setattr(gps_service.clock, "now", lambda: NOW)
    return api



def send(client: Api, point: object = POINT, *, key: str, user: int = 5):
    token = issue_token(user, {})
    return client.client.post(
        "/api/v1/trips/1/positions",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        json=point,
    )


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
    execute(
        gps.dsn,
        "UPDATE ref.compliance_record SET status='missing' WHERE type='GPS_NOTICE'",
    )
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
def test_US_GPS_01_AC2_invalid_point_rejected_without_write(
    gps: Api, invalid: dict[str, object]
) -> None:
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
    execute(
        gps.dsn,
        "UPDATE ops.delivery_trip SET assigned_dispatcher_employee_id=NULL WHERE id=1",
    )
    response = gps.get("/gps/live", 2)
    assert response.status_code == 200 and response.json() == []


def test_US_GPS_02_AC4_historical_position_route_is_unmounted(gps: Api) -> None:
    assert_error(gps.get("/trips/1/positions", 2), 405, "VALIDATION_ERROR")
