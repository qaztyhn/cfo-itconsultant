"""T13 Round 3 single-point HTTP/PG acceptance (synthetic market only)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.security import issue_token
from app.providers.routing_ors import RouteEstimate
from app.services import gps_service
from tests.integration import rows
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.dev2_helpers import transact
from tests.integration.hr_fixture import SETUP

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 10, 8, 30, tzinfo=UTC)
POINT = {"lat": 59.30, "lon": 18.10, "accuracy_m": 12.5, "recorded_at": "2026-11-10T08:05:00Z"}


@pytest.fixture
def prepared(api: Api, monkeypatch: pytest.MonkeyPatch) -> Api:  # noqa: F811
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
        "UPDATE ops.customer_order SET status='DISPATCHED',approved_plan_id=1,"
        "approved_at='2026-11-10T06:45Z',committed_date='2026-11-10',"
        "promise_start='2026-11-10T08:00Z',promise_end='2026-11-10T12:00Z' WHERE id=1",
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


def send(client: Api, point: object = POINT, *, key: str | None = None, user: int = 5, trip: int = 1):
    token = issue_token(user, {})
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.client.post(f"/api/v1/trips/{trip}/positions", headers=headers, json=point)


def test_US_GPS_01_AC1_one_point_202_writes_exactly_once_with_eta(prepared: Api) -> None:
    key = str(uuid4())
    first = send(prepared, key=key)
    assert first.status_code == 202, first.text
    ack = first.json()
    assert ack["accepted"] == 1 and ack["trip_id"] == 1 and ack["provider"] == "fallback"
    assert datetime.fromisoformat(ack["recorded_at"]) == datetime.fromisoformat("2026-11-10T08:05:00Z")
    assert fetch(prepared.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 1
    assert fetch(prepared.dsn, "SELECT count(*) FROM ops.eta_forecast")[0][0] == 1
    assert fetch(prepared.dsn, "SELECT source,route_source FROM ops.vehicle_position")[0] == (
        "driver_tap", "fallback"
    )
    repeated = send(prepared, key=key)
    assert repeated.status_code == 202 and repeated.json() == ack
    assert fetch(prepared.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 1
    assert fetch(prepared.dsn, "SELECT count(*) FROM ops.eta_forecast")[0][0] == 1
    changed = send(prepared, {**POINT, "lat": 59.31}, key=key)
    assert_error(changed, 409, "IDEMPOTENCY_CONFLICT")
    assert fetch(prepared.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 1


def test_US_GPS_01_AC2_batch_without_key_wrong_owner_or_shift_is_denied(prepared: Api) -> None:
    assert_error(send(prepared, {"positions": [POINT]}, key=str(uuid4())), 422, "VALIDATION_ERROR")
    assert_error(send(prepared), 422, "VALIDATION_ERROR")
    assert_error(send(prepared, key=str(uuid4()), user=2), 403, "FORBIDDEN")
    assert_error(send(prepared, key=str(uuid4()), user=6), 403, "FORBIDDEN")
    # User is a driver but trip belongs to another driver: 404, no PII or coordinates.
    execute(prepared.dsn, "UPDATE ops.delivery_trip SET driver_employee_id=2 WHERE id=1")
    assert_error(send(prepared, key=str(uuid4())), 404, "NOT_FOUND")
    execute(prepared.dsn, "UPDATE ops.delivery_trip SET driver_employee_id=5 WHERE id=1")
    execute(prepared.dsn, "DELETE FROM hr.driver_availability WHERE driver_employee_id=5")
    assert_error(send(prepared, key=str(uuid4())), 409, "NOT_ON_TRIP")
    assert fetch(prepared.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


def test_US_GPS_01_AC3_not_on_road_fails_closed(prepared: Api) -> None:
    execute(
        prepared.dsn,
        "UPDATE ops.delivery_trip SET status='completed',"
        "ended_at='2026-11-10T08:20Z' WHERE id=1",
    )
    assert_error(send(prepared, key=str(uuid4())), 409, "NOT_ON_TRIP")


def test_US_GPS_02_AC1_assigned_dispatcher_only_live_and_hidden_after_trip_end(prepared: Api) -> None:
    assert send(prepared, key=str(uuid4())).status_code == 202
    visible = prepared.get("/gps/live", 2)
    assert visible.status_code == 200 and len(visible.json()) == 1
    item = visible.json()[0]
    assert item["trip_id"] == 1 and item["order_id"] == 1 and item["vehicle_code"] == "GPS-1"
    assert item["last_position"] == {"lat": 59.3, "lon": 18.1}
    assert item["updated_at"] and item["forecast_eta"]
    assert_error(prepared.get("/gps/live", 6), 403, "FORBIDDEN")
    assert_error(prepared.get("/trips/1/positions", 2), 404, "NOT_FOUND")
    execute(prepared.dsn, "UPDATE ops.delivery_trip SET assigned_dispatcher_employee_id=NULL WHERE id=1")
    assert prepared.get("/gps/live", 2).json() == []
    execute(prepared.dsn, "UPDATE ops.delivery_trip SET assigned_dispatcher_employee_id=2,"
        "status='completed',ended_at='2026-11-10T09:00Z' WHERE id=1")
    assert prepared.get("/gps/live", 2).json() == []


def test_US_GPS_03_AC1_purge_terminal_order_and_no_history_route(prepared: Api) -> None:
    assert send(prepared, key=str(uuid4())).status_code == 202
    assert transact(prepared.dsn, lambda s: gps_service.purge_order(s, 1)) == 1
    assert fetch(prepared.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0
    assert_error(prepared.get("/trips/1/positions", 2), 404, "NOT_FOUND")


def test_US_GPS_01_AC1_ors_route_provenance_on_postgresql(
    prepared: Api, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ors(*_args: object, **_kwargs: object) -> RouteEstimate:
        return RouteEstimate(Decimal("3.20"), 6, "ors")

    monkeypatch.setattr(gps_service, "route_with_fallback", ors)
    response = send(prepared, key=str(uuid4()))
    assert response.status_code == 202, response.text
    assert response.json()["provider"] == "ors"
    assert fetch(
        prepared.dsn,
        "SELECT route_source,remaining_km,remaining_min FROM ops.vehicle_position",
    )[0] == (
        "ors", Decimal("3.2"), 6
    )


def test_US_GPS_01_AC3_no_transactional_state_leak_on_invalid_timestamp(prepared: Api) -> None:
    value = {**POINT, "recorded_at": "2026-11-10T18:05:00Z"}
    assert_error(send(prepared, value, key=str(uuid4())), 409, "NOT_ON_TRIP")
    assert fetch(prepared.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0
    assert fetch(prepared.dsn, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 0
