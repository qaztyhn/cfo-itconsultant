"""Lập kế hoạch (04 mục 7.1; US-PLN-01..08).

Nạp ngữ cảnh theo kho và chân trời 14 ngày → EngineConfig/OrderCtx/WarehouseCtx → engine.plan_order →
trong MỘT transaction: planning_run (+input_snapshot), fulfilment_plan + plan_vehicle, giữ chỗ
(ReservationService, KHÔNG khóa, cho phép vượt), đơn PLANNED/NO_FEASIBLE_DATE, PLAN_PROPOSED +
RESERVATION_HELD. Chạy lại bắt buộc lý do (CRITERIA_CHANGED_RERUN), giữ chỗ cũ released. suggest_replan():
4 tín hiệu (source_change, plan_invalidated, vehicle_issue, delivery_failed) →
planning_run(kind='replan_suggestion'), cộng lại tài nguyên của kế hoạch cũ của chính đơn vào ngữ cảnh,
KHÔNG giữ chỗ, alert REPLAN_SUGGESTED (06 mục 6.6; US-APR-04).

Owner: Dev 1 (A) — M4.
"""

from collections.abc import Iterable
from datetime import date, time
from decimal import Decimal

from app.core.config import MarketConfig
from app.engine.types import EngineConfig


def _dec(value: float | int) -> Decimal:
    """float của JSON cấu hình → Decimal qua chuỗi (tránh sai số nhị phân)."""
    return Decimal(str(value))


def _receiving_hours(cfg: MarketConfig) -> tuple[time, time]:
    windows = {tuple(v) for v in cfg.default_receiving_hours.values()}
    if len(windows) != 1:
        raise ValueError("default_receiving_hours must define one window (engine supports a single window)")
    opens, closes = next(iter(windows))
    return time.fromisoformat(opens), time.fromisoformat(closes)


def engine_config(cfg: MarketConfig, holidays: Iterable[date]) -> EngineConfig:
    """Chuyển MarketConfig của market (04 mục 8) + ngày lễ (ref.market_holiday) sang EngineConfig thuần.

    Mọi số cấu hình đến từ `ref.market.config` (09 bất biến 20); engine không đọc Pydantic/env (bất biến 6).
    """
    return EngineConfig(
        working_days=frozenset(cfg.working_days),
        default_receiving_hours=_receiving_hours(cfg),
        holidays=frozenset(holidays),
        search_days_max=cfg.search_days_max,
        reserve_safe_days=cfg.reserve_safe_days,
        eta_round_min=cfg.eta_round_min,
        delivery_share=_dec(cfg.delivery_share),
        final_inspection_hours=_dec(cfg.final_inspection_hours),
        flag_multiplier_cap=_dec(cfg.flag_multiplier_cap),
        loading_base_min=cfg.loading.base_min,
        loading_min_per_ton=cfg.loading.min_per_ton,
        unloading_base_min=cfg.unloading.base_min,
        unloading_min_per_ton=cfg.unloading.min_per_ton,
        driver_max_hours_day=_dec(cfg.driver_max_hours_day),
        receiving_lead_days=cfg.receiving_lead_days,
        max_arrival_spread_min=cfg.multi_vehicle.max_arrival_spread_min,
        w_km=_dec(cfg.rank.w_km),
        w_fill=_dec(cfg.rank.w_fill),
        dz_km_abs=_dec(cfg.rank.dz_km_abs),
        dz_km_pct=_dec(cfg.rank.dz_km_pct),
        dz_fill=_dec(cfg.rank.dz_fill),
        tie_eps=_dec(cfg.rank.tie_eps),
        allow_route_fallback=cfg.routing.allow_fallback,
    )


