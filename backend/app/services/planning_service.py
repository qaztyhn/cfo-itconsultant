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

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import MarketConfig
from app.core.db import get_sessionmaker
from app.core.errors import DomainError
from app.domain.enums import OrderStatus
from app.domain.models.ops import Alert, CustomerOrder, DateNegotiation, OrderRouting
from app.domain.models.plan import FulfilmentPlan, PlanningRun, PlanVehicle
from app.domain.models.ref import Location, Market, Vehicle
from app.domain.transitions import transition
from app.engine.planner import plan_order
from app.engine.types import EngineConfig, PlanCandidate, PlanningResult, RankWeights
from app.engine.workload import compute_workload
from app.services import reservation_service
from app.services.planning_inputs import PlanningInputs, load_inputs


def _dec(value: float | int) -> Decimal:
    """float của JSON cấu hình → Decimal qua chuỗi (tránh sai số nhị phân)."""
    return Decimal(str(value))


def _receiving_hours(cfg: MarketConfig) -> tuple[time, time]:
    windows = {tuple(v) for v in cfg.default_receiving_hours.values()}
    if len(windows) != 1:
        raise ValueError("default_receiving_hours must specify one supported window")
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


InputLoader = Callable[..., Awaitable[PlanningInputs]]
_VALID_KEYS = frozenset(
    {"target_date", "exclude_warehouse_ids", "exclude_vehicle_ids", "weights", "reason_code", "reason_text"}
)
_VALID_TRIGGERS = frozenset({"source_change", "plan_invalidated", "vehicle_issue", "delivery_failed"})


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
    workload: dict[str, object] = {
        "prep_by_day": {d.isoformat(): str(h) for d, h in candidate.prep_by_day.items()},
        "labour_hours": str(candidate.prep_hours),
    }
    if candidate.planned_start_prep is not None:
        workload["planned_start_prep"] = candidate.planned_start_prep.isoformat()
    return workload


def _candidate_row(
    run: PlanningRun, candidate: PlanCandidate, actor_id: int | None, weights: RankWeights
) -> FulfilmentPlan:
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
        score_breakdown={
            "score": str(candidate.score),
            "w_km": str(weights.w_km),
            "w_fill": str(weights.w_fill),
        },
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
    session: AsyncSession,
    run: PlanningRun,
    result: PlanningResult,
    actor_id: int | None,
    weights: RankWeights,
) -> None:
    for candidate in result.candidates:
        row = _candidate_row(run, candidate, actor_id, weights)
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
                        {"line_no": number, "qty_base": str(qty)} for number, qty in vehicle.load_lines
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
        order.origin_store_id is None or order.origin_store_id not in getattr(actor, "location_ids", ())
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
        if not (params.get("reason_code") or params.get("reason_text")):
            raise _fail("REASON_REQUIRED", "Plan Again requires an auditable reason.")
    if order.status in ("PLANNED", "NO_FEASIBLE_DATE"):
        changed = await transition(
            session,
            order.id,
            OrderStatus.SUBMITTED,
            "dispatcher" if "dispatcher" in roles else "sales",
            "Plan Again",
            sales_plan_again_order_id=order.id if "dispatcher" not in roles else None,
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
            actor_role="dispatcher" if "dispatcher" in roles else "sales",
        )
    inputs = await loader(session, order, market, now=now, params=params)
    result = plan_order(
        inputs.order, list(inputs.warehouses), cast(EngineConfig, inputs.config), _weights(params)
    )
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
    config = cast(EngineConfig, inputs.config)
    effective_weights = _weights(params) or RankWeights(config.w_km, config.w_fill)
    await _save_candidates(session, run, result, _actor_id(actor), effective_weights)
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


def _plain(value: Decimal) -> str:
    """Capacity as a plain decimal string without trailing zeros (12000.000 -> "12000")."""
    return format(value.normalize(), "f")


def _vehicle_ref(vehicle: Vehicle) -> dict[str, object]:
    """Public fleet fields only: no plate, licence, availability, GPS or driver data."""
    return {
        "id": vehicle.id,
        "code": vehicle.code,
        "name": vehicle.name,
        "capacity_kg": _plain(vehicle.capacity_kg),
        "capacity_m3": _plain(vehicle.capacity_m3),
    }


def _vehicle_out(
    vehicle: PlanVehicle, *, compact: bool, catalog: Mapping[int, Vehicle] | None = None
) -> dict[str, object]:
    if compact:
        return {
            "seq": vehicle.seq,
            "eta_at": vehicle.eta_at.isoformat(),
        }
    record = (catalog or {}).get(vehicle.vehicle_id)
    if record is None:
        # A stored allocation always references ref.vehicle (FK); fail closed instead of a partial DTO.
        raise _fail("INTERNAL_ERROR", "Plan vehicle record is unavailable.")
    return {
        "seq": vehicle.seq,
        "vehicle_id": vehicle.vehicle_id,
        "driver_employee_id": vehicle.driver_employee_id,
        "vehicle": _vehicle_ref(record),
        "load_kg": str(vehicle.load_kg),
        "load_m3": str(vehicle.load_m3),
        "load_lines": vehicle.load_lines,
        "loading_start_at": vehicle.loading_start_at.isoformat(),
        "depart_at": vehicle.depart_at.isoformat(),
        "eta_at": vehicle.eta_at.isoformat(),
        "trip_end_at": vehicle.trip_end_at.isoformat(),
    }


