"""T15 PostgreSQL regression: rotation, atomicity, handover and GPS revocation."""

from datetime import UTC, datetime

import pytest

from app.core import clock
from app.services import approval_service, dispatcher_assignment_service
from tests.integration import rows
from tests.integration.api_harness import Api, assert_error
from tests.integration.api_harness import api as api_fixture  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.test_approval_service import (
    _actor,
    _hold,
    _parallel_approve,
    _recheck,
    _run,
    _second_order,
)
from tests.integration.test_approval_service import db as approval_db_fixture  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def t15_db(request: pytest.FixtureRequest) -> str:
    return request.getfixturevalue("approval_db_fixture")


def _dispatchers(dsn: str) -> None:
    execute(
        dsn,
        "INSERT INTO hr.dispatcher_staff(employee_id,in_rotation) VALUES (1,true),(2,true)",
        "INSERT INTO ref.app_user(employee_id,email,password_hash,roles) "
        "VALUES(2,'second-dispatcher@cfo.test','not-a-real-hash','{dispatcher}')",
    )


def test_US_GPS_02_AC3_two_vehicle_approval_assigns_once_and_retries(t15_db: str) -> None:
    db = t15_db
    _dispatchers(db)
    execute(
        db,
        "INSERT INTO hr.driver_staff(employee_id,home_warehouse_id,licence_class,licence_expires_on) "
        "VALUES(2,1,'C','2027-01-01')",
        rows.plan_vehicle_sql(1, 2, 2, 2),
        "UPDATE plan.fulfilment_plan SET vehicle_count=2 WHERE id=1",
    )
    _hold(db)

    async def approve(session):
        return await approval_service.approve(
            1, _actor(), {}, "t15-two-vehicle", session=session, recheck=_recheck
        )

    first = _run(db, approve)
    assert first == _run(db, approve)
    assert len(first["trip_ids"]) == 2
    trips = fetch(db, "SELECT assigned_dispatcher_employee_id FROM ops.delivery_trip ORDER BY id")
    assert [t[0] for t in trips] == [1, 1]
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_APPROVED'")[0][0] == 1
    assert _run(db, lambda s: dispatcher_assignment_service.choose_dispatcher(s, 1)) == 2


def test_US_GPS_02_AC3_market_rotation_concurrent_approvals_no_double_turn(t15_db: str) -> None:
    db = t15_db
    _dispatchers(db)
    _hold(db)
    _second_order(db, stock=100)
    successes, failures = _parallel_approve(db)
    assert sorted(successes) == [1, 2], failures
    assert not failures
    assignments = fetch(
        db,
        "SELECT ts.order_id, dt.assigned_dispatcher_employee_id "
        "FROM ops.trip_stop ts JOIN ops.delivery_trip dt ON dt.id=ts.trip_id ORDER BY ts.order_id",
    )
    assert {r["assigned_dispatcher_employee_id"] for r in assignments} == {1, 2}
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_APPROVED'")[0][0] == 2
    # Both have now been assigned once; the earlier turn goes first.
    first_audit = fetch(
        db,
        "SELECT (after->>'assigned_dispatcher_employee_id')::bigint AS employee_id "
        "FROM audit.decision_log WHERE action='PLAN_APPROVED' ORDER BY id LIMIT 1",
    )[0]["employee_id"]
    assert _run(db, lambda s: dispatcher_assignment_service.choose_dispatcher(s, 1)) == first_audit


def test_US_GPS_02_AC3_no_eligible_dispatcher_keeps_approval_and_alert(t15_db: str) -> None:
    db = t15_db
    _hold(db)
    result = _run(
        db,
        lambda s: approval_service.approve(1, _actor(), {}, "no-dispatcher", session=s, recheck=_recheck),
    )
    assert result["order"]["status"] == "APPROVED"
    assert fetch(db, "SELECT assigned_dispatcher_employee_id FROM ops.delivery_trip")[0][0] is None
    alerts = fetch(
        db,
        "SELECT type FROM ops.alert WHERE order_id=1 AND type='NO_DISPATCHER_IN_ROTATION'",
    )
    assert len(alerts) == 1


