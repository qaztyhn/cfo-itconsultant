"""Demo P0: a routed Source order reaches the real five-gate planner on PostgreSQL.

This test uses only synthetic driver evidence and a persisted stock snapshot. It does not
claim WMS reserve ACK, production stock ingestion, or final approval acceptance.
"""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.adapters import demo_d7_reader
from app.core import clock
from app.deps import CurrentUser
from app.services import driver_history, planning_service
from app.services.approval_recheck import five_gate_recheck
from tests.d7_evidence import evidence
from tests.integration.conftest import execute, fetch
from tests.integration.dev2_helpers import transact
from tests.integration.test_ingest_orders import db as db  # noqa: F401 (PostgreSQL fixture)
from tests.integration.test_ingest_orders import prepare, run_orders, source
from tests.integration.test_ingest_runner import NOW
from tests.unit.test_demo_d7_reader import attest as attest_d7
from tests.unit.test_demo_d7_reader import fixture as build_d7

pytestmark = pytest.mark.integration
TARGET = date(2026, 11, 10)
DISPATCHER = CurrentUser(id=1, employee_id=1, roles=("dispatcher",), market="SE", location_ids=(2,))


class SyntheticReader:
    async def read(self, session, employee_id, market_code, target_date):
        if employee_id != 2 or market_code != "SE":
            return None
        return evidence(2, target_date)


@pytest.fixture
def standard_order(db: str):
    prepare(db)
    execute(
        db,
        "UPDATE ref.vehicle SET regulation_561_scope='out_of_scope' WHERE id=1",
        "INSERT INTO hr.employee_assignment(employee_id,location_id,start_date) "
        "VALUES(1,1,'2026-01-01'),(2,1,'2026-01-01')",
        "INSERT INTO hr.warehouse_staff(employee_id,role,counts_in_capacity) VALUES(1,'operator',true)",
        "INSERT INTO hr.driver_staff(employee_id,home_warehouse_id,licence_class,licence_expires_on) "
        "VALUES(2,1,'C','2027-01-31')",
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
    driver_history.configure_reader(SyntheticReader())
    try:
        yield db
    finally:
        driver_history.configure_reader(None)
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


def test_US_PLN_03_AC3_missing_official_driver_shift_cannot_produce_plan(standard_order: str) -> None:
    execute(standard_order, "DELETE FROM hr.employee_shift_schedule WHERE employee_id=2")
    transact(standard_order, lambda s: planning_service.plan(1, DISPATCHER, {}, session=s))
    assert (
        fetch(standard_order, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "NO_FEASIBLE_DATE"
    )
    assert fetch(standard_order, "SELECT count(*) FROM plan.stock_reservation")[0][0] == 0


def _enable_disposable_d7(db: str, tmp_path, monkeypatch) -> None:
    build_d7(tmp_path)
    execute(db, "UPDATE hr.employee SET employee_no='DEMO-DRIVER-1' WHERE id=2")
    monkeypatch.setenv("DEMO_DISPOSABLE", "1")
    monkeypatch.setattr(
        demo_d7_reader,
        "get_settings",
        lambda: SimpleNamespace(app_env="test", app_now=demo_d7_reader.DEMO_NOW),
    )
    driver_history.configure_reader(demo_d7_reader.DisposableD7Reader(tmp_path))


def test_demo_D7_attested_reader_real_postgres_planner(standard_order: str, tmp_path, monkeypatch) -> None:
    _enable_disposable_d7(standard_order, tmp_path, monkeypatch)
    run_id = transact(standard_order, lambda s: planning_service.plan(1, DISPATCHER, {}, session=s))
    assert run_id == 1
    assert fetch(standard_order, "SELECT result FROM plan.planning_run WHERE id=1")[0][0] == "feasible"
    plan_id = fetch(standard_order, "SELECT id FROM plan.fulfilment_plan ORDER BY rank LIMIT 1")[0][0]
    proof = transact(standard_order, lambda s: five_gate_recheck(s, plan_id))
    assert all(proof.gates.values())


def test_demo_D7_missing_day_real_postgres_planner_fails_closed(
    standard_order: str, tmp_path, monkeypatch
) -> None:
    _enable_disposable_d7(standard_order, tmp_path, monkeypatch)
    first_week = tmp_path / "history_week_01.json"
    data = json.loads(first_week.read_text(encoding="utf-8"))
    data["records"].pop()
    first_week.write_text(json.dumps(data), encoding="utf-8")
    attest_d7(tmp_path)
    transact(standard_order, lambda s: planning_service.plan(1, DISPATCHER, {}, session=s))
    assert (
        fetch(standard_order, "SELECT status FROM ops.customer_order WHERE id=1")[0][0]
        == "NO_FEASIBLE_DATE"
    )
    assert fetch(standard_order, "SELECT count(*) FROM plan.vehicle_reservation")[0][0] == 0