async def _load_allocations(session: AsyncSession, plan_ids: Sequence[int]) -> dict[int, list[PlanVehicle]]:
    """All allocations of the given plans in one query, ordered by seq."""
    grouped: dict[int, list[PlanVehicle]] = {plan_id: [] for plan_id in plan_ids}
    if plan_ids:
        rows = await session.scalars(
            select(PlanVehicle).where(PlanVehicle.plan_id.in_(plan_ids)).order_by(PlanVehicle.seq)
        )
        for row in rows:
            grouped[row.plan_id].append(row)
    return grouped


async def _load_catalog(session: AsyncSession, allocations: Iterable[PlanVehicle]) -> dict[int, Vehicle]:
    """Referenced ref.vehicle rows in one query (no per-vehicle lookups)."""
    ids = {a.vehicle_id for a in allocations}
    if not ids:
        return {}
    return {v.id: v for v in await session.scalars(select(Vehicle).where(Vehicle.id.in_(ids)))}


async def _plan_out(
    session: AsyncSession,
    row: FulfilmentPlan,
    *,
    compact: bool,
    allocations: Sequence[PlanVehicle] | None = None,
    catalog: Mapping[int, Vehicle] | None = None,
) -> dict[str, object]:
    if allocations is None:
        allocations = (await _load_allocations(session, [row.id]))[row.id]
    if catalog is None and not compact:
        catalog = await _load_catalog(session, allocations)
    basic: dict[str, object] = {
        "id": row.id,
        "rank": row.rank,
        "status": row.status,
        "target_date": row.target_date.isoformat(),
        "eta_at": row.eta_at.isoformat(),
        "vehicle_count": row.vehicle_count,
        "vehicles": [_vehicle_out(v, compact=compact, catalog=catalog) for v in allocations],
    }
    if compact:
        warehouse = await session.get(Location, row.warehouse_id)
        # Sales receives option-level feasibility, not driver identities, gate diagnostics or scores.
        checks = row.checks if isinstance(row.checks, dict) else {}
        return basic | {
            "warehouse": {"id": row.warehouse_id, "name": warehouse.name if warehouse else ""},
            "checks": {
                name: {"passed": checks[name].get("passed") is True, "code": checks[name].get("code")}
                for name in ("stock", "preparation", "truck", "site_date", "safety")
                if isinstance(checks.get(name), dict)
            },
        }
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


async def get_run(run_id: int, actor: object, *, session: AsyncSession | None = None) -> dict[str, object]:
    """Read ranked options with role-scoped DTOs; never disclose drivers/GPS to Sales."""
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
            select(FulfilmentPlan).where(FulfilmentPlan.run_id == run.id).order_by(FulfilmentPlan.rank)
        )
    ).all()
    by_plan = await _load_allocations(session, [plan.id for plan in plans])
    catalog = None if compact else await _load_catalog(session, (a for v in by_plan.values() for a in v))
    response: dict[str, object] = {
        "id": run.id,
        "order_id": order.id,
        "run_no": run.run_no,
        "kind": run.kind,
        "result": run.result,
        "reserve_class": run.reserve_class,
        "hold_expires_at": run.hold_expires_at.isoformat() if run.hold_expires_at else None,
        "hold_extensions": run.hold_extensions,
        "requested_date": order.date_to.isoformat(),
        "plans": [
            await _plan_out(session, plan, compact=compact, allocations=by_plan[plan.id], catalog=catalog)
            for plan in plans
        ],
    }
    if compact:
        latest = await _latest_run(session, order.id)
        live = (
            latest is not None
            and latest.id == run.id
            and order.status == "PLANNED"
            and order.version == run.order_version
            and run.result == "feasible"
            and run.kind in ("initial", "rerun")
            and run.hold_expires_at is not None
            and run.hold_expires_at > clock.now()
        )
        for item in response["plans"]:
            stored = next(p for p in plans if p.id == item["id"])
            item["requires_date_agreement"] = stored.target_date != order.date_to
            item["approvable"] = bool(
                live
                and stored.rank in (1, 2, 3)
                and stored.status == "proposed"
                and all(
                    isinstance(stored.checks, dict)
                    and isinstance(stored.checks.get(g), dict)
                    and stored.checks[g].get("passed") is True
                    for g in ("stock", "preparation", "truck", "site_date", "safety")
                )
            )
        response["sales_approvable"] = any(p["approvable"] for p in response["plans"])
        response["sales_block_reason"] = None if response["sales_approvable"] else "PLAN_NOT_APPROVABLE"
    else:
        response.update(
            {
                "failed_check": run.failed_check,
                "earliest_feasible_date": (
                    run.earliest_feasible_date.isoformat() if run.earliest_feasible_date else None
                ),
                "planning_reserve_min": run.planning_reserve_min,
                "workload": run.input_snapshot.get("workload", {}),
                "rejected_candidates": run.input_snapshot.get("rejected_candidates", []),
            }
        )
    return response