# T14 implementation. Keep the pure engine conversion above independent of DB.
from collections.abc import Awaitable, Callable
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.db import get_sessionmaker
from app.core.errors import DomainError
from app.domain.enums import OrderStatus
from app.domain.models.ops import CustomerOrder, DateNegotiation, OrderRouting
from app.domain.models.plan import FulfilmentPlan, PlanningRun, PlanVehicle
from app.domain.models.ref import Location, Market
from app.domain.transitions import transition
from app.engine.planner import plan_order
from app.engine.types import PlanCandidate, PlanningResult, RankWeights, WarehouseCtx
from app.engine.workload import compute_workload
from app.services import reservation_service
from app.services.planning_inputs import PlanningInputs, load_inputs

InputLoader = Callable[..., Awaitable[PlanningInputs]]
_VALID_KEYS = frozenset(
    {"target_date", "exclude_warehouse_ids", "exclude_vehicle_ids", "weights", "reason_code", "reason_text"}
)
_VALID_TRIGGERS = frozenset(
    {"source_change", "plan_invalidated", "vehicle_issue", "delivery_failed"}
)


def _fail(code: str, message: str) -> DomainError:
    return DomainError(code, message)


def _actor_id(actor: object | None) -> int:
    user_id = getattr(actor, "id", None)
    if not isinstance(user_id, int):
        raise _fail("AUTH_INVALID", "An active user is required.")
    return user_id


def _roles(actor: object | None) -> set[str]:
    return set(getattr(actor, "roles", ()))


def _validate_params(params: dict[str, object], actor: object | None) -> dict[str, object]:
    if set(params) - _VALID_KEYS:
        raise _fail("VALIDATION_ERROR", "Unknown planning parameter.")
    roles = _roles(actor)
    if "dispatcher" not in roles and params:
        raise _fail("FORBIDDEN", "Sales may only request the default plan.")
    for key in ("exclude_warehouse_ids", "exclude_vehicle_ids"):
        value = params.get(key, [])
        if not isinstance(value, list) or any(type(v) is not int or v <= 0 for v in value):
            raise _fail("VALIDATION_ERROR", f"Invalid {key}.")
        params[key] = sorted(set(value))
    if params.get("weights") is not None:
        value = params["weights"]
        if not isinstance(value, dict) or set(value) != {"w_km", "w_fill"}:
            raise _fail("VALIDATION_ERROR", "Both rank weights are required.")
        try:
            km, fill = Decimal(str(value["w_km"])), Decimal(str(value["w_fill"]))
        except (ValueError, TypeError) as exc:
            raise _fail("VALIDATION_ERROR", "Invalid rank weights.") from exc
        if not all(v.is_finite() and 0 <= v <= 1 for v in (km, fill)) or km + fill != 1:
            raise _fail("VALIDATION_ERROR", "Rank weights must be nonnegative and sum to 1.")
        params["weights"] = {"w_km": str(km), "w_fill": str(fill)}
    for key in ("reason_code", "reason_text"):
        if key in params and (not isinstance(params[key], str) or not params[key].strip()):
            raise _fail("VALIDATION_ERROR", f"Invalid {key}.")
    return params


def _weights(params: dict[str, object]) -> RankWeights | None:
    obj = params.get("weights")
    if not isinstance(obj, dict):
        return None
    return RankWeights(Decimal(str(obj["w_km"])), Decimal(str(obj["w_fill"])))


def _check_to_json(candidate: PlanCandidate) -> dict[str, object]:
    return {
        check.name: {"passed": check.passed, "code": check.code, "detail": check.detail}
        for check in candidate.checks
    }


def _line_payload(candidate: PlanCandidate) -> dict[str, object]:
    return {
        "prep_by_day": {d.isoformat(): str(h) for d, h in candidate.prep_by_day.items()},
        "labour_hours": str(candidate.prep_hours),
    }


