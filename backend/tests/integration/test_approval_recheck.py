"""T16 trusted five-gate recheck adapter (04 section 7.10): real PostgreSQL, fresh engine run.

The engine is replaced by a deterministic stand-in (as in test_planning_service.py): these tests prove the
adapter's contract with approval_service, not the engine's maths. The production loader is exercised too, to
show that a real market fails closed (the D7 history marker is not persisted).
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from functools import partial
from typing import Any

import pytest

from app.core.errors import DomainError
from app.engine.types import CheckResult, PlanCandidate, PlanningResult, VehicleAssignment
from app.services import approval_recheck, approval_service, planning_service, reservation_service
from app.services.approval_recheck import five_gate_recheck
from tests.integration import rows
from tests.integration.conftest import execute, fetch
from tests.integration.test_approval_service import _actor, _run
from tests.integration.test_approval_service import db as db
from tests.integration.test_planning_service import TARGET, D, _loader

pytestmark = pytest.mark.integration

GATES = ("stock", "preparation", "truck", "site_date", "safety")
DAY = datetime(2026, 11, 10, tzinfo=UTC)


def _unit(
    seq: int = 1,
    vehicle: int = 1,
    driver: int = 1,
    kg: str = "1000",
    m3: str = "2",
    lines: tuple[tuple[int, str], ...] = (),
) -> VehicleAssignment:
    """A vehicle assignment equal to the fixture (06:30 load, 07:00 depart, 09:00 ETA, 11:00 end)."""
    return VehicleAssignment(
        seq=seq, vehicle_id=vehicle, vehicle_code=f"V-{vehicle}", capacity_kg=D("8000"), capacity_m3=D("30"),
        driver_employee_id=driver, load_kg=D(kg), load_m3=D(m3),
        load_lines=tuple((n, D(q)) for n, q in lines),
        loading_start_at=DAY.replace(hour=6, minute=30), depart_at=DAY.replace(hour=7),
        eta_at=DAY.replace(hour=9), trip_end_at=DAY.replace(hour=11),
    )  # fmt: skip


def _candidate(
    *units: VehicleAssignment, safety: bool = True, warehouse: int = 1, **plan: Any
) -> PlanCandidate:
    """The plan row stored by `rows.plan_sql` (06:00 ready, 42 km / 120 min, 1.5 h prep, 'fallback' route)."""
    units = units or (_unit(),)
    checks = tuple(CheckResult(name, name != "safety" or safety, name.upper(), {}) for name in GATES)
    fields: dict[str, Any] = dict(
        warehouse_id=warehouse, vehicles=units, target_date=TARGET, goods_ready_at=DAY.replace(hour=6),
        loading_start_at=DAY.replace(hour=6, minute=30), depart_at=DAY.replace(hour=7),
        eta_at=DAY.replace(hour=9), trip_end_at=DAY.replace(hour=11), distance_km=D("42"), drive_min=120,
        prep_hours=D("1.5"), capacity_fill=D("0.5"), complexity_points=0, planning_reserve_min=2880,
        route_provenance="fallback", checks=checks, prep_by_day={TARGET: D("1.5")}, rank=1,
    )  # fmt: skip
    fields.update(plan)
    return PlanCandidate(**fields)


def _engine(monkeypatch: pytest.MonkeyPatch, *candidates: PlanCandidate) -> None:
    result = PlanningResult(
        "feasible" if candidates else "infeasible",
        candidates,
        (),
        None if candidates else "truck",
        None,
        "safe",
        2880,
        (),
    )  # fmt: skip
    monkeypatch.setattr(planning_service, "plan_order", lambda *a, **k: result)


def _hold(db: str) -> None:
    _run(db, lambda s: reservation_service.hold(1, session=s))
    execute(db, "UPDATE ops.customer_order SET status='PLANNED' WHERE id=1")


def _approve(db: str, key: str, **kw: Any) -> dict[str, object]:
    recheck = partial(five_gate_recheck, **kw)
    return _run(db, lambda s: approval_service.approve(1, _actor(), {}, key, session=s, recheck=recheck))


def _state(db: str) -> tuple[str, str, str]:
    plan = fetch(db, "SELECT status FROM plan.fulfilment_plan WHERE id=1")[0][0]
    order = fetch(db, "SELECT status FROM ops.customer_order WHERE id=1")[0][0]
    stock = fetch(db, "SELECT status FROM plan.stock_reservation WHERE run_id=1")[0][0]
    return plan, order, stock


def _nothing_committed(db: str) -> None:
    """A failed recheck leaves every reservation held, the order PLANNED/unapproved and no approval audit."""
    assert _state(db) == ("proposed", "PLANNED", "held")
    assert {r[0] for r in fetch(db, "SELECT status FROM plan.prep_reservation WHERE run_id=1")} == {"held"}
    assert {r[0] for r in fetch(db, "SELECT status FROM plan.vehicle_reservation WHERE run_id=1")} == {"held"}
    assert fetch(db, "SELECT approved_plan_id FROM ops.customer_order WHERE id=1")[0][0] is None
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='PLAN_APPROVED'")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM ops.delivery_trip")[0][0] == 0


def test_five_gate_recheck_approves_the_same_plan_when_all_gates_still_pass(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hold(db)
    _engine(monkeypatch, _candidate())
    result = _approve(db, "k1", inputs_loader=_loader)
    assert result["order"]["status"] == "APPROVED"  # type: ignore[index]
    assert _state(db) == ("approved", "APPROVED", "committed")


@pytest.mark.parametrize(
    "candidates",
    [
        (),  # the engine finds nothing any more
        (_candidate(safety=False),),  # same plan, but a gate no longer passes
        (_candidate(_unit(driver=2)),),  # same vehicle, different driver: not the held plan
        (_candidate(_unit(vehicle=2)),),  # different vehicle
        (_candidate(warehouse=3),),  # different warehouse
    ],
    ids=["nothing", "safety-failed", "other-driver", "other-vehicle", "other-warehouse"],
)
def test_five_gate_recheck_rejects_when_the_stored_plan_is_not_confirmed(
    db: str, monkeypatch: pytest.MonkeyPatch, candidates: tuple[PlanCandidate, ...]
) -> None:
    _hold(db)
    _engine(monkeypatch, *candidates)
    with pytest.raises(DomainError) as caught:
        _approve(db, "k-reject", inputs_loader=_loader)
    assert (caught.value.code, caught.value.details.get("conflict")) == ("RESOURCE_CONFLICT", "five_gates")
    _nothing_committed(db)


def test_five_gate_recheck_rejects_when_the_source_order_changed_after_the_run(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hold(db)
    execute(
        db,
        "UPDATE plan.planning_run SET input_snapshot='{\"source_version\": 1}'::jsonb WHERE id=1",
        "UPDATE ops.customer_order SET source_version=2 WHERE id=1",
    )
    _engine(monkeypatch, _candidate())  # the engine would still like it; the changed source must win
    with pytest.raises(DomainError) as caught:
        _approve(db, "k-source", inputs_loader=_loader)
    assert caught.value.details.get("conflict") == "five_gates"
    _nothing_committed(db)


def test_five_gate_recheck_propagates_input_failures_instead_of_approving(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hold(db)
    _engine(monkeypatch, _candidate())

    async def stale(*_a: object, **_k: object) -> object:
        raise DomainError("RESOURCE_CONFLICT", "Market stock snapshot unavailable or stale.")

    with pytest.raises(DomainError, match="stale"):
        _approve(db, "k-stale", inputs_loader=stale)
    _nothing_committed(db)


def test_the_production_loader_fails_closed_without_the_d7_history_marker(db: str) -> None:
    """No injected loader: the real planning inputs cannot be built/approved for this market today."""
    _hold(db)
    with pytest.raises(DomainError):
        _approve(db, "k-real")
    _nothing_committed(db)


def test_the_recheck_never_approves_a_missing_plan(db: str) -> None:
    with pytest.raises(DomainError) as caught:
        _run(db, lambda s: five_gate_recheck(s, 999, inputs_loader=_loader))
    assert caught.value.code == "NOT_FOUND"


def _reject(db: str, monkeypatch: pytest.MonkeyPatch, candidate: PlanCandidate, key: str) -> None:
    _hold(db)
    _engine(monkeypatch, candidate)
    with pytest.raises(DomainError) as caught:
        _approve(db, key, inputs_loader=_loader)
    assert (caught.value.code, caught.value.details.get("conflict")) == ("RESOURCE_CONFLICT", "five_gates")
    _nothing_committed(db)


def _shift(unit: VehicleAssignment, **minutes: int) -> VehicleAssignment:
    return replace(
        unit, **{name: getattr(unit, name) + timedelta(minutes=delta) for name, delta in minutes.items()}
    )


def test_same_vehicle_and_driver_with_a_later_departure_is_not_the_held_plan(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reject(db, monkeypatch, _candidate(_shift(_unit(), depart_at=30)), "k-depart-vehicle")


def test_a_changed_plan_level_departure_is_not_the_held_plan(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reject(db, monkeypatch, _candidate(depart_at=DAY.replace(hour=7, minute=30)), "k-depart-plan")


@pytest.mark.parametrize("level", ["vehicle", "plan"])
def test_same_vehicle_and_driver_with_a_changed_eta_is_not_the_held_plan(
    db: str, monkeypatch: pytest.MonkeyPatch, level: str
) -> None:
    if level == "vehicle":
        candidate = _candidate(_shift(_unit(), eta_at=15))
    else:
        candidate = _candidate(eta_at=DAY.replace(hour=9, minute=15))
    _reject(db, monkeypatch, candidate, f"k-eta-{level}")


@pytest.mark.parametrize(
    "field",
    ["goods_ready_at", "loading_start_at", "trip_end_at"],
)
def test_other_changed_schedule_instants_are_not_the_held_plan(
    db: str, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    moved = getattr(_candidate(), field) + timedelta(minutes=5)
    _reject(db, monkeypatch, _candidate(**{field: moved}), f"k-{field}")


@pytest.mark.parametrize(
    "unit",
    [
        _unit(kg="1000.01"),
        _unit(m3="2.001"),
        _unit(lines=((1, "5"),)),  # the held vehicle carries no line here
    ],
    ids=["load-kg", "load-m3", "load-lines"],
)
def test_a_changed_single_vehicle_load_is_not_the_held_plan(
    db: str, monkeypatch: pytest.MonkeyPatch, unit: VehicleAssignment
) -> None:
    _reject(db, monkeypatch, _candidate(unit), "k-load")


@pytest.mark.parametrize(
    "plan",
    [
        {"prep_hours": D("1.501")},
        {"prep_by_day": {TARGET: D("2.0")}},
        {"prep_by_day": {TARGET + timedelta(days=1): D("1.5")}},
        {"distance_km": D("42.01")},
        {"drive_min": 121},
        {"planning_reserve_min": 2000},
        {"route_provenance": "ors"},
    ],
    ids=["prep-hours", "prep-day-hours", "prep-day", "distance", "drive-min", "reserve", "route"],
)
def test_changed_plan_level_workload_or_route_is_not_the_held_plan(
    db: str, monkeypatch: pytest.MonkeyPatch, plan: dict[str, Any]
) -> None:
    _reject(db, monkeypatch, _candidate(**plan), "k-plan-field")


def test_equal_values_in_another_representation_still_match(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Decimal scale and UTC offset are representation only: same quantity, same instant, approve."""
    _hold(db)
    plus_one = datetime(2026, 11, 10, 8, 0, tzinfo=timezone(timedelta(hours=1)))  # == 07:00Z
    unit = replace(_unit(kg="1000.00", m3="2.000"), depart_at=plus_one)
    _engine(monkeypatch, _candidate(unit, depart_at=plus_one, distance_km=D("42.000"), prep_hours=D("1.50")))
    assert _approve(db, "k-repr", inputs_loader=_loader)["order"]["status"] == "APPROVED"  # type: ignore[index]


