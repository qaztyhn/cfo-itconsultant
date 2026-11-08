"""Plan vehicle DTO: nested `vehicle` object (docs/06 §6.2, owner decision Option B)."""

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.core.errors import DomainError
from app.services import planning_service
from tests.integration.conftest import execute
from tests.integration.test_planning_service import _actor, _request, _run  # noqa: F401
from tests.integration.test_planning_service import db as db


def _plan(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _request(db, monkeypatch) == 1


def test_dispatcher_run_vehicle_has_nested_fleet_object(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _plan(db, monkeypatch)
    run = _run(db, lambda s: planning_service.get_run(1, _actor(), session=s))
    vehicle = run["plans"][0]["vehicles"][0]
    assert vehicle["vehicle_id"] == 1
    assert vehicle["driver_employee_id"] == 1
    assert vehicle["vehicle"] == {
        "id": 1,
        "code": "V-1",
        "name": "Truck 1",
        "capacity_kg": "8000",
        "capacity_m3": "30",
    }
    # existing fields are preserved
    for key in ("seq", "load_kg", "load_m3", "load_lines", "loading_start_at", "depart_at", "eta_at"):
        assert key in vehicle


def test_plan_and_run_return_identical_vehicle_dto(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _plan(db, monkeypatch)
    run = _run(db, lambda s: planning_service.get_run(1, _actor(), session=s))
    plan_id = run["plans"][0]["id"]
    plan = _run(db, lambda s: planning_service.get_plan(plan_id, _actor(), session=s))
    assert plan["vehicles"] == run["plans"][0]["vehicles"]


def test_vehicle_dto_exposes_no_sensitive_fleet_fields(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _plan(db, monkeypatch)
    run = _run(db, lambda s: planning_service.get_run(1, _actor(), session=s))
    nested = run["plans"][0]["vehicles"][0]["vehicle"]
    assert set(nested) == {"id", "code", "name", "capacity_kg", "capacity_m3"}
    assert "TST001" not in str(run)  # plate


def test_sales_view_stays_compact_without_vehicle_detail(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _plan(db, monkeypatch)
    run = _run(db, lambda s: planning_service.get_run(1, _actor("sales"), session=s))
    assert set(run["plans"][0]["vehicles"][0]) == {"seq", "eta_at"}
    plan_id = run["plans"][0]["id"]
    plan = _run(db, lambda s: planning_service.get_plan(plan_id, _actor("sales"), session=s))
    assert set(plan["vehicles"][0]) == {"seq", "eta_at"}


def test_vehicles_are_batch_loaded_once(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _plan(db, monkeypatch)
    statements: list[str] = []

    def record(_conn: object, _cur: object, statement: str, *_a: object) -> None:
        statements.append(statement)

    async def read(session: object) -> None:
        sync_engine: Engine = session.bind.sync_engine  # type: ignore[attr-defined]
        event.listen(sync_engine, "before_cursor_execute", record)
        try:
            await planning_service.get_run(1, _actor(), session=session)  # type: ignore[arg-type]
        finally:
            event.remove(sync_engine, "before_cursor_execute", record)

    _run(db, read)
    assert sum("FROM ref.vehicle" in s for s in statements) == 1
    assert sum("FROM plan.plan_vehicle" in s for s in statements) == 1


def test_missing_vehicle_record_fails_closed(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _plan(db, monkeypatch)
    # Force an orphan reference: the FK is deferred away only inside this test database.
    execute(db, "ALTER TABLE plan.plan_vehicle DROP CONSTRAINT IF EXISTS plan_vehicle_vehicle_id_fkey")
    execute(db, "UPDATE plan.plan_vehicle SET vehicle_id=999")
    with pytest.raises(DomainError) as exc:
        _run(db, lambda s: planning_service.get_run(1, _actor(), session=s))
    assert exc.value.code == "INTERNAL_ERROR"
    assert "999" not in exc.value.message
