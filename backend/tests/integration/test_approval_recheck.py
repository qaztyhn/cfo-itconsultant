"""T16 trusted five-gate recheck adapter (04 section 7.10): real PostgreSQL, fresh engine run.

The engine is replaced by a deterministic stand-in (as in test_planning_service.py): these tests prove the
adapter's contract with approval_service, not the engine's maths. The production loader is exercised too, to
show that a real market fails closed (the D7 history marker is not persisted).
"""

from datetime import UTC, datetime
from functools import partial
from typing import Any

import pytest

from app.core.errors import DomainError
from app.engine.types import CheckResult, PlanCandidate, PlanningResult, VehicleAssignment
from app.services import approval_recheck, approval_service, planning_service, reservation_service
from app.services.approval_recheck import five_gate_recheck
from tests.integration.conftest import execute, fetch
from tests.integration.test_approval_service import _actor, _run
from tests.integration.test_approval_service import db as db
from tests.integration.test_planning_service import TARGET, D, _loader

pytestmark = pytest.mark.integration

GATES = ("stock", "preparation", "truck", "site_date", "safety")


def _candidate(
    *, safety: bool = True, driver: int = 1, vehicle: int = 1, warehouse: int = 1
) -> PlanCandidate:
    checks = tuple(CheckResult(name, name != "safety" or safety, name.upper(), {}) for name in GATES)
    unit = VehicleAssignment(
        seq=1, vehicle_id=vehicle, vehicle_code="V-1", capacity_kg=D("8000"), capacity_m3=D("30"),
        driver_employee_id=driver, load_kg=D("1000"), load_m3=D("2"), load_lines=(),
        loading_start_at=datetime(2026, 11, 10, 6, 30, tzinfo=UTC),
        depart_at=datetime(2026, 11, 10, 7, tzinfo=UTC),
        eta_at=datetime(2026, 11, 10, 9, tzinfo=UTC),
        trip_end_at=datetime(2026, 11, 10, 11, tzinfo=UTC),
    )  # fmt: skip
    return PlanCandidate(
        warehouse_id=warehouse, vehicles=(unit,), target_date=TARGET, goods_ready_at=unit.loading_start_at,
        loading_start_at=unit.loading_start_at, depart_at=unit.depart_at, eta_at=unit.eta_at,
        trip_end_at=unit.trip_end_at, distance_km=D("42"), drive_min=120, prep_hours=D("1.5"),
        capacity_fill=D("0.5"), complexity_points=0, planning_reserve_min=2880, route_provenance="ors",
        checks=checks, prep_by_day={TARGET: D("1.5")}, rank=1,
    )  # fmt: skip


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
        (_candidate(driver=2),),  # same vehicle, different driver: not the held plan
        (_candidate(vehicle=2),),  # different vehicle
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
    assert _state(db) == ("proposed", "PLANNED", "held")  # nothing committed, hold intact


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
    assert _state(db) == ("proposed", "PLANNED", "held")


def test_five_gate_recheck_propagates_input_failures_instead_of_approving(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hold(db)
    _engine(monkeypatch, _candidate())

    async def stale(*_a: object, **_k: object) -> object:
        raise DomainError("RESOURCE_CONFLICT", "Market stock snapshot unavailable or stale.")

    with pytest.raises(DomainError, match="stale"):
        _approve(db, "k-stale", inputs_loader=stale)
    assert _state(db) == ("proposed", "PLANNED", "held")


def test_the_production_loader_fails_closed_without_the_d7_history_marker(db: str) -> None:
    """No injected loader: the real planning inputs cannot be built/approved for this market today."""
    _hold(db)
    with pytest.raises(DomainError):
        _approve(db, "k-real")
    assert _state(db) == ("proposed", "PLANNED", "held")


def test_the_recheck_never_approves_a_missing_plan(db: str) -> None:
    with pytest.raises(DomainError) as caught:
        _run(db, lambda s: five_gate_recheck(s, 999, inputs_loader=_loader))
    assert caught.value.code == "NOT_FOUND"


def test_the_approve_route_uses_the_trusted_adapter_not_client_data() -> None:
    import inspect

    from app.api.v1 import planning

    source = inspect.getsource(planning.approve_plan)
    assert "recheck=five_gate_recheck" in source and "recheck=None" not in source
    assert planning.five_gate_recheck is approval_recheck.five_gate_recheck