async def get_plan(plan_id: int, actor: object, *, session: AsyncSession) -> dict[str, object]:
    plan = await session.get(FulfilmentPlan, plan_id)
    if plan is None:
        raise _fail("NOT_FOUND", "Plan not found.")
    order, _ = await _authorize(session, plan.order_id, actor, lock=False)
    compact = "dispatcher" not in _roles(actor)
    if compact and plan.rank not in (1, 2, 3):
        raise _fail("NOT_FOUND", "Plan not found.")
    detail = await _plan_out(session, plan, compact=compact)
    if compact:
        detail["requires_date_agreement"] = plan.target_date != order.date_to
    return detail


async def list_runs(order_id: int, actor: object, *, session: AsyncSession) -> dict[str, object]:
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


async def list_date_negotiations(order_id: int, actor: object, *, session: AsyncSession) -> dict[str, object]:
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


async def suggest_replan(
    order_id: int,
    trigger: str,
    *,
    session: AsyncSession | None = None,
    inputs_loader: InputLoader = load_inputs,
) -> int | None:
    """Create an unheld advisory run for an approved/pre-dispatch order.

    Only T07-approved signals may call this internal service; it never approves
    automatically or mutates the currently committed plan. After DISPATCHED
    the dispatcher receives an alert instead of a replacement plan.
    """
    if trigger not in _VALID_TRIGGERS:
        raise _fail("VALIDATION_ERROR", "Unknown replanning signal.")
    if session is None:
        async with get_sessionmaker()() as db, db.begin():
            return await suggest_replan(order_id, trigger, session=db, inputs_loader=inputs_loader)
    order = await session.scalar(select(CustomerOrder).where(CustomerOrder.id == order_id).with_for_update())
    if order is None:
        raise _fail("NOT_FOUND", "Order not found.")
    if order.status not in ("APPROVED", "PREPARING", "GOODS_READY", "LOADED", "FAILED", "DISPATCHED"):
        return None
    latest = await _latest_run(session, order.id)
    if (
        latest is not None
        and latest.kind == "replan_suggestion"
        and latest.params.get("trigger") == trigger
        and latest.order_version == order.version
        and latest.input_snapshot.get("source_version") == order.source_version
    ):
        return latest.id
    market = await session.get(Market, order.market_id)
    if market is None:
        raise _fail("NOT_FOUND", "Market not found.")
    now = clock.now()
    if order.status == "DISPATCHED":
        dedupe = f"replan-after-dispatch:{order.id}:{order.version}:{trigger}"
        existing_alert = await session.scalar(select(Alert.id).where(Alert.dedupe_key == dedupe))
        if existing_alert is None:
            session.add(
                Alert(
                    order_id=order.id,
                    market_id=market.id,
                    level="warning",
                    type="REPLAN_SUGGESTED",
                    message="Order needs dispatcher review; delivery is already dispatched.",
                    target_roles=["dispatcher"],
                    dedupe_key=dedupe,
                )
            )
        return None
    # Excluding reservations from this very order mirrors 04 §7.10.
    inputs = await inputs_loader(session, order, market, now=now, params={})
    cfg = cast(EngineConfig, inputs.config)
    result = plan_order(inputs.order, list(inputs.warehouses), cfg, None)
    run = PlanningRun(
        order_id=order.id,
        order_version=order.version,
        triggered_by=None,
        kind="replan_suggestion",
        run_no=1 if latest is None else latest.run_no + 1,
        params={"trigger": trigger},
        input_snapshot=inputs.snapshot,
        result=result.result,
        failed_check=result.failed_check,
        earliest_feasible_date=result.earliest_feasible_date,
        planning_reserve_min=result.planning_reserve_min,
        reserve_class=result.reserve_class,
    )
    session.add(run)
    await session.flush()
    weights = RankWeights(cfg.w_km, cfg.w_fill)
    await _save_candidates(session, run, result, None, weights)
    dedupe_key = f"replan:{order.id}:{run.id}"
    session.add(
        Alert(
            order_id=order.id,
            market_id=market.id,
            level="warning",
            type="REPLAN_SUGGESTED",
            message="A replacement plan is available for dispatcher review.",
            target_roles=["dispatcher"],
            dedupe_key=dedupe_key,
        )
    )
    await record_decision(
        session,
        Action.REPLAN_SUGGESTED,
        "planning_run",
        str(run.id),
        order_id=order.id,
        snapshot={
            "trigger": trigger,
            "existing_approved_plan_id": order.approved_plan_id,
            "order_version": order.version,
        },
        after={"new_run_id": run.id, "result": result.result, "hold_created": False},
    )
    return run.id