def _candidate_row(run: PlanningRun, candidate: PlanCandidate, actor_id: int) -> FulfilmentPlan:
    return FulfilmentPlan(
        run_id=run.id,
        order_id=run.order_id,
        rank=candidate.rank,
        status="proposed",
        warehouse_id=candidate.warehouse_id,
        vehicle_count=candidate.vehicle_count,
        total_capacity_kg=candidate.total_capacity_kg,
        total_capacity_m3=sum((v.capacity_m3 for v in candidate.vehicles), Decimal(0)),
        target_date=candidate.target_date,
        goods_ready_at=candidate.goods_ready_at,
        loading_start_at=candidate.loading_start_at,
        depart_at=candidate.depart_at,
        eta_at=candidate.eta_at,
        trip_end_at=candidate.trip_end_at,
        distance_km=candidate.distance_km,
        drive_min=candidate.drive_min,
        prep_hours=candidate.prep_hours,
        capacity_fill=candidate.capacity_fill,
        score=candidate.score,
        score_breakdown={"score": str(candidate.score), "weights": {"w_km": "market", "w_fill": "market"}},
        complexity_points=candidate.complexity_points,
        planning_reserve_min=candidate.planning_reserve_min,
        route_provenance=candidate.route_provenance,
        workload=_line_payload(candidate),
        checks=_check_to_json(candidate),
        reason_codes=list(candidate.reason_codes),
        explanation=candidate.explanation,
        created_by=actor_id,
    )


async def _save_candidates(
    session: AsyncSession, run: PlanningRun, result: PlanningResult, actor_id: int
) -> None:
    for candidate in result.candidates:
        row = _candidate_row(run, candidate, actor_id)
        session.add(row)
        await session.flush()
        for vehicle in candidate.vehicles:
            session.add(
                PlanVehicle(
                    plan_id=row.id,
                    seq=vehicle.seq,
                    vehicle_id=vehicle.vehicle_id,
                    driver_employee_id=vehicle.driver_employee_id,
                    load_kg=vehicle.load_kg,
                    load_m3=vehicle.load_m3,
                    load_lines=[
                        {"line_no": number, "qty_base": str(qty)}
                        for number, qty in vehicle.load_lines
                    ],
                    loading_start_at=vehicle.loading_start_at,
                    depart_at=vehicle.depart_at,
                    eta_at=vehicle.eta_at,
                    trip_end_at=vehicle.trip_end_at,
                )
            )
    await session.flush()


async def _latest_run(session: AsyncSession, order_id: int) -> PlanningRun | None:
    return await session.scalar(
        select(PlanningRun)
        .where(PlanningRun.order_id == order_id)
        .order_by(PlanningRun.run_no.desc(), PlanningRun.id.desc())
        .limit(1)
    )


async def _authorize(
    session: AsyncSession, order_id: int, actor: object | None, *, lock: bool
) -> tuple[CustomerOrder, Market]:
    query = select(CustomerOrder).where(CustomerOrder.id == order_id)
    if lock:
        query = query.with_for_update()
    order = await session.scalar(query)
    if order is None:
        raise _fail("NOT_FOUND", "Order not found.")
    market = await session.get(Market, order.market_id)
    if market is None or getattr(actor, "market", None) != market.code.strip():
        raise _fail("NOT_FOUND", "Order not found.")
    roles = _roles(actor)
    if not roles.intersection({"dispatcher", "sales"}):
        raise _fail("FORBIDDEN", "Only Dispatcher or Sales may plan.")
    if "dispatcher" not in roles and (
        order.origin_store_id is None
        or order.origin_store_id not in getattr(actor, "location_ids", ())
    ):
        raise _fail("NOT_FOUND", "Order not found.")
    return order, market


async def _route_is_cfo(session: AsyncSession, order: CustomerOrder) -> None:
    route = await session.scalar(
        select(OrderRouting.route).where(
            OrderRouting.market_id == order.market_id,
            OrderRouting.external_ref == order.external_ref,
        )
    )
    if route != "cfo":
        raise _fail("PLAN_NOT_APPROVABLE", "CFO routing decision is not confirmed.")


