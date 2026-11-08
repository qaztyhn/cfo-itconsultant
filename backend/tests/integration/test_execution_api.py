"""M6 PostgreSQL tests: scoped execution, driver safety and transaction rollback."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core import clock
from app.core.security import issue_token
from app.services import execution_service, notify_service, planning_service, risk_service
from tests.integration import rows
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.hr_fixture import DISPATCHER, DRIVER, SALES, SETUP, WAREHOUSE, ZZ_WAREHOUSE

pytestmark = pytest.mark.integration

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
    try:
        yield api
    finally:
        clock.set_now(None)


def send(
    client: Api,
    actor: int,
    kind: str,
    at: str,
    payload: dict[str, object] | None = None,
    key: str | None = None,
):
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


def test_US_WH_04_AC4_missing_risk_dependency_rolls_back(execution_api: Api) -> None:
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
    assert response.json()["items"][0]["order_no"] == "SE-M6"
    assert "contact_name" not in response.text
    assert_error(execution_api.get("/warehouses/3/prep-queue", WAREHOUSE), 404, "NOT_FOUND")
    assert_error(execution_api.get("/warehouses/1/prep-queue", DRIVER), 403, "FORBIDDEN")
    assert_error(execution_api.get("/prep-queue", WAREHOUSE, warehouse_id=1), 409, "PLAN_NOT_APPROVABLE")


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


def test_US_EXE_02_AC5_AC7_partial_delivery_single_notice_and_gps_purge(
    execution_api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bypass missing external gate *only in this integration test* to test order aggregation."""

    async def test_driver_gate(*_args: object) -> None:
        return None

    messages: list[str] = []
    triggers: list[str] = []

    async def test_enqueue(order_id: int, template: str, plan_id: int | None = None) -> int:
        assert order_id == 1 and plan_id == 1
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
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.vehicle_position")[0]["n"] == 1
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
    assert triggers == ["delivery_failed"]
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.vehicle_position")[0]["n"] == 0
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.proof_of_delivery")[0]["n"] == 2
    assert fetch(execution_api.dsn, "SELECT count(*) AS n FROM ops.alert WHERE type='EXCEPTION'")[0]["n"] == 1


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

    async def test_enqueue(order_id: int, template: str, plan_id: int | None = None) -> int:
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
