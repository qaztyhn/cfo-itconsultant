"""Demo P0: a routed Source order reaches the real five-gate planner on PostgreSQL.

This test uses only synthetic driver evidence and a persisted stock snapshot. It does not
claim WMS reserve ACK, production stock ingestion, or final approval acceptance.
"""

import json
from datetime import date

import pytest

from app.core import clock
from app.deps import CurrentUser
from app.services import approval_service, driver_history, planning_service
from app.services.approval_recheck import five_gate_recheck
from tests.integration.api_harness import api_for_db
from tests.integration.conftest import execute, fetch
from tests.integration.dev2_helpers import transact
from tests.integration.test_ingest_orders import db as db  # noqa: F401 (PostgreSQL fixture)
from tests.integration.test_ingest_orders import prepare, run_orders, source
from tests.integration.test_ingest_runner import NOW

pytestmark = pytest.mark.integration
TARGET = date(2026, 11, 10)
DISPATCHER = CurrentUser(id=1, employee_id=1, roles=("dispatcher",), market="SE", location_ids=(2,))


@pytest.fixture
def standard_order(db: str):
    prepare(db)
    execute(
        db,
        "UPDATE ref.vehicle SET regulation_561_scope='out_of_scope',max_permissible_mass_kg=12000 WHERE id=1",
        "INSERT INTO hr.employee_assignment(employee_id,location_id,start_date) "
        "VALUES(1,1,'2026-01-01'),(2,1,'2026-01-01')",
        "INSERT INTO hr.warehouse_staff(employee_id,role,counts_in_capacity) VALUES(1,'operator',true)",
        "INSERT INTO hr.driver_staff(employee_id,home_warehouse_id,licence_class,licence_expires_on) "
        "VALUES(2,1,'C','2027-01-31')",
        "INSERT INTO hr.driver_availability "
        "(driver_employee_id,work_date,available_from,available_to,max_driving_min,"
        "verified_by,verified_at,source,source_ref) VALUES "
        "(2,'2026-11-10','2026-11-10T06:00Z','2026-11-10T18:00Z',540,"
        "'Fleet Desk','2026-11-04T09:00Z','fleet_api','STD-AV')",
        "INSERT INTO hr.driver_vehicle_eligibility "
        "(driver_employee_id,vehicle_id,verified_until,verified_by,verified_at,source,source_ref) VALUES "
        "(2,1,'2026-11-10','Fleet Desk','2026-11-04T09:00Z','fleet_api','STD-QUAL')",
        "INSERT INTO hr.employee_shift_schedule(employee_id,warehouse_id,work_date,start_time,end_time,"
        "assigned_by,assigned_at) VALUES "
        "(1,1,'2026-11-10','07:00','17:00',1,'2026-11-04T09:00Z'),"
        "(2,1,'2026-11-10','06:00','18:00',1,'2026-11-04T09:00Z')",
        "INSERT INTO hr.attendance(employee_id,work_date,status) VALUES "
        "(1,'2026-11-10','planned'),(2,'2026-11-10','planned')",
        "INSERT INTO ops.stock_snapshot(warehouse_id,global_product_id,on_hand,wms_reserved,as_of) "
        "VALUES(1,1,100,0,'2026-11-04T09:05Z')",
        "INSERT INTO plan.route_matrix(warehouse_id,to_lat,to_lon,distance_km,duration_min,provider) "
        "VALUES(1,59,18,20,45,'ors')",
    )
    result = run_orders(db, [source(version=2)])
    assert result.status == "ok", result
    assert fetch(db, "SELECT source_version FROM ops.customer_order WHERE id=1")[0][0] == 2
    clock.set_now(NOW)
    try:
        yield db
    finally:
        clock.set_now(None)