def test_US_GPS_02_AC3_approval_rollback_does_not_advance_rotation(t15_db: str) -> None:
    db = t15_db
    _dispatchers(db)
    _hold(db)

    async def rollback(session):
        await approval_service.approve(1, _actor(), {}, "rollback-t15", session=session, recheck=_recheck)
        raise RuntimeError("force rollback after approval")

    with pytest.raises(RuntimeError, match="force rollback"):
        _run(db, rollback)
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_APPROVED'")[0][0] == 0
    assert _run(db, lambda s: dispatcher_assignment_service.choose_dispatcher(s, 1)) == 1
    result = _run(
        db,
        lambda s: approval_service.approve(
            1, _actor(), {}, "retry-after-rollback", session=s, recheck=_recheck
        ),
    )
    assert result["order"]["status"] == "APPROVED"
    assert fetch(db, "SELECT assigned_dispatcher_employee_id FROM ops.delivery_trip")[0][0] == 1


@pytest.fixture
def handover_api(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Api:
    """Two active on-road trips for one order, two Dispatchers, a different market."""
    api: Api = request.getfixturevalue("api_fixture")
    execute(
        api.dsn,
        *rows.REF_HR,
        rows.order_sql(1),
        "INSERT INTO hr.dispatcher_staff(employee_id,in_rotation) VALUES (1,true),(2,true)",
        "INSERT INTO ref.app_user(employee_id,email,password_hash,roles) "
        "VALUES(2,'dispatcher2@cfo.test','not-a-real-hash','{dispatcher}')",
        "INSERT INTO hr.employee_assignment(employee_id,location_id,start_date) "
        "VALUES(1,1,'2026-01-01'),(2,1,'2026-01-01')",
        "INSERT INTO hr.driver_staff(employee_id,home_warehouse_id,licence_class,licence_expires_on) "
        "VALUES (1,1,'C','2027-01-01')",
        "INSERT INTO hr.employee_shift_schedule "
        "(employee_id,warehouse_id,work_date,start_time,end_time,status,assigned_by,assigned_at) "
        "VALUES(1,1,'2026-11-04','07:00','17:00','scheduled',1,'2026-11-03T08:00:00Z')",
        "INSERT INTO ops.delivery_trip "
        "(warehouse_id,vehicle_id,driver_employee_id,assigned_dispatcher_employee_id,"
        "depart_planned_at,depart_actual_at,status) VALUES "
        "(1,1,1,1,'2026-11-04T07:00:00Z','2026-11-04T08:00:00Z','on_road'),"
        "(1,2,1,1,'2026-11-04T07:00:00Z','2026-11-04T08:00:00Z','on_road')",
        rows.stop_sql(1, 1),
        rows.stop_sql(2, 1),
        "INSERT INTO ops.vehicle_position "
        "(trip_id,vehicle_id,lat,lon,recorded_at,source) "
        "VALUES (1,1,59.3,18.1,'2026-11-04T08:20:00Z','device'),"
        "(2,2,59.3,18.1,'2026-11-04T08:20:00Z','device')",
        "UPDATE ref.market SET gps_enabled=true WHERE id=1",
        "INSERT INTO ref.location(market_id,type,code,name,lat,lon) "
        "VALUES (2,'warehouse','ZZ-WH','Other Market',50,10)",
        "INSERT INTO hr.employee(market_id,employee_no,first_name,last_name,position_code,hire_date) "
        "VALUES (2,'Z3','Other','Dispatcher','TEST_POS','2026-01-01')",
        "INSERT INTO ref.app_user(employee_id,email,password_hash,roles) "
        "VALUES(3,'market2@cfo.test','not-a-real-hash','{dispatcher}')",
        "INSERT INTO hr.dispatcher_staff(employee_id,in_rotation) VALUES (3,true)",
        "INSERT INTO hr.employee_assignment(employee_id,location_id,start_date) " "VALUES(3,3,'2026-01-01')",
        "INSERT INTO hr.employee(market_id,employee_no,first_name,last_name,position_code,hire_date) "
        "VALUES (1,'S4','Sales','Worker','TEST_POS','2026-01-01')",
        "INSERT INTO ref.app_user(employee_id,email,password_hash,roles) "
        "VALUES(4,'non-dispatcher@cfo.test','not-a-real-hash','{sales}')",
    )
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 4, 9, 5, tzinfo=UTC))
    return api


