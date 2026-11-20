"""M6 PostgreSQL tests: scoped execution, driver safety and transaction rollback."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core import clock
from app.core.errors import DomainError
from app.core.security import issue_token
from app.domain.models.ops import TripStop, VehiclePosition
from app.providers.routing_ors import RouteEstimate
from app.services import execution_service, gps_service, notify_service, planning_service, risk_service
from tests.integration import rows
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.hr_fixture import DISPATCHER, DRIVER, SALES, SETUP, WAREHOUSE, ZZ_WAREHOUSE

pytestmark = pytest.mark.integration
REAL_RECORD_POINT = gps_service.record_point
REAL_PURGE_ORDER = gps_service.purge_order

SEED = (
    *SETUP,
    "INSERT INTO ref.customer (market_id, external_ref, type, name) VALUES "
    "(1, 'EXE-CLIENT', 'business', 'Synthetic client')",
    "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
    "VALUES (1, 'SE-M6-D2', 'Synthetic', 'DriverTwo', 'DRIVER', '2025-01-01')",
    "INSERT INTO hr.employee_assignment (employee_id, location_id, start_date) "
    "VALUES (11, 1, '2025-01-01')",
    "INSERT INTO hr.driver_staff (employee_id, home_warehouse_id, licence_class, licence_expires_on) "
    "VALUES (11, 1, 'CE', '2027-01-31')",
    "INSERT INTO ref.app_user (employee_id, email, password_hash, roles) "
    "VALUES (11, 'driver-two@cfo.test', 'not-a-real-hash', '{driver}')",
    "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, capacity_m3,"
    " required_licence, max_permissible_mass_kg, regulation_561_scope) VALUES "
    "(1, 'V-EX-1', 'SYN-1', 'Synthetic truck 1', 9000, 30, 'C', 12000, 'in_scope'), "
    "(1, 'V-EX-2', 'SYN-2', 'Synthetic truck 2', 9000, 30, 'C', 12000, 'in_scope')",
    "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id,"
    "contact_name, delivery_address, delivery_lat, delivery_lon, date_mode, date_to,"
    "order_date, currency, submitted_at, status) VALUES "
    "('SE-M6', 1, 'EX-ORDER', 1, 'Demo recipient', 'Synthetic delivery site', 59.0, 18.0,"
    "'latest', '2026-11-10', '2026-11-04T09:00Z', 'SEK', '2026-11-04T09:00Z', 'APPROVED')",
    rows.run_sql(1, 1),
    rows.plan_sql(1, 1, 1, "approved"),
    rows.plan_vehicle_sql(1, 1, 1, 5),
    rows.plan_vehicle_sql(1, 2, 2, 11),
    "UPDATE plan.fulfilment_plan SET vehicle_count=2 WHERE id=1",
    "UPDATE ops.customer_order SET approved_plan_id=1 WHERE id=1",
    "INSERT INTO ops.delivery_trip (plan_vehicle_id, warehouse_id, vehicle_id, driver_employee_id,"
    " depart_planned_at) VALUES "
    "(1, 1, 1, 5, '2026-11-10T08:00Z'), (2, 1, 2, 11, '2026-11-10T08:00Z')",
    "INSERT INTO ops.trip_stop (trip_id, seq, order_id, eta_planned_at) VALUES "
    "(1, 1, 1, '2026-11-10T10:00Z'), (2, 1, 1, '2026-11-10T10:30Z')",
)


@pytest.fixture
def execution_api(api: Api, monkeypatch: pytest.MonkeyPatch) -> Api:  # noqa: F811
    clock.set_now(datetime(2026, 11, 10, 15, 0, tzinfo=UTC))
    execute(api.dsn, *SEED)

    async def record_point(session, trip_id, point, source):
        assert session.in_transaction()
        session.add(
            VehiclePosition(
                trip_id=trip_id,
                vehicle_id=trip_id,
                lat=point["lat"],
                lon=point["lon"],
                accuracy_m=point["accuracy_m"],
                recorded_at=point["recorded_at"],
                source=source,
                remaining_km=Decimal("1.0"),
                remaining_min=10,
                route_source="haversine_estimate",
            )
        )
        await session.flush()
        return SimpleNamespace(
            recorded_at=point["recorded_at"],
            remaining_km=Decimal("1.0"),
            remaining_min=10,
            provider="fallback",
        )

    async def purge_order(session, order_id):
        await session.execute(
            delete(VehiclePosition).where(
                VehiclePosition.trip_id.in_(select(TripStop.trip_id).where(TripStop.order_id == order_id))
            )
        )

    monkeypatch.setattr(gps_service, "record_point", record_point, raising=False)
    monkeypatch.setattr(gps_service, "purge_order", purge_order, raising=False)
    try:
        yield api
    finally:
        clock.set_now(None)


GPS_DUTY = (
    "UPDATE ref.market SET gps_enabled=true WHERE id=1",
    "INSERT INTO hr.employee_shift_schedule (employee_id,warehouse_id,work_date,start_time,end_time,"
    "assigned_by,assigned_at) VALUES (5,1,'2026-11-10','07:00','17:00',3,'2026-11-08T09:00Z'), "
    "(11,1,'2026-11-10','07:00','17:00',3,'2026-11-08T09:00Z')",
)


def positions(db: str) -> list[tuple[int, str]]:
    rows_ = fetch(
        db,
        "SELECT trip_id, to_char(recorded_at AT TIME ZONE 'UTC','HH24:MI') AS t "
        "FROM ops.vehicle_position ORDER BY 1,2",
    )
    return [(r["trip_id"], r["t"]) for r in rows_]


def send(
    client: Api,
    actor: int,
    kind: str,
    at: str,
    payload: dict[str, object] | None = None,
    key: str | None = None,
):
    if (
        kind in {"DELIVERED", "FAILED"}
        and payload
        and ("recipient_name" in payload or "failure_reason" in payload)
    ):
        payload = {
            **payload,
            "position": payload.get(
                "position",
                {
                    "lat": 59.0,
                    "lon": 18.0,
                    "accuracy_m": 10,
                    "recorded_at": at,
                },
            ),
        }
    return client.client.post(
        "/api/v1/orders/1/events",
        headers={
            "Authorization": "Bearer " + issue_token(actor, {}),
            "Idempotency-Key": key or str(uuid4()),
        },
        json={"event_type": kind, "occurred_at": at, "payload": payload or {}},
    )


async def verified_risk(order_id: int, trigger: str, *, session: object = None) -> dict[str, object]:
    assert order_id == 1 and trigger.startswith("event:")
    assert session is not None, "M7 must run in the caller's transaction (session-aware)"
    return {"status": "ON_TRACK", "color": "green", "forecast_eta": "2026-11-10T10:00:00Z"}


def test_US_EXE_01_AC1_driver_trip_list_only_own_safe_fields(execution_api: Api) -> None:
    response = execution_api.get("/driver/trips", DRIVER, date="2026-11-10")
    assert response.status_code == 200, response.text
    trips = response.json()["items"]
    assert len(trips) == 1
    assert {row["vehicle_code"] for row in trips} == {"V-EX-1"}
    other = execution_api.get("/driver/trips", 14, date="2026-11-10")
    assert other.status_code == 200
    assert [row["vehicle_code"] for row in other.json()["items"]] == ["V-EX-2"]
    assert_error(execution_api.get("/driver/trips/2", DRIVER), 404, "NOT_FOUND")
    assert trips[0]["stops"][0]["delivery_address"] == "Synthetic delivery site"
    assert "total_amount" not in response.text
    assert "latitude" not in response.text and "gps" not in response.text
    assert_error(execution_api.get("/driver/trips", DISPATCHER), 403, "FORBIDDEN")
    assert_error(execution_api.get("/driver/trips/1", SALES), 403, "FORBIDDEN")
    assert_error(execution_api.get("/driver/trips/999", DRIVER), 404, "NOT_FOUND")
    assert execution_api.get("/driver/trips", DRIVER, date="2026-11-11").json() == {"items": []}


def test_US_WH_04_AC1_AC3_start_prep_and_idempotent_replay(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    key = str(uuid4())
    first = send(execution_api, WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3}, key)
    assert first.status_code == 200, first.text
    assert first.json()["order_status"] == "PREPARING"
    again = send(execution_api, WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3}, key)
    assert again.status_code == 200 and again.json() == first.json()
    assert_error(
        send(execution_api, WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 4}, key),
        409,
        "IDEMPOTENCY_CONFLICT",
    )
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.milestone_event")[0]["n"] == 1


def test_US_WH_04_AC5_AC6_AC8_labour_pause_resume(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    assert_error(
        send(execution_api, WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z"), 422, "VALIDATION_ERROR"
    )
    assert (
        send(execution_api, WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3}).status_code
        == 200
    )
    assert send(execution_api, WAREHOUSE, "PREP_PAUSED", "2026-11-10T09:00:00Z").status_code == 200
    assert_error(
        send(execution_api, WAREHOUSE, "PREP_PAUSED", "2026-11-10T09:10:00Z"), 409, "ILLEGAL_TRANSITION"
    )
    assert_error(
        send(execution_api, WAREHOUSE, "PREP_RESUMED", "2026-11-10T13:00:00Z"), 422, "VALIDATION_ERROR"
    )
    assert (
        send(execution_api, WAREHOUSE, "PREP_RESUMED", "2026-11-10T13:00:00Z", {"crew_size": 2}).status_code
        == 200
    )
    response = send(execution_api, WAREHOUSE, "GOODS_READY", "2026-11-10T14:30:00Z")
    assert response.status_code == 200, response.text
    assert response.json()["order_status"] == "GOODS_READY"
    assert response.json()["actual_labour_hours"] == "9.000"
    payload = fetch(
        execution_api.dsn, "SELECT payload FROM ops.milestone_event WHERE event_type='GOODS_READY'"
    )[0]["payload"]
    payload = json.loads(payload) if isinstance(payload, str) else payload
    assert payload["actual_labour_hours"] == "9.000"
    assert len(payload["labour_segments"]) == 2


def test_US_WH_04_AC2_ordering_and_multi_vehicle_loading(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    assert_error(
        send(execution_api, WAREHOUSE, "LOADED", "2026-11-10T07:00:00Z", {"trip_id": 1}),
        409,
        "ILLEGAL_TRANSITION",
    )
    assert_error(
        send(
            execution_api,
            WAREHOUSE,
            "SHORTAGE",
            "2026-11-10T06:55:00Z",
            {"sku": "SE-SYN", "qty_missing": 1},
        ),
        409,
        "ILLEGAL_TRANSITION",
    )
    send(execution_api, WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3})
    assert_error(
        send(execution_api, WAREHOUSE, "GOODS_READY", "2026-11-10T06:00:00Z"), 409, "ILLEGAL_TRANSITION"
    )
    send(execution_api, WAREHOUSE, "GOODS_READY", "2026-11-10T07:30:00Z")
    one = send(execution_api, WAREHOUSE, "LOADED", "2026-11-10T08:00:00Z", {"trip_id": 1})
    assert one.status_code == 200 and one.json()["order_status"] == "GOODS_READY"
    two = send(execution_api, WAREHOUSE, "LOADED", "2026-11-10T08:05:00Z", {"trip_id": 2})
    assert two.status_code == 200 and two.json()["order_status"] == "LOADED"
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.milestone_event")[0]["n"] == 4


def test_US_WH_04_AC1_AC2_AC4_frozen_clock_keeps_seconds_and_records_each_trip(
    execution_api: Api,
) -> None:
    clock.init_from_settings("2026-11-10T10:05:00+01:00")
    execute(
        execution_api.dsn,
        "UPDATE ops.customer_order SET promise_end='2026-11-10T13:00Z' WHERE id=1",
        "UPDATE plan.fulfilment_plan SET workload="
        "jsonb_build_object('planned_start_prep','2026-11-10T05:00:00Z') WHERE id=1",
    )
    queue_path = "/warehouses/1/prep-queue"
    initial = execution_api.get(queue_path, WAREHOUSE)
    assert initial.status_code == 200, initial.text
    assert initial.json()["date"] == "2026-11-10"
    assert [order["status"] for order in initial.json()["orders"]] == ["APPROVED"]
    assert initial.json()["orders"][0]["prep_window"]["start"] is None

    steps = (
        ("START_PREP", "2026-11-10T10:05:10+01:00", {"crew_size": 3}, "PREPARING", []),
        ("GOODS_READY", "2026-11-10T10:05:40+01:00", {}, "GOODS_READY", []),
        ("LOADED", "2026-11-10T10:05:50+01:00", {"trip_id": 1}, "GOODS_READY", [1]),
        ("LOADED", "2026-11-10T10:06:00+01:00", {"trip_id": 2}, "LOADED", [1, 2]),
    )
    for version, (kind, at, payload, expected_status, loaded_trips) in enumerate(steps, start=1):
        response = send(execution_api, WAREHOUSE, kind, at, payload)
        assert response.status_code == 200, response.text
        assert response.json()["order_status"] == expected_status
        assert response.json()["risk"]["version"] == version
        refreshed = execution_api.get(queue_path, WAREHOUSE)
        assert refreshed.status_code == 200, refreshed.text
        order = refreshed.json()["orders"][0]
        assert order["status"] == expected_status
        assert [trip["trip_id"] for trip in order["loading"] if trip["loaded"]] == loaded_trips

    events = fetch(
        execution_api.dsn,
        "SELECT event_type, occurred_at, trip_id FROM ops.milestone_event "
        "WHERE order_id = 1 ORDER BY occurred_at, id",
    )
    assert [(row["event_type"], row["occurred_at"], row["trip_id"]) for row in events] == [
        (kind, datetime.fromisoformat(at), payload.get("trip_id")) for kind, at, payload, _, _ in steps
    ]


def test_US_NOT_01_AC1_execution_outbox_rolls_back_with_milestone_and_dedupes(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Real PostgreSQL outbox in the SAME transaction as the delivery status change.
    execute(
        execution_api.dsn,
        "UPDATE ref.customer SET email='demo@cfo.test' WHERE id=1",
        "UPDATE ops.customer_order SET promise_start='2026-11-10T08:00:00Z',"
        "promise_end='2026-11-10T11:00:00Z' WHERE id=1",
    )

    async def verified_driver(*_args: object) -> None:
        return None

    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    monkeypatch.setattr(execution_service, "_driver_gate", verified_driver)
    for who, event, at, payload in (
        (WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3}),
        (WAREHOUSE, "GOODS_READY", "2026-11-10T07:30:00Z", {}),
        (WAREHOUSE, "LOADED", "2026-11-10T08:00:00Z", {"trip_id": 1}),
        (WAREHOUSE, "LOADED", "2026-11-10T08:05:00Z", {"trip_id": 2}),
    ):
        resp = send(execution_api, who, event, at, payload)
        assert resp.status_code == 200, resp.text

    original_enqueue = notify_service.enqueue

    async def abort(order_id: int, template: str, plan_id: int | None = None, **kw: object) -> int:
        assert kw.get("session") is not None
        await original_enqueue(order_id, template, plan_id, session=kw["session"])
        raise DomainError("PLAN_NOT_APPROVABLE", "Synthetic transaction rollback test.")

    monkeypatch.setattr(notify_service, "enqueue", abort)
    failed = send(execution_api, DRIVER, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1})
    assert_error(failed, 409, "PLAN_NOT_APPROVABLE")
    assert fetch(execution_api.dsn, "SELECT count(*) FROM ops.notification")[0][0] == 0
    assert fetch(execution_api.dsn, "SELECT count(*) FROM ops.milestone_event")[0][0] == 4
    order_status = fetch(execution_api.dsn, "SELECT status::text FROM ops.customer_order WHERE id=1")[0][0]
    assert order_status == "LOADED"

    monkeypatch.setattr(notify_service, "enqueue", original_enqueue)
    first = send(execution_api, DRIVER, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1})
    assert first.status_code == 200, first.text
    second = send(execution_api, 14, "DISPATCHED", "2026-11-10T08:12:00Z", {"trip_id": 2})
    assert second.status_code == 200, second.text
    rows = fetch(execution_api.dsn, "SELECT template FROM ops.notification")
    assert [row["template"] for row in rows] == ["DISPATCHED"]


def test_US_WH_04_AC4_missing_risk_dependency_rolls_back(execution_api: Api) -> None:
    execute(execution_api.dsn, "UPDATE ops.customer_order SET promise_end='2026-11-10T17:00Z' WHERE id=1")
    response = send(execution_api, WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3})
    assert_error(response, 409, "PLAN_NOT_APPROVABLE")
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.milestone_event")[0]["n"] == 0
    status = fetch(execution_api.dsn, "SELECT status::text AS status FROM ops.customer_order")
    assert status[0]["status"] == "APPROVED"
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.idempotency_key")[0]["n"] == 0


def test_US_WH_04_AC2_AC5_RBAC_and_timestamp_guards(execution_api: Api) -> None:
    body = {"crew_size": 3}
    assert_error(send(execution_api, SALES, "START_PREP", "2026-11-10T07:00:00Z", body), 403, "FORBIDDEN")
    assert_error(
        send(execution_api, ZZ_WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", body), 404, "NOT_FOUND"
    )
    assert_error(
        send(execution_api, WAREHOUSE, "START_PREP", "2026-11-10T15:06:00Z", body), 422, "VALIDATION_ERROR"
    )
    assert_error(
        send(execution_api, WAREHOUSE, "START_PREP", "2026-11-10T07:00:00", body), 422, "VALIDATION_ERROR"
    )


def test_US_WH_04_AC1_prep_queue_scoped(execution_api: Api) -> None:
    response = execution_api.get("/warehouses/1/prep-queue", WAREHOUSE, date="2026-11-10")
    assert response.status_code == 200, response.text
    assert response.json()["orders"][0]["order_no"] == "SE-M6"
    assert "contact_name" not in response.text
    assert_error(execution_api.get("/warehouses/3/prep-queue", WAREHOUSE), 404, "NOT_FOUND")
    assert_error(execution_api.get("/warehouses/1/prep-queue", DRIVER), 403, "FORBIDDEN")
    legacy = execution_api.get("/prep-queue", WAREHOUSE, warehouse_id=1, date="2026-11-10")
    assert legacy.status_code == 200 and legacy.json() == response.json()  # alias, same contract


def test_US_EXE_02_AC4_outside_shift_and_incomplete_history_denied(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    send(execution_api, WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3})
    send(execution_api, WAREHOUSE, "GOODS_READY", "2026-11-10T07:30:00Z")
    send(execution_api, WAREHOUSE, "LOADED", "2026-11-10T08:00:00Z", {"trip_id": 1})
    send(execution_api, WAREHOUSE, "LOADED", "2026-11-10T08:05:00Z", {"trip_id": 2})
    assert_error(
        send(execution_api, DISPATCHER, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1}),
        403,
        "FORBIDDEN",
    )
    assert_error(
        send(execution_api, DRIVER, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1}),
        409,
        "PLAN_NOT_APPROVABLE",
    )
    execute(
        execution_api.dsn,
        "INSERT INTO hr.employee_shift_schedule "
        "(employee_id, warehouse_id, work_date, start_time, end_time, status, assigned_by, assigned_at) "
        "VALUES (5, 1, '2026-11-10', '07:00', '16:00', 'scheduled', 3, '2026-11-04T08:00Z')",
    )
    assert_error(
        send(execution_api, DRIVER, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1}),
        409,
        "PLAN_NOT_APPROVABLE",
    )
    trip_state = fetch(execution_api.dsn, "SELECT status::text AS status FROM ops.delivery_trip")
    assert trip_state[0]["status"] == "loading"
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.proof_of_delivery")[0]["n"] == 0


def test_US_EXE_02_AC3_failure_reason_is_required(execution_api: Api) -> None:
    assert_error(
        send(execution_api, DRIVER, "FAILED", "2026-11-10T10:00:00Z", {"trip_id": 1}), 422, "VALIDATION_ERROR"
    )
    assert_error(
        send(
            execution_api,
            DRIVER,
            "FAILED",
            "2026-11-10T10:00:00Z",
            {"trip_id": 1, "failure_reason": "custom_reason"},
        ),
        422,
        "VALIDATION_ERROR",
    )


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("DELIVERED", {"trip_id": 1, "recipient_name": "Synthetic recipient"}),
        ("FAILED", {"trip_id": 1, "failure_reason": "customer_absent"}),
    ],
)
def test_US_EXE_02_AC8_completion_without_position_preserves_transaction(
    execution_api: Api, kind: str, payload: dict[str, object]
) -> None:
    response = execution_api.client.post(
        "/api/v1/orders/1/events",
        headers={"Authorization": "Bearer " + issue_token(DRIVER, {}), "Idempotency-Key": str(uuid4())},
        json={"event_type": kind, "occurred_at": "2026-11-10T09:30:00Z", "payload": payload},
    )
    assert_error(response, 422, "VALIDATION_ERROR")
    assert response.json()["error"]["details"]["reason"] == "position_required"
    assert (
        fetch(execution_api.dsn, "SELECT status::text FROM ops.customer_order WHERE id=1")[0][0] == "APPROVED"
    )
    for table in ("proof_of_delivery", "milestone_event", "vehicle_position", "idempotency_key"):
        assert fetch(execution_api.dsn, f"SELECT count(*) FROM ops.{table}")[0][0] == 0


def test_US_EXE_05_AC1_AC2_AC3_incident_scope_alert_and_eta_rules(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as dispatch_setup:
        _dispatch_both_vehicles(execution_api, dispatch_setup, [])
    _enable_real_gps(execution_api, monkeypatch)
    clock.set_now(datetime(2026, 11, 10, 9, 45, tzinfo=UTC))
    execute(
        execution_api.dsn,
        "UPDATE ops.customer_order SET committed_date='2026-11-10',"
        "promise_start='2026-11-10T09:00Z',promise_end='2026-11-10T12:00Z' WHERE id=1",
    )

    async def assigned_driver(session, actor, trip, market, at):
        if trip.driver_employee_id != actor.employee_id:
            raise DomainError("FORBIDDEN", "Driver is not assigned to this trip.")

    monkeypatch.setattr(execution_service, "_driver_gate", assigned_driver)
    at = "2026-11-10T09:30:00Z"
    assert_error(
        send(execution_api, DRIVER, "DRIVER_INCIDENT", at, {"trip_id": 2, "reason": "traffic_or_accident"}),
        403,
        "FORBIDDEN",
    )
    assert_error(
        send(execution_api, DRIVER, "DRIVER_INCIDENT", at, {"trip_id": 1, "reason": "other"}),
        422,
        "VALIDATION_ERROR",
    )
    ordinary = send(
        execution_api,
        DRIVER,
        "DRIVER_INCIDENT",
        at,
        {"trip_id": 1, "reason": "other", "note": "Synthetic incident"},
    )
    assert ordinary.status_code == 200, ordinary.text
    assert ordinary.json()["risk"] is None
    assert fetch(execution_api.dsn, "SELECT version FROM ops.eta_forecast") == []
    with_position = send(
        execution_api,
        DRIVER,
        "DRIVER_INCIDENT",
        "2026-11-10T09:35:00Z",
        {
            "trip_id": 1,
            "reason": "traffic_or_accident",
            "note": None,
            "position": {"lat": 59.0, "lon": 18.0, "accuracy_m": 10, "recorded_at": "2026-11-10T09:35:00Z"},
        },
    )
    assert with_position.status_code == 200, with_position.text
    forecast_sql = "SELECT version, trigger, forecast_eta FROM ops.eta_forecast ORDER BY version"
    forecasts = fetch(execution_api.dsn, forecast_sql)
    assert len(forecasts) == 1
    forecast = forecasts[0]
    assert (forecast["version"], forecast["trigger"]) == (1, "event:DRIVER_INCIDENT")
    risk = with_position.json()["risk"]
    assert risk["version"] == forecast["version"]
    assert datetime.fromisoformat(risk["forecast_eta"]) == forecast["forecast_eta"]
    breakdown = send(
        execution_api,
        DRIVER,
        "DRIVER_INCIDENT",
        "2026-11-10T09:40:00Z",
        {
            "trip_id": 1,
            "reason": "vehicle_breakdown",
            "position": {"lat": 59.0, "lon": 18.0, "accuracy_m": 10, "recorded_at": "2026-11-10T09:40:00Z"},
        },
    )
    assert breakdown.status_code == 200, breakdown.text
    assert breakdown.json()["risk"] is None
    assert fetch(execution_api.dsn, forecast_sql) == forecasts
    alerts = fetch(
        execution_api.dsn, "SELECT type,level,message FROM ops.alert WHERE type='DRIVER_INCIDENT' ORDER BY id"
    )
    assert [(a["type"], a["level"]) for a in alerts] == [
        ("DRIVER_INCIDENT", "warning"),
        ("DRIVER_INCIDENT", "warning"),
        ("DRIVER_INCIDENT", "critical"),
    ]
    assert "ETA không xác định" in alerts[-1]["message"]
    assert positions(execution_api.dsn) == [(1, "09:35"), (1, "09:40")]
    assert (
        fetch(execution_api.dsn, "SELECT status::text FROM ops.customer_order WHERE id=1")[0][0]
        == "DISPATCHED"
    )
    assert fetch(execution_api.dsn, "SELECT count(*) FROM plan.planning_run")[0][0] == 1
    milestones = fetch(execution_api.dsn, "SELECT payload::text FROM ops.milestone_event ORDER BY id")
    assert all("position" not in row[0] and "59.0" not in row[0] for row in milestones)


def test_US_EXE_02_AC5_AC7_partial_delivery_single_notice_and_gps_purge(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bypass missing external gate *only in this integration test* to test order aggregation."""

    async def test_driver_gate(*_args: object) -> None:
        return None

    messages: list[str] = []
    triggers: list[str] = []

    async def test_enqueue(order_id: int, template: str, plan_id: int | None = None, **kw: object) -> int:
        assert order_id == 1 and plan_id == 1
        assert kw.get("session") is not None  # Outbox shares milestone transaction.
        messages.append(template)
        return len(messages)

    async def test_replan(order_id: int, trigger: str, **_kwargs: object) -> int:
        assert order_id == 1
        triggers.append(trigger)
        return 2

    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    monkeypatch.setattr(notify_service, "enqueue", test_enqueue)
    monkeypatch.setattr(execution_service, "_driver_gate", test_driver_gate)
    monkeypatch.setattr(planning_service, "suggest_replan", test_replan)

    steps = (
        (WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3}),
        (WAREHOUSE, "GOODS_READY", "2026-11-10T07:30:00Z", {}),
        (WAREHOUSE, "LOADED", "2026-11-10T08:00:00Z", {"trip_id": 1}),
        (WAREHOUSE, "LOADED", "2026-11-10T08:05:00Z", {"trip_id": 2}),
        (DRIVER, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1}),
        (14, "DISPATCHED", "2026-11-10T08:12:00Z", {"trip_id": 2}),
    )
    for actor, kind, at, data in steps:
        response = send(execution_api, actor, kind, at, data)
        assert response.status_code == 200, response.text
    assert messages == ["DISPATCHED"]

    execute(
        execution_api.dsn,
        *GPS_DUTY,
        "INSERT INTO ops.vehicle_position (trip_id, vehicle_id, lat, lon, recorded_at, source) "
        "VALUES (1, 1, 59, 18, '2026-11-10T08:30Z', 'simulator'), "
        "(2, 2, 59, 18, '2026-11-10T08:31Z', 'simulator')",
    )
    first = send(
        execution_api,
        DRIVER,
        "DELIVERED",
        "2026-11-10T09:30:00Z",
        {"trip_id": 1, "recipient_name": "Synthetic recipient"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["order_status"] == "DISPATCHED"
    assert positions(execution_api.dsn) == [(1, "08:30"), (1, "09:30"), (2, "08:31")]
    assert messages == ["DISPATCHED"]

    second = send(
        execution_api,
        14,
        "FAILED",
        "2026-11-10T09:35:00Z",
        {"trip_id": 2, "failure_reason": "customer_absent"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["order_status"] == "FAILED"
    assert messages == ["DISPATCHED", "FAILED"]
    assert triggers == []  # R3: failed delivery never creates a replan suggestion.
    assert positions(execution_api.dsn) == [(1, "08:30"), (1, "09:30"), (2, "08:31"), (2, "09:35")]
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.proof_of_delivery")[0]["n"] == 2
    assert (
        fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.alert WHERE type='DELIVERY_FAILED'")[0]["n"]
        == 1
    )


def test_US_WH_04_AC1_assigned_shift_supervisor_can_record_event(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    execute(
        execution_api.dsn,
        "UPDATE hr.warehouse_staff SET role='supervisor' WHERE employee_id=4",
        "UPDATE ref.app_user SET roles='{warehouse}' WHERE id=4",
    )
    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    result = send(execution_api, 4, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 2})
    assert result.status_code == 200, result.text
    assert result.json()["order_status"] == "PREPARING"


def test_US_EXE_02_AC4_expired_licence_denies_dispatch(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    for event, at, payload in (
        ("START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3}),
        ("GOODS_READY", "2026-11-10T07:30:00Z", {}),
        ("LOADED", "2026-11-10T08:00:00Z", {"trip_id": 1}),
        ("LOADED", "2026-11-10T08:05:00Z", {"trip_id": 2}),
    ):
        assert send(execution_api, WAREHOUSE, event, at, payload).status_code == 200
    execute(
        execution_api.dsn,
        "UPDATE hr.driver_staff SET licence_class='B' WHERE employee_id=5",
    )
    assert_error(
        send(execution_api, DRIVER, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1}),
        409,
        "PLAN_NOT_APPROVABLE",
    )
    execute(
        execution_api.dsn,
        "UPDATE hr.driver_staff SET licence_class='CE', "
        "licence_expires_on='2026-11-09' WHERE employee_id=5",
    )
    assert_error(
        send(execution_api, DRIVER, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1}),
        422,
        "LICENCE_EXPIRED",
    )
    assert_error(
        send(execution_api, 14, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1}),
        403,
        "FORBIDDEN",
    )
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.proof_of_delivery")[0]["n"] == 0


def test_US_EXE_02_AC5_prior_cancelled_trip_does_not_block_current_plan(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Historic stops remain visible for audit, but never count toward current plan aggregation."""
    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    execute(
        execution_api.dsn,
        "INSERT INTO ops.delivery_trip (warehouse_id, vehicle_id, driver_employee_id, "
        "status, depart_planned_at) VALUES "
        "(1, 1, 5, 'cancelled', '2026-11-10T08:00Z')",
        "INSERT INTO ops.trip_stop (trip_id, seq, order_id, eta_planned_at, status) "
        "VALUES (3, 1, 1, '2026-11-10T10:00Z', 'cancelled')",
    )
    for event, at, payload in (
        ("START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3}),
        ("GOODS_READY", "2026-11-10T07:30:00Z", {}),
        ("LOADED", "2026-11-10T08:00:00Z", {"trip_id": 1}),
        ("LOADED", "2026-11-10T08:05:00Z", {"trip_id": 2}),
    ):
        result = send(execution_api, WAREHOUSE, event, at, payload)
        assert result.status_code == 200, result.text
    assert result.json()["order_status"] == "LOADED"
    assert (
        fetch(
            execution_api.dsn,
            "SELECT status::text AS status FROM ops.delivery_trip WHERE id=3",
        )[
            0
        ]["status"]
        == "cancelled"
    )


def test_M6_1_two_vehicles_deliver_same_order_one_pod_per_trip_stop(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DEC-OWNER-20261109 M6-1: two successful PODs for one multi-vehicle order, one per trip stop."""

    async def test_driver_gate(*_args: object) -> None:
        return None

    async def test_enqueue(order_id: int, template: str, plan_id: int | None = None, **kw: object) -> int:
        assert kw.get("session") is not None
        return 1

    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    monkeypatch.setattr(notify_service, "enqueue", test_enqueue)
    monkeypatch.setattr(execution_service, "_driver_gate", test_driver_gate)
    steps = (
        (WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3}),
        (WAREHOUSE, "GOODS_READY", "2026-11-10T07:30:00Z", {}),
        (WAREHOUSE, "LOADED", "2026-11-10T08:00:00Z", {"trip_id": 1}),
        (WAREHOUSE, "LOADED", "2026-11-10T08:05:00Z", {"trip_id": 2}),
        (DRIVER, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1}),
        (14, "DISPATCHED", "2026-11-10T08:12:00Z", {"trip_id": 2}),
        (DRIVER, "DELIVERED", "2026-11-10T09:30:00Z", {"trip_id": 1, "recipient_name": "Synthetic one"}),
        (14, "DELIVERED", "2026-11-10T09:35:00Z", {"trip_id": 2, "recipient_name": "Synthetic two"}),
    )
    for actor, kind, at, data in steps:
        response = send(execution_api, actor, kind, at, data)
        assert response.status_code == 200, response.text
    assert response.json()["order_status"] == "DELIVERED"
    pods = fetch(
        execution_api.dsn,
        "SELECT trip_stop_id, result FROM ops.proof_of_delivery WHERE order_id=1 ORDER BY trip_stop_id",
    )
    assert [p["result"] for p in pods] == ["delivered", "delivered"]
    assert len({p["trip_stop_id"] for p in pods}) == 2


def test_US_EXE_02_AC2_completion_stores_distance_per_trip_without_coordinate_leak(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dispatch_both_vehicles(execution_api, monkeypatch, [])
    point = {"lat": 59.001, "lon": 18.0, "accuracy_m": 10, "recorded_at": "2026-11-10T09:30:00Z"}
    first = send(
        execution_api,
        DRIVER,
        "DELIVERED",
        "2026-11-10T09:30:00Z",
        {"trip_id": 1, "recipient_name": "Synthetic one", "position": point},
    )
    assert first.status_code == 200, first.text
    assert first.json()["order_status"] == "DISPATCHED"
    pod = fetch(execution_api.dsn, "SELECT trip_stop_id,site_distance_m FROM ops.proof_of_delivery")[0]
    assert pod["trip_stop_id"] == 1 and 110 <= pod["site_distance_m"] <= 112
    assert fetch(execution_api.dsn, "SELECT source FROM ops.vehicle_position")[0][0] == "driver_completion"
    milestone = fetch(
        execution_api.dsn, "SELECT payload::text FROM ops.milestone_event ORDER BY id DESC LIMIT 1"
    )[0][0]
    assert "position" not in milestone and "59.001" not in milestone
    second = send(
        execution_api,
        14,
        "DELIVERED",
        "2026-11-10T09:35:00Z",
        {"trip_id": 2, "recipient_name": "Synthetic two"},
    )
    assert second.status_code == 200 and second.json()["order_status"] == "DELIVERED"
    assert fetch(execution_api.dsn, "SELECT count(*) FROM ops.proof_of_delivery")[0][0] == 2
    assert fetch(execution_api.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == 0


def test_US_EXE_02_AC2_terminal_purge_and_pod_rollback_together(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dispatch_both_vehicles(execution_api, monkeypatch, [])
    first = send(
        execution_api,
        DRIVER,
        "DELIVERED",
        "2026-11-10T09:30:00Z",
        {"trip_id": 1, "recipient_name": "Synthetic one"},
    )
    assert first.status_code == 200, first.text
    before = fetch(execution_api.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0]
    assert before == 1

    async def fail_notify(*_args, **_kwargs):
        raise DomainError("PLAN_NOT_APPROVABLE", "Test notification failure.")

    monkeypatch.setattr(notify_service, "enqueue", fail_notify)
    response = send(
        execution_api,
        14,
        "DELIVERED",
        "2026-11-10T09:35:00Z",
        {"trip_id": 2, "recipient_name": "Synthetic two"},
    )
    assert_error(response, 409, "PLAN_NOT_APPROVABLE")
    assert (
        fetch(execution_api.dsn, "SELECT status::text FROM ops.customer_order WHERE id=1")[0][0]
        == "DISPATCHED"
    )
    assert fetch(execution_api.dsn, "SELECT count(*) FROM ops.proof_of_delivery")[0][0] == 1
    assert fetch(execution_api.dsn, "SELECT count(*) FROM ops.vehicle_position")[0][0] == before
    assert fetch(execution_api.dsn, "SELECT status::text FROM ops.trip_stop WHERE id=2")[0][0] == "pending"


def _dispatch_both_vehicles(client: Api, monkeypatch: pytest.MonkeyPatch, notices: list[str]) -> None:
    async def test_driver_gate(*_args: object) -> None:
        return None

    async def test_enqueue(order_id: int, template: str, plan_id: int | None = None, **kw: object) -> int:
        assert kw.get("session") is not None
        notices.append(template)
        return len(notices)

    monkeypatch.setattr(risk_service, "recalculate", verified_risk)
    monkeypatch.setattr(notify_service, "enqueue", test_enqueue)
    monkeypatch.setattr(execution_service, "_driver_gate", test_driver_gate)
    for actor, kind, at, data in (
        (WAREHOUSE, "START_PREP", "2026-11-10T07:00:00Z", {"crew_size": 3}),
        (WAREHOUSE, "GOODS_READY", "2026-11-10T07:30:00Z", {}),
        (WAREHOUSE, "LOADED", "2026-11-10T08:00:00Z", {"trip_id": 1}),
        (WAREHOUSE, "LOADED", "2026-11-10T08:05:00Z", {"trip_id": 2}),
        (DRIVER, "DISPATCHED", "2026-11-10T08:10:00Z", {"trip_id": 1}),
        (14, "DISPATCHED", "2026-11-10T08:12:00Z", {"trip_id": 2}),
    ):
        assert send(client, actor, kind, at, data).status_code == 200


def test_M6_1_delivery_replay_with_same_idempotency_key_never_duplicates_pod(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    notices: list[str] = []
    _dispatch_both_vehicles(execution_api, monkeypatch, notices)
    body = {"trip_id": 1, "recipient_name": "Synthetic one"}
    key = str(uuid4())
    first = send(execution_api, DRIVER, "DELIVERED", "2026-11-10T09:30:00Z", body, key)
    again = send(execution_api, DRIVER, "DELIVERED", "2026-11-10T09:30:00Z", body, key)
    assert first.status_code == 200 and again.status_code == 200 and again.json() == first.json()
    # a fresh key for the already completed stop is an illegal transition, not a second POD
    assert_error(
        send(execution_api, DRIVER, "DELIVERED", "2026-11-10T09:31:00Z", body), 409, "ILLEGAL_TRANSITION"
    )
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.proof_of_delivery")[0]["n"] == 1
    assert (
        fetch(execution_api.dsn, "SELECT status::text AS s FROM ops.customer_order")[0]["s"] == "DISPATCHED"
    )
    assert notices == ["DISPATCHED"]  # no DELIVERED notice until every stop is delivered


def test_M6_1_both_vehicles_delivering_concurrently_complete_the_order_once(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    notices: list[str] = []
    _dispatch_both_vehicles(execution_api, monkeypatch, notices)
    calls = (
        (DRIVER, "2026-11-10T09:30:00Z", {"trip_id": 1, "recipient_name": "Synthetic one"}),
        (14, "2026-11-10T09:30:00Z", {"trip_id": 2, "recipient_name": "Synthetic two"}),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda c: send(execution_api, c[0], "DELIVERED", c[1], c[2]), calls))
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.proof_of_delivery")[0]["n"] == 2
    assert fetch(execution_api.dsn, "SELECT status::text AS s FROM ops.customer_order")[0]["s"] == "DELIVERED"
    assert notices.count("DELIVERED") == 1 and notices.count("DISPATCHED") == 1


def test_M6_1_failure_after_the_pod_insert_rolls_back_pod_stop_and_gps_purge(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    notices: list[str] = []
    _dispatch_both_vehicles(execution_api, monkeypatch, notices)
    execute(
        execution_api.dsn,
        *GPS_DUTY,
        "INSERT INTO ops.vehicle_position (trip_id, vehicle_id, lat, lon, recorded_at, source) "
        "VALUES (1, 1, 59, 18, '2026-11-10T08:30Z', 'simulator'), "
        "(1, 1, 59, 18, '2026-11-10T08:00Z', 'simulator')",  # before departure: invalid, purge must be undone
    )

    async def failing_risk(order_id: int, trigger: str, *, session: object = None) -> None:
        return None  # M7 produced no verified result for a non-terminal order -> whole event rolls back

    monkeypatch.setattr(risk_service, "recalculate", failing_risk)
    response = send(
        execution_api,
        DRIVER,
        "DELIVERED",
        "2026-11-10T09:30:00Z",
        {"trip_id": 1, "recipient_name": "Synthetic"},
    )
    assert_error(response, 409, "PLAN_NOT_APPROVABLE")
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.proof_of_delivery")[0]["n"] == 0
    assert (
        fetch(execution_api.dsn, "SELECT status::text AS s FROM ops.trip_stop WHERE id=1")[0]["s"]
        == "pending"
    )
    assert (
        fetch(execution_api.dsn, "SELECT status::text AS s FROM ops.delivery_trip WHERE id=1")[0]["s"]
        == "on_road"
    )
    assert positions(execution_api.dsn) == [(1, "08:00"), (1, "08:30")]  # GPS cleanup rolled back too


def test_US_GPS_03_AC1_terminal_order_purges_all_vehicles_positions(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dispatch_both_vehicles(execution_api, monkeypatch, [])
    execute(
        execution_api.dsn,
        *GPS_DUTY,
        "INSERT INTO ops.vehicle_position (trip_id, vehicle_id, lat, lon, recorded_at, source) VALUES "
        "(1, 1, 59, 18, '2026-11-10T08:30Z', 'device'), "  # valid
        "(1, 1, 59, 18, '2026-11-10T08:00Z', 'device'), "  # before the actual departure (08:10)
        "(1, 1, 59, 18, '2026-11-10T10:00Z', 'device'), "  # after the trip ended (09:30)
        "(2, 2, 59, 18, '2026-11-10T08:00Z', 'device'), "  # other vehicle: before ITS departure (08:12)
        "(2, 2, 59, 18, '2026-11-10T08:40Z', 'device')",  # other vehicle, still on the road: untouched
    )
    done = send(
        execution_api, DRIVER, "DELIVERED", "2026-11-10T09:30:00Z", {"trip_id": 1, "recipient_name": "S"}
    )
    assert done.status_code == 200, done.text
    assert (
        len(positions(execution_api.dsn)) == 6
    )  # first trip's completion point and both trips' older points
    # trip 2 is still tracked: its own cleanup happens only when it ends
    ended = send(
        execution_api, 14, "DELIVERED", "2026-11-10T09:40:00Z", {"trip_id": 2, "recipient_name": "S"}
    )
    assert ended.status_code == 200, ended.text
    assert positions(execution_api.dsn) == []


def test_US_GPS_03_AC1_partial_completion_does_not_purge_order_points(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dispatch_both_vehicles(execution_api, monkeypatch, [])
    execute(
        execution_api.dsn,
        "INSERT INTO ops.vehicle_position (trip_id, vehicle_id, lat, lon, recorded_at, source) "
        "VALUES (1, 1, 59, 18, '2026-11-10T08:30Z', 'device')",
    )
    done = send(
        execution_api, DRIVER, "DELIVERED", "2026-11-10T09:30:00Z", {"trip_id": 1, "recipient_name": "S"}
    )
    assert done.status_code == 200, done.text
    assert positions(execution_api.dsn) == [(1, "08:30"), (1, "09:30")]


def test_DEC_GPS_RET_no_collection_after_the_trip_ends_and_expired_points_are_never_returned(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import timedelta

    from app.deps import CurrentUser
    from app.services import gps_service
    from tests.integration.dev2_helpers import transact

    _dispatch_both_vehicles(execution_api, monkeypatch, [])
    execute(
        execution_api.dsn,
        *GPS_DUTY,
        "INSERT INTO ops.vehicle_position (trip_id, vehicle_id, lat, lon, recorded_at, source) "
        "VALUES (1, 1, 59, 18, '2026-11-10T08:30Z', 'device')",
    )
    done = send(
        execution_api, DRIVER, "DELIVERED", "2026-11-10T09:30:00Z", {"trip_id": 1, "recipient_name": "S"}
    )
    assert done.status_code == 200, done.text
    late = execution_api.client.post(
        "/api/v1/trips/1/positions",
        headers={"Authorization": "Bearer " + issue_token(DRIVER, {}), "Idempotency-Key": str(uuid4())},
        json={
            "lat": 59.3,
            "lon": 18.1,
            "accuracy_m": 10,
            "recorded_at": "2026-11-10T09:00:00Z",
        },
    )
    assert_error(late, 409, "NOT_ON_TRIP")  # offline upload after the trip ended is refused
    assert positions(execution_api.dsn) == [(1, "08:30"), (1, "09:30")]

    reviewer = CurrentUser(id=1, employee_id=1, roles=("admin",), market="SE")

    async def allow(
        _s, _a, _t
    ):  # a reviewed authorizer does not exist yet; this stands in for it in the test
        return True

    async def read(session, now):
        return await gps_service.read_history(
            session, reviewer, 1, case_ref="CASE-1", reason="Complaint", authorizer=allow, now=now
        )

    within = transact(execution_api.dsn, lambda s: read(s, clock.now() + timedelta(days=6)))
    assert len(within) == 2
    expired = transact(execution_api.dsn, lambda s: read(s, clock.now() + timedelta(days=8)))
    assert expired == []  # not returned although the retention job never ran
    assert positions(execution_api.dsn) == [(1, "08:30"), (1, "09:30")]
    default = CurrentUser(id=2, employee_id=2, roles=("dispatcher",), market="SE")

    async def denied(session):
        return await gps_service.read_history(session, default, 1, case_ref="C", reason="r", now=clock.now())

    with pytest.raises(Exception, match="not authorized"):
        transact(execution_api.dsn, denied)  # default authorizer: Dispatcher never reads history


def _enable_real_gps(execution_api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    execute(
        execution_api.dsn,
        *GPS_DUTY,
        "INSERT INTO ref.compliance_record (market_id,type,status,approved_on,reference) "
        "VALUES (1,'GPS_NOTICE','approved','2026-11-01','SYNTHETIC-T14')",
        "INSERT INTO hr.driver_availability "
        "(driver_employee_id,work_date,available_from,available_to,max_driving_min,"
        "verified_by,verified_at,source,source_ref) VALUES "
        "(5,'2026-11-10','2026-11-10T07:00Z','2026-11-10T17:00Z',540,"
        "'synthetic-demo','2026-11-08T09:00Z','synthetic_demo','t14-avail-1'),"
        "(11,'2026-11-10','2026-11-10T07:00Z','2026-11-10T17:00Z',540,"
        "'synthetic-demo','2026-11-08T09:00Z','synthetic_demo','t14-avail-2')",
    )
    monkeypatch.setattr(gps_service, "record_point", REAL_RECORD_POINT)
    monkeypatch.setattr(gps_service, "purge_order", REAL_PURGE_ORDER)

    async def route(_provider: object, *_args: object, **_kwargs: object) -> RouteEstimate:
        return RouteEstimate(Decimal("1.0"), 10, "ors")

    monkeypatch.setattr(gps_service, "route_with_fallback", route)


def test_US_EXE_02_AC2_AC8_real_gps_completion_purge_and_rollback(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T13 GPS writes and T14 completion/POD share the actual PostgreSQL transaction."""
    notices: list[str] = []
    _dispatch_both_vehicles(execution_api, monkeypatch, notices)
    _enable_real_gps(execution_api, monkeypatch)
    first = send(
        execution_api,
        DRIVER,
        "DELIVERED",
        "2026-11-10T09:30:00Z",
        {"trip_id": 1, "recipient_name": "Synthetic one"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["order_status"] == "DISPATCHED"
    assert fetch(execution_api.dsn, "SELECT count(*) FROM ops.proof_of_delivery")[0][0] == 1
    assert positions(execution_api.dsn) == [(1, "09:30")]

    async def fail_notify(*_args: object, **_kwargs: object) -> int:
        raise DomainError("PLAN_NOT_APPROVABLE", "Synthetic notification failure.")

    original_enqueue = notify_service.enqueue
    monkeypatch.setattr(notify_service, "enqueue", fail_notify)
    second_payload = {"trip_id": 2, "recipient_name": "Synthetic two"}
    failed = send(execution_api, 14, "DELIVERED", "2026-11-10T09:35:00Z", second_payload)
    assert_error(failed, 409, "PLAN_NOT_APPROVABLE")
    assert (
        fetch(execution_api.dsn, "SELECT status::text FROM ops.customer_order WHERE id=1")[0][0]
        == "DISPATCHED"
    )
    assert fetch(execution_api.dsn, "SELECT count(*) FROM ops.proof_of_delivery")[0][0] == 1
    assert positions(execution_api.dsn) == [(1, "09:30")]
    assert fetch(execution_api.dsn, "SELECT status::text FROM ops.trip_stop WHERE id=2")[0][0] == "pending"

    monkeypatch.setattr(notify_service, "enqueue", original_enqueue)
    second = send(execution_api, 14, "DELIVERED", "2026-11-10T09:35:00Z", second_payload)
    assert second.status_code == 200, second.text
    assert second.json()["order_status"] == "DELIVERED"
    assert fetch(execution_api.dsn, "SELECT count(*) FROM ops.proof_of_delivery")[0][0] == 2
    assert positions(execution_api.dsn) == []
    milestone = fetch(
        execution_api.dsn, "SELECT payload::text FROM ops.milestone_event ORDER BY id DESC LIMIT 1"
    )[0][0]
    assert "position" not in milestone and "59.0" not in milestone