def test_US_INT_01_AC2_source_order_uses_real_persisted_five_gate_planner(standard_order: str) -> None:
    run_id = transact(standard_order, lambda s: planning_service.plan(1, DISPATCHER, {}, session=s))
    run = fetch(
        standard_order,
        "SELECT result,input_snapshot->>'source_version' AS source_version FROM plan.planning_run WHERE id=1",
    )[0]
    assert run_id == 1 and (run["result"], run["source_version"]) == ("feasible", "2")
    plans = fetch(
        standard_order,
        "SELECT id,checks,warehouse_id,vehicle_count FROM plan.fulfilment_plan ORDER BY rank",
    )
    assert plans and all(
        all(
            json.loads(plan["checks"])[gate]["passed"] is True
            for gate in ("stock", "preparation", "truck", "site_date", "safety")
        )
        for plan in plans
    )
    assert all(plan["warehouse_id"] == 1 and plan["vehicle_count"] >= 1 for plan in plans)
    assert fetch(standard_order, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"
    assert fetch(standard_order, "SELECT count(*) FROM plan.stock_reservation WHERE status='held'")[0][0] == 1
    assert fetch(standard_order, "SELECT count(*) FROM plan.prep_reservation WHERE status='held'")[0][0] >= 1
    assert (
        fetch(standard_order, "SELECT count(*) FROM plan.vehicle_reservation WHERE status='held'")[0][0] >= 1
    )
    proof = transact(standard_order, lambda s: five_gate_recheck(s, plans[0]["id"]))
    assert all(proof.gates.values())


def test_US_PLN_03_AC3_missing_fleet_verification_returns_no_driver(
    standard_order: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    execute(standard_order, "DELETE FROM hr.driver_availability")
    with api_for_db(standard_order, monkeypatch) as api:
        response = api.send("POST", "/orders/1/plan", DISPATCHER.id, {})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["result"] == "infeasible" and not payload["plans"]
    assert any(
        item["code"] == "NO_DRIVER" and item["detail"]["reason"] == "not_verified"
        for item in payload["rejected_candidates"]
    )
    assert fetch(standard_order, "SELECT count(*) FROM plan.stock_reservation")[0][0] == 0


def test_US_APR_01_recheck_rejects_fleet_revocation_after_planning(
    standard_order: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def legacy_history(*args, **kwargs):
        pytest.fail("The R3 planner or approval called the D7 reader")

    monkeypatch.setattr(driver_history, "load_proof", legacy_history)
    monkeypatch.delenv("DEMO_D7_FIXTURE_DIR", raising=False)
    transact(standard_order, lambda s: planning_service.plan(1, DISPATCHER, {}, session=s))
    plan_id = fetch(standard_order, "SELECT id FROM plan.fulfilment_plan WHERE rank=1")[0][0]
    assert all(transact(standard_order, lambda s: five_gate_recheck(s, plan_id)).gates.values())
    execute(standard_order, "UPDATE hr.driver_vehicle_eligibility SET revoked_at='2026-11-04T09:05Z'")
    assert not any(transact(standard_order, lambda s: five_gate_recheck(s, plan_id)).gates.values())


@pytest.mark.parametrize("requested_day", ["2026-11-10", "2026-11-09"])
def test_US_PLN_07_AC1_AC3_public_planning_and_date_negotiation(
    standard_order: str, monkeypatch: pytest.MonkeyPatch, requested_day: str
) -> None:
    fetch(
        standard_order,
        "UPDATE ops.customer_order SET date_from=$1, date_to=$1 WHERE id=1 RETURNING id",
        date.fromisoformat(requested_day),
    )
    with api_for_db(standard_order, monkeypatch) as api:
        monkeypatch.setattr(approval_service, "get_sessionmaker", lambda: api.maker)
        response = api.send("POST", "/orders/1/plan", DISPATCHER.id, {})
        assert response.status_code == 200, response.text
        run = response.json()
        assert "transfer_suggestions" not in run
        read = api.get(f"/planning-runs/{run['id']}", DISPATCHER.id)
        assert read.status_code == 200
        assert read.json() == run
        if requested_day == TARGET.isoformat():
            assert run["result"] == "feasible"
            assert run["plans"][0]["target_date"] == requested_day
            return
        assert run["result"] == "infeasible" and not run["plans"]
        assert run["earliest_feasible_date"] == TARGET.isoformat()
        assert run["failed_check"] and any(item["code"] for item in run["rejected_candidates"])
        order_before = fetch(standard_order, "SELECT date_to,version,status FROM ops.customer_order")[0]
        assert order_before["status"] == "NO_FEASIBLE_DATE"
        result = api.send(
            "POST",
            "/orders/1/date-negotiations",
            DISPATCHER.id,
            {
                "proposed_date": run["earliest_feasible_date"],
                "contacted_at": NOW.isoformat(),
                "outcome": "agreed",
                "channel": "phone",
                "note": "Synthetic agreement",
            },
        )
        assert result.status_code == 200, result.text
        history = api.get("/orders/1/date-negotiations", DISPATCHER.id)
        assert history.status_code == 200 and history.json()["items"][0]["id"] == result.json()["id"]
        assert (
            fetch(standard_order, "SELECT date_to,version,status FROM ops.customer_order")[0] == order_before
        )
        assert fetch(standard_order, "SELECT count(*) FROM plan.planning_run")[0][0] == 1