def _handover(api: Api, user: int, target: int = 2, reason: str = "Shift reassignment"):
    return api.send("POST", "/trips/1/handover", user, {"to_employee_id": target, "reason_text": reason})


def test_US_GPS_02_AC3_handover_revokes_old_live_scope_after_commit(handover_api: Api) -> None:
    api = handover_api
    initial_old = api.get("/gps/live", 1)
    assert initial_old.status_code == 200, initial_old.text
    assert {t["trip_id"] for t in initial_old.json()} == {1, 2}
    assert api.get("/gps/live", 2).json() == []

    changed = _handover(api, 1)
    assert changed.status_code == 200, changed.text
    assert changed.json() == {
        "trip_id": 1,
        "previous_dispatcher_employee_id": 1,
        "assigned_dispatcher_employee_id": 2,
    }
    old = api.get("/gps/live", 1)
    new = api.get("/gps/live", 2)
    assert old.status_code == 200 and {t["trip_id"] for t in old.json()} == {2}
    assert new.status_code == 200 and {t["trip_id"] for t in new.json()} == {1}
    assert new.json()[0]["last_position"] == {"lat": 59.3, "lon": 18.1}
    assert (
        fetch(api.dsn, "SELECT assigned_dispatcher_employee_id FROM ops.delivery_trip WHERE id=2")[0][0] == 1
    )
    audits = fetch(
        api.dsn,
        "SELECT actor_user_id,actor_employee_id,reason_text,before,after FROM audit.decision_log "
        "WHERE action='TRIP_DISPATCHER_HANDOVER'",
    )
    assert len(audits) == 1
    assert audits[0]["actor_user_id"] == audits[0]["actor_employee_id"] == 1
    assert audits[0]["reason_text"] == "Shift reassignment"
    assert audits[0]["before"]["assigned_dispatcher_employee_id"] == 1
    assert audits[0]["after"]["assigned_dispatcher_employee_id"] == 2
    assert_error(_handover(api, 1), 409, "ILLEGAL_TRANSITION")
    assert (
        fetch(api.dsn, "SELECT count(*) FROM audit.decision_log WHERE action='TRIP_DISPATCHER_HANDOVER'")[0][
            0
        ]
        == 1
    )


def test_US_GPS_02_AC3_handover_rejections_are_atomic(handover_api: Api) -> None:
    api = handover_api
    assert_error(_handover(api, 1, reason="   "), 422, "REASON_REQUIRED")
    assert_error(_handover(api, 4), 403, "FORBIDDEN")
    assert_error(_handover(api, 3), 404, "NOT_FOUND")
    assert_error(_handover(api, 1, target=3), 422, "VALIDATION_ERROR")
    execute(api.dsn, "UPDATE hr.dispatcher_staff SET in_rotation=false WHERE employee_id=2")
    assert_error(_handover(api, 1), 422, "VALIDATION_ERROR")
    execute(
        api.dsn,
        "UPDATE hr.dispatcher_staff SET in_rotation=true WHERE employee_id=2",
        "UPDATE hr.employee SET status='terminated' WHERE id=2",
    )
    assert_error(_handover(api, 1), 422, "VALIDATION_ERROR")
    assert (
        fetch(api.dsn, "SELECT assigned_dispatcher_employee_id FROM ops.delivery_trip WHERE id=1")[0][0] == 1
    )
    assert (
        fetch(api.dsn, "SELECT count(*) FROM audit.decision_log WHERE action='TRIP_DISPATCHER_HANDOVER'")[0][
            0
        ]
        == 0
    )
