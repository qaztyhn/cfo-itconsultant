"""Thin planning HTTP boundary (06 §6). Role and store scope enforced server-side.

T16 approval is intentionally fail-closed without its trusted source/driver
recheck adapter; no client-supplied five-gate proof is accepted.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Header
from pydantic import BaseModel, Field

from app.core.errors import DomainError
from app.deps import AuthUser, DbSession
from app.services import approval_service, planning_service, reservation_service
from app.services.approval_recheck import five_gate_recheck

router = APIRouter(tags=["planning"])


class PlanningParams(BaseModel):
    target_date: str | None = None
    exclude_warehouse_ids: list[int] = Field(default_factory=list)
    exclude_vehicle_ids: list[int] = Field(default_factory=list)
    weights: dict[str, float] | None = None
    reason_code: str | None = None
    reason_text: str | None = None


@router.post("/orders/{order_id}/plan")
async def run_plan(
    order_id: int,
    user: AuthUser,
    db: DbSession,
    body: Annotated[PlanningParams | None, Body()] = None,
) -> dict[str, object]:
    """New planning_run for an eligible CFO order; Plan Again never copies the order."""
    params = (
        {k: v for k, v in body.model_dump(exclude_none=True).items() if v not in ([], {})}
        if body is not None
        else {}
    )
    run_id = await planning_service.plan(order_id, user, params, session=db)
    return await planning_service.get_run(run_id, user, session=db)


@router.get("/orders/{order_id}/planning-runs")
async def list_runs(order_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
    """Scoped, chronological planning run history."""
    return await planning_service.list_runs(order_id, user, session=db)


@router.get("/planning-runs/{run_id}")
async def get_run(run_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
    """Dispatcher: diagnostics; Sales: rank1, ETA and hold only."""
    return await planning_service.get_run(run_id, user, session=db)


@router.post("/planning-runs/{run_id}/extend")
async def extend_hold(run_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
    """Extend live hold once; T15 enforces maximum two and store scope."""
    await reservation_service.extend(run_id, user, session=db)
    return await planning_service.get_run(run_id, user, session=db)


@router.post("/planning-runs/{run_id}/keep-current")
async def keep_current(
    run_id: int, user: AuthUser, body: Annotated[dict[str, object], Body()]
) -> dict[str, object]:
    """Replan-suggestion keep-current requires T16/T07 adapter, no silent success."""
    reason = body.get("reason_text")
    if not isinstance(reason, str) or not reason.strip():
        raise DomainError("REASON_REQUIRED", "Keep-current requires an auditable reason.")
    await approval_service.keep_current(run_id, user, reason)
    return {"run_id": run_id, "status": "kept"}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
    """Scoped detail. Sales cannot enumerate alternative ranks or see driver data."""
    return await planning_service.get_plan(plan_id, user, session=db)


@router.post("/plans/{plan_id}/approve")
async def approve_plan(
    plan_id: int,
    user: AuthUser,
    db: DbSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    body: Annotated[dict[str, object] | None, Body()] = None,
) -> dict[str, object]:
    """T16 transaction with the trusted fresh five-gate recheck (never client data).

    The 56-day duty-history completeness marker (D7) is not persisted yet, so the `safety` gate keeps failing
    closed for real markets until that contract exists; this wiring does not bypass it.
    """
    return await approval_service.approve(
        plan_id,
        user,
        body or {},
        idempotency_key,
        session=db,
        recheck=five_gate_recheck,
    )


@router.post("/orders/{order_id}/manual-plan")
async def manual_plan(
    order_id: int,
    user: AuthUser,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    body: Annotated[dict[str, object], Body()],
) -> dict[str, object]:
    """T16 manual-plan guard: rejects unverified proposals rather than bypassing gates."""
    return await approval_service.manual_plan(order_id, user, body, idempotency_key)


@router.post("/orders/{order_id}/date-negotiations")
async def create_date_negotiation(
    order_id: int, user: AuthUser, body: Annotated[dict[str, object], Body()]
) -> dict[str, object]:
    """Record customer negotiation; does not silently change the promised date."""
    record_id = await approval_service.record_date_negotiation(order_id, user, body)
    return {"id": record_id}


@router.get("/orders/{order_id}/date-negotiations")
async def list_date_negotiations(order_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
    """Dispatcher-only scoped negotiation history."""
    return await planning_service.list_date_negotiations(order_id, user, session=db)


@router.get("/orders/{order_id}/transfer-suggestions")
async def transfer_suggestions(order_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
    """No synthetic warehouse-to-warehouse distances; T18 owns real suggestions."""
    await planning_service.list_runs(order_id, user, session=db)
    return {"items": []}