async def _execute_plan(
    session: AsyncSession,
    order_id: int,
    actor: object,
    params: dict[str, object],
    loader: InputLoader,
) -> int:
    now = clock.now()
    order, market = await _authorize(session, order_id, actor, lock=True)
    await _route_is_cfo(session, order)
    params = _validate_params(dict(params), actor)
    existing = await _latest_run(session, order.id)
    roles = _roles(actor)
    if order.status not in ("SUBMITTED", "PLANNED", "NO_FEASIBLE_DATE"):
        raise _fail("ILLEGAL_TRANSITION", "Order is no longer eligible for planning.")
    if existing is not None and order.status == "PLANNED" and existing.result == "feasible":
        if (
            existing.params == params
            and existing.triggered_by == _actor_id(actor)
            and existing.hold_expires_at is not None
            and existing.hold_expires_at > now
        ):
            return existing.id  # concurrent/double-click retry; same actor and inputs
    is_rerun = existing is not None
    if is_rerun:
        if "dispatcher" not in roles:
            raise _fail("FORBIDDEN", "Only Dispatcher can change plan criteria or Plan Again.")
        if not (params.get("reason_code") or params.get("reason_text")):
            raise _fail("REASON_REQUIRED", "Plan Again requires an auditable reason.")
    if order.status in ("PLANNED", "NO_FEASIBLE_DATE"):
        changed = await transition(
            session, order.id, OrderStatus.SUBMITTED, "dispatcher", "Plan Again"
        )
        await record_decision(
            session,
            Action.CRITERIA_CHANGED_RERUN,
            "customer_order",
            str(order.id),
            order_id=order.id,
            reason_code=cast(str | None, params.get("reason_code")),
            reason_text=cast(str | None, params.get("reason_text")),
            before=changed.closed.before if changed.closed is not None else None,
            after={"requested_by": _actor_id(actor), "kind": "rerun"},
            actor_user_id=_actor_id(actor),
            actor_employee_id=getattr(actor, "employee_id", None),
            actor_role="dispatcher",
        )
    inputs = await loader(session, order, market, now=now, params=params)
    result = plan_order(inputs.order, list(inputs.warehouses), cast(EngineConfig, inputs.config), _weights(params))
    no = (existing.run_no + 1) if existing is not None else 1
    raw_rejections = [
        {
            "warehouse_id": rejected.warehouse_id,
            "vehicle_code": rejected.vehicle_code,
            "failed_check": rejected.failed_check,
            "code": rejected.code,
            "detail": rejected.detail,
        }
        for rejected in result.rejected
    ]
    workload = compute_workload(inputs.order.lines, cast(EngineConfig, inputs.config))
    snapshot = {
        **inputs.snapshot,
        "rejected_candidates": raw_rejections,
        "workload": {
            "labour_hours": str(workload.labour_hours),
            "lines": [str(item) for item in workload.line_hours],
        },
    }
    run = PlanningRun(
        order_id=order.id,
        order_version=order.version,
        triggered_by=_actor_id(actor),
        kind="rerun" if is_rerun else "initial",
        run_no=no,
        params=params,
        input_snapshot=snapshot,
        result=result.result,
        failed_check=result.failed_check,
        earliest_feasible_date=result.earliest_feasible_date,
        planning_reserve_min=result.planning_reserve_min,
        reserve_class=result.reserve_class,
    )
    session.add(run)
    await session.flush()
    await _save_candidates(session, run, result, _actor_id(actor))
    if result.result == "feasible":
        await reservation_service.hold(run.id, session=session)
        await transition(session, order.id, OrderStatus.PLANNED, "system")
    else:
        await transition(session, order.id, OrderStatus.NO_FEASIBLE_DATE, "system")
    order.planned_at = now
    await record_decision(
        session,
        Action.PLAN_PROPOSED,
        "planning_run",
        str(run.id),
        order_id=order.id,
        actor_user_id=_actor_id(actor),
        actor_employee_id=getattr(actor, "employee_id", None),
        actor_role="sales" if "dispatcher" not in roles else "dispatcher",
        snapshot={"order_version": order.version, "source_version": order.source_version},
        after={
            "run_no": no,
            "result": result.result,
            "ranked_plan_count": len(result.candidates),
            "hold_expires_at": run.hold_expires_at.isoformat() if run.hold_expires_at else None,
        },
    )
    return run.id