def test_a_naive_timestamp_never_matches(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    naive = datetime(2026, 11, 10, 7, 0)  # noqa: DTZ001 - naive on purpose
    _reject(db, monkeypatch, _candidate(depart_at=naive), "k-naive")


def _two_vehicle_plan(db: str) -> None:
    """Held plan with two vehicles/drivers and distinct loads (must be set up BEFORE the hold)."""
    execute(
        db,
        "INSERT INTO hr.driver_staff (employee_id,home_warehouse_id,licence_class,licence_expires_on) "
        "VALUES (2,1,'C','2027-01-01')",
        rows.plan_vehicle_sql(1, 2, 2, 2),
        "UPDATE plan.fulfilment_plan SET vehicle_count=2,total_capacity_kg=16000,"
        "total_capacity_m3=60 WHERE id=1",
        "UPDATE plan.plan_vehicle SET load_kg=1000,load_m3=2,"
        'load_lines=\'[{"line_no":1,"qty_base":"12"}]\'::jsonb WHERE seq=1',
        "UPDATE plan.plan_vehicle SET load_kg=500,load_m3=1,"
        'load_lines=\'[{"line_no":1,"qty_base":"8"}]\'::jsonb WHERE seq=2',
    )


def _pair(
    *, first_driver: int = 1, second_driver: int = 2, swap_loads: bool = False
) -> tuple[VehicleAssignment, ...]:
    first = _unit(1, 1, first_driver, "1000", "2", ((1, "12"),))
    second = _unit(2, 2, second_driver, "500", "1", ((1, "8"),))
    if swap_loads:
        first = replace(first, load_kg=second.load_kg, load_m3=second.load_m3, load_lines=second.load_lines)
        second = replace(second, load_kg=D("1000"), load_m3=D("2"), load_lines=((1, D("12")),))
    return first, second


def test_two_vehicle_plan_identical_to_the_held_one_stays_approvable(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_vehicle_plan(db)
    _hold(db)
    _engine(monkeypatch, _candidate(*_pair()))
    assert _approve(db, "k-two-ok", inputs_loader=_loader)["order"]["status"] == "APPROVED"  # type: ignore[index]
    assert _state(db) == ("approved", "APPROVED", "committed")


@pytest.mark.parametrize(
    "units",
    [
        _pair(first_driver=2, second_driver=1),  # the two drivers swapped between the vehicles
        _pair(second_driver=1),  # one driver would drive both vehicles
        _pair(swap_loads=True),  # same vehicles and drivers, loads redistributed
    ],
    ids=["drivers-swapped", "one-driver-twice", "loads-redistributed"],
)
def test_two_vehicle_plan_with_changed_drivers_or_load_distribution_is_rejected(
    db: str, monkeypatch: pytest.MonkeyPatch, units: tuple[VehicleAssignment, ...]
) -> None:
    _two_vehicle_plan(db)
    _hold(db)
    _engine(monkeypatch, _candidate(*units))
    with pytest.raises(DomainError) as caught:
        _approve(db, "k-two-bad", inputs_loader=_loader)
    assert caught.value.details.get("conflict") == "five_gates"
    _nothing_committed(db)


def test_two_vehicle_plan_produced_with_one_vehicle_less_is_rejected(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_vehicle_plan(db)
    _hold(db)
    _engine(monkeypatch, _candidate(_pair()[0]))
    with pytest.raises(DomainError) as caught:
        _approve(db, "k-two-short", inputs_loader=_loader)
    assert caught.value.details.get("conflict") == "five_gates"
    _nothing_committed(db)


def test_the_approve_route_uses_the_trusted_adapter_not_client_data() -> None:
    import inspect

    from app.api.v1 import planning

    source = inspect.getsource(planning.approve_plan)
    assert "recheck=five_gate_recheck" in source and "recheck=None" not in source
    assert planning.five_gate_recheck is approval_recheck.five_gate_recheck
