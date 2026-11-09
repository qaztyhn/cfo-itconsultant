"""T16 trusted five-gate recheck for plan approval (04 section 7.10, 09 invariants).

Called by `approval_service.approve` AFTER the approval locks are taken. It never accepts client data: it
reloads the order, the market and every planning input from the database (source version, confirmed mappings,
official shifts, vehicle/driver duties, stock and routes), runs the engine again and answers whether
**the same plan** (warehouse, date, every vehicle with its driver, load and times, preparation hours) is
still feasible with all five gates passed.

Fail closed:
- any input that cannot be loaded (stale stock, unmapped SKU, missing route, ...) raises: no approval;
- the source order changed since the run was proposed -> every gate is False;
- the stored plan is no longer produced by the engine -> every gate is False;
- driver eligibility depends on the 56-day duty-history completeness marker, which is not persisted yet
  (D7), so a real market cannot pass the `safety` gate until that contract exists. This adapter does not
  bypass it.
The order's own held reservations are excluded by the input loader (04 section 7.10), so a plan is never
blocked by its own hold.
"""

from collections.abc import Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder
from app.domain.models.plan import FulfilmentPlan, PlanningRun, PlanVehicle
from app.domain.models.ref import Market
from app.engine.types import EngineConfig, PlanCandidate, VehicleAssignment
from app.services import planning_service
from app.services.approval_service import RecheckProof
from app.services.planning_inputs import load_inputs

GATES = ("stock", "preparation", "truck", "site_date", "safety")


_CENT = Decimal("0.01")
_MILLI = Decimal("0.001")


def _q(value: Decimal, scale: Decimal) -> Decimal:
    """Round like the NUMERIC column the stored value went through, so equal plans compare equal."""
    return value.quantize(scale, rounding=ROUND_HALF_UP)


def _same_instant(left: datetime, right: datetime) -> bool:
    return left.tzinfo is not None and right.tzinfo is not None and left == right


def _lines(stored: object) -> list[tuple[int, Decimal]] | None:
    if not isinstance(stored, list):
        return None
    try:
        return sorted((int(row["line_no"]), Decimal(str(row["qty_base"]))) for row in stored)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None


def _same_vehicle(produced: VehicleAssignment, row: PlanVehicle) -> bool:
    produced_lines = sorted((int(number), Decimal(qty)) for number, qty in produced.load_lines)
    return (
        produced.seq == row.seq
        and produced.vehicle_id == row.vehicle_id
        and produced.driver_employee_id == row.driver_employee_id
        and _q(produced.load_kg, _CENT) == row.load_kg
        and _q(produced.load_m3, _MILLI) == row.load_m3
        and _lines(row.load_lines) == produced_lines
        and _same_instant(produced.loading_start_at, row.loading_start_at)
        and _same_instant(produced.depart_at, row.depart_at)
        and _same_instant(produced.eta_at, row.eta_at)
        and _same_instant(produced.trip_end_at, row.trip_end_at)
    )


def _same_prep(candidate: PlanCandidate, plan: FulfilmentPlan) -> bool:
    try:
        stored = {
            date.fromisoformat(day): Decimal(str(hours))
            for day, hours in plan.workload["prep_by_day"].items()
        }
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
        return False
    return stored.keys() == candidate.prep_by_day.keys() and all(
        stored[day] == candidate.prep_by_day[day] for day in stored
    )


def _same_plan(candidate: PlanCandidate, plan: FulfilmentPlan, stored: Sequence[PlanVehicle]) -> bool:
    """True only if the engine reproduced the HELD plan exactly.

    The reservations (stock, preparation hours, vehicles, drivers) were taken for the stored plan, so any
    difference in who drives what, how it is loaded, or when anything happens means the held resources are no
    longer the ones the engine would allocate: the proof must fail (the dispatcher plans again). Quantities
    are compared at the stored NUMERIC scale and instants as timezone-aware values.
    """
    ordered = sorted(stored, key=lambda row: row.seq)
    produced = sorted(candidate.vehicles, key=lambda unit: unit.seq)
    return (
        candidate.warehouse_id == plan.warehouse_id
        and candidate.target_date == plan.target_date
        and plan.vehicle_count == len(ordered) == len(produced) == candidate.vehicle_count
        and _q(candidate.total_capacity_kg, _CENT) == plan.total_capacity_kg
        and _q(sum((v.capacity_m3 for v in produced), Decimal(0)), _CENT) == plan.total_capacity_m3
        and _same_instant(candidate.goods_ready_at, plan.goods_ready_at)
        and _same_instant(candidate.loading_start_at, plan.loading_start_at)
        and _same_instant(candidate.depart_at, plan.depart_at)
        and _same_instant(candidate.eta_at, plan.eta_at)
        and _same_instant(candidate.trip_end_at, plan.trip_end_at)
        and _q(candidate.distance_km, _CENT) == plan.distance_km
        and candidate.drive_min == plan.drive_min
        and _q(candidate.prep_hours, _MILLI) == plan.prep_hours
        and candidate.planning_reserve_min == plan.planning_reserve_min
        and candidate.route_provenance == plan.route_provenance
        and _same_prep(candidate, plan)
        and all(_same_vehicle(unit, row) for unit, row in zip(produced, ordered, strict=True))
    )


async def five_gate_recheck(
    session: AsyncSession,
    plan_id: int,
    *,
    inputs_loader: planning_service.InputLoader = load_inputs,
) -> RecheckProof:
    plan = await session.get(FulfilmentPlan, plan_id)
    run = await session.get(PlanningRun, plan.run_id) if plan is not None else None
    order = await session.get(CustomerOrder, plan.order_id) if plan is not None else None
    market = await session.get(Market, order.market_id) if order is not None else None
    if plan is None or run is None or order is None or market is None:
        raise DomainError("NOT_FOUND", "Plan not found.")
    now = clock.now()
    failed: dict[str, bool] = {name: False for name in GATES}
    proposed_source = run.input_snapshot.get("source_version")
    if proposed_source is not None and proposed_source != order.source_version:
        return RecheckProof(order.version, order.source_version, plan.id, failed, now)
    stored = (await session.scalars(select(PlanVehicle).where(PlanVehicle.plan_id == plan.id))).all()
    inputs = await inputs_loader(session, order, market, now=now, params=dict(run.params))
    # Called through the module so tests can substitute the engine exactly as test_planning_service does.
    result = planning_service.plan_order(  # type: ignore[attr-defined]
        inputs.order,
        list(inputs.warehouses),
        cast(EngineConfig, inputs.config),
        planning_service._weights(dict(run.params)),
    )
    match = next((c for c in result.candidates if _same_plan(c, plan, stored)), None)
    if match is None:
        return RecheckProof(order.version, order.source_version, plan.id, failed, now)
    passed: dict[str, bool] = {check.name: check.passed is True for check in match.checks}
    gates: dict[str, bool] = {name: passed.get(name, False) for name in GATES}
    return RecheckProof(order.version, order.source_version, plan.id, gates, now)
