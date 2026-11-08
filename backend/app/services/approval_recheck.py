"""T16 trusted five-gate recheck for plan approval (04 section 7.10, 09 invariants).

Called by `approval_service.approve` AFTER the approval locks are taken. It never accepts client data: it
reloads the order, the market and every planning input from the database (source version, confirmed mappings,
official shifts, vehicle/driver duties, stock and routes), runs the engine again and answers whether
**the same plan** (same warehouse, same vehicles with the same drivers, same target date) is still feasible
with all five gates passed.

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

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder
from app.domain.models.plan import FulfilmentPlan, PlanningRun, PlanVehicle
from app.domain.models.ref import Market
from app.engine.types import EngineConfig, PlanCandidate
from app.services import planning_service
from app.services.approval_service import RecheckProof
from app.services.planning_inputs import load_inputs

GATES = ("stock", "preparation", "truck", "site_date", "safety")


def _same_plan(candidate: PlanCandidate, plan: FulfilmentPlan, stored: set[tuple[int, int]]) -> bool:
    produced = {(v.vehicle_id, v.driver_employee_id) for v in candidate.vehicles}
    return (
        candidate.warehouse_id == plan.warehouse_id
        and candidate.target_date == plan.target_date
        and produced == stored
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
    stored = {
        (row.vehicle_id, row.driver_employee_id)
        for row in (await session.scalars(select(PlanVehicle).where(PlanVehicle.plan_id == plan.id))).all()
    }
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