async def plan(
    order_id: int,
    actor: object | None,
    params: dict[str, object] | None = None,
    *,
    session: AsyncSession | None = None,
    inputs_loader: InputLoader = load_inputs,
) -> int:
    """One-transaction order → run → candidates → T15 hold → state + audit.

    inputs_loader is a trusted internal testing seam, never a request field.
    Re-running the same order locks its row and releases old holds before reserving.
    """
    if session is not None:
        return await _execute_plan(session, order_id, actor, params or {}, inputs_loader)
    async with get_sessionmaker()() as db, db.begin():
        return await _execute_plan(db, order_id, actor, params or {}, inputs_loader)


def _safe_json(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _vehicle_out(vehicle: PlanVehicle, *, compact: bool) -> dict[str, object]:
    if compact:
        return {
            "seq": vehicle.seq,
            "eta_at": vehicle.eta_at.isoformat(),
        }
    return {
        "seq": vehicle.seq,
        "vehicle_id": vehicle.vehicle_id,
        "driver_employee_id": vehicle.driver_employee_id,
        "load_kg": str(vehicle.load_kg),
        "load_m3": str(vehicle.load_m3),
        "load_lines": vehicle.load_lines,
        "loading_start_at": vehicle.loading_start_at.isoformat(),
        "depart_at": vehicle.depart_at.isoformat(),
        "eta_at": vehicle.eta_at.isoformat(),
        "trip_end_at": vehicle.trip_end_at.isoformat(),
    }


async def _plan_out(
    session: AsyncSession, row: FulfilmentPlan, *, compact: bool
) -> dict[str, object]:
    allocations = (
        await session.scalars(select(PlanVehicle).where(PlanVehicle.plan_id == row.id).order_by(PlanVehicle.seq))
    ).all()
    basic: dict[str, object] = {
        "id": row.id,
        "rank": row.rank,
        "status": row.status,
        "target_date": row.target_date.isoformat(),
        "eta_at": row.eta_at.isoformat(),
        "vehicle_count": row.vehicle_count,
        "vehicles": [_vehicle_out(v, compact=compact) for v in allocations],
    }
    if compact:
        return basic
    warehouse = await session.get(Location, row.warehouse_id)
    return basic | {
        "warehouse": {"id": row.warehouse_id, "name": warehouse.name if warehouse else ""},
        "total_capacity_kg": str(row.total_capacity_kg),
        "total_capacity_m3": str(row.total_capacity_m3),
        "goods_ready_at": row.goods_ready_at.isoformat(),
        "loading_start_at": row.loading_start_at.isoformat(),
        "depart_at": row.depart_at.isoformat(),
        "trip_end_at": row.trip_end_at.isoformat(),
        "distance_km": str(row.distance_km),
        "drive_min": row.drive_min,
        "prep_hours": str(row.prep_hours),
        "capacity_fill": str(row.capacity_fill),
        "score": str(row.score),
        "score_breakdown": row.score_breakdown,
        "complexity_points": row.complexity_points,
        "planning_reserve_min": row.planning_reserve_min,
        "route_provenance": row.route_provenance,
        "checks": row.checks,
        "reason_codes": row.reason_codes,
        "explanation": row.explanation,
    }


async def get_run(
    run_id: int, actor: object, *, session: AsyncSession | None = None
) -> dict[str, object]:
    """Read the persisted run; Sales sees rank1/hold/ETA only, never scores or driver/GPS."""
    if session is None:
        async with get_sessionmaker()() as db:
            return await get_run(run_id, actor, session=db)
    run = await session.get(PlanningRun, run_id)
    if run is None:
        raise _fail("NOT_FOUND", "Planning run not found.")
    order, _ = await _authorize(session, run.order_id, actor, lock=False)
    compact = "dispatcher" not in _roles(actor)
    plans = (
        await session.scalars(
            select(FulfilmentPlan)
            .where(FulfilmentPlan.run_id == run.id)
            .order_by(FulfilmentPlan.rank)
        )
    ).all()
    if compact:
        plans = [plan for plan in plans if plan.rank == 1]
    response: dict[str, object] = {
        "id": run.id,
        "order_id": order.id,
        "run_no": run.run_no,
        "kind": run.kind,
        "result": run.result,
        "reserve_class": run.reserve_class,
        "hold_expires_at": run.hold_expires_at.isoformat() if run.hold_expires_at else None,
        "hold_extensions": run.hold_extensions,
        "plans": [await _plan_out(session, plan, compact=compact) for plan in plans],
    }
    if compact:
        response["sales_approvable"] = bool(
            plans
            and run.reserve_class == "safe"
            and run.hold_expires_at is not None
            and run.hold_expires_at > clock.now()
            and plans[0].status == "proposed"
            and plans[0].vehicle_count == 1
            and plans[0].target_date == order.date_to
            and run.kind == "initial"
        )
        response["sales_block_reason"] = (
            None if response["sales_approvable"] else "PLAN_NOT_APPROVABLE"
        )
    else:
        response.update(
            {
                "failed_check": run.failed_check,
                "earliest_feasible_date": run.earliest_feasible_date.isoformat()
                if run.earliest_feasible_date
                else None,
                "planning_reserve_min": run.planning_reserve_min,
                "workload": run.input_snapshot.get("workload", {}),
                "rejected_candidates": run.input_snapshot.get("rejected_candidates", []),
                "transfer_suggestions": [],
            }
        )
    return response


async def get_plan(
    plan_id: int, actor: object, *, session: AsyncSession
) -> dict[str, object]:
    plan = await session.get(FulfilmentPlan, plan_id)
    if plan is None:
        raise _fail("NOT_FOUND", "Plan not found.")
    await _authorize(session, plan.order_id, actor, lock=False)
    compact = "dispatcher" not in _roles(actor)
    if compact and plan.rank != 1:
        raise _fail("NOT_FOUND", "Plan not found.")
    return await _plan_out(session, plan, compact=compact)


async def list_runs(
    order_id: int, actor: object, *, session: AsyncSession
) -> dict[str, object]:
    await _authorize(session, order_id, actor, lock=False)
    runs = (
        await session.scalars(
            select(PlanningRun).where(PlanningRun.order_id == order_id).order_by(PlanningRun.run_no.desc())
        )
    ).all()
    compact = "dispatcher" not in _roles(actor)
    return {
        "items": [
            {
                "id": run.id,
                "order_id": run.order_id,
                "run_no": run.run_no,
                "result": run.result,
                "hold_expires_at": run.hold_expires_at.isoformat() if run.hold_expires_at else None,
                **({} if compact else {"kind": run.kind, "failed_check": run.failed_check}),
            }
            for run in runs
        ]
    }


async def list_date_negotiations(
    order_id: int, actor: object, *, session: AsyncSession
) -> dict[str, object]:
    if "dispatcher" not in _roles(actor):
        raise _fail("FORBIDDEN", "Only Dispatcher may read negotiation history.")
    await _authorize(session, order_id, actor, lock=False)
    rows = (
        await session.scalars(
            select(DateNegotiation)
            .where(DateNegotiation.order_id == order_id)
            .order_by(DateNegotiation.contacted_at.desc())
        )
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "proposed_date": row.proposed_date.isoformat(),
                "outcome": row.outcome,
                "channel": row.channel,
                "contacted_at": row.contacted_at.isoformat(),
                "remind_at": row.remind_at.isoformat() if row.remind_at else None,
            }
            for row in rows
        ]
    }


async def suggest_replan(order_id: int, trigger: str) -> int | None:
    """Fail closed until T07 integrates the approved source-change event and D7 history attestations.

    No live plan is changed here. T16 must not automatically approve suggestions.
    """
    if trigger not in _VALID_TRIGGERS:
        raise _fail("VALIDATION_ERROR", "Unknown replanning signal.")
    return None
