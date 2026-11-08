"""Pure order-planning orchestration (04 §6.2; US-PLN-01..07).

The service injects market-local time, warehouses, resource snapshots and routes.
No database, clock, network or environment access is permitted in the engine.
"""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import cast

from app.engine.atp import check_atp, stock_check
from app.engine.delivery import choose_vehicle_sets, plan_delivery, planning_reserve_min
from app.engine.explain import explanation_for, reason_codes_for, reserve_class
from app.engine.gate import all_passed, first_failure, furthest_failed_check
from app.engine.schedule import schedule_preparation
from app.engine.scoring import rank_candidates
from app.engine.types import (
    CheckResult,
    EngineConfig,
    OrderCtx,
    PlanCandidate,
    PlanningResult,
    RankWeights,
    RejectedCandidate,
    ReserveClassT,
    WarehouseCtx,
    Workload,
)
from app.engine.workload import compute_workload, warehouse_labour_hours


def _reject(warehouse_id: int, checks: tuple[CheckResult, ...]) -> RejectedCandidate:
    failure = first_failure(checks)
    if failure is None:
        raise ValueError("A rejected candidate must have a failing gate")
    return RejectedCandidate(warehouse_id, None, failure.name, failure.code, failure.detail)


def _attempt(
    order: OrderCtx, warehouse: WarehouseCtx, cfg: EngineConfig, workload: Workload
) -> tuple[list[PlanCandidate], list[RejectedCandidate], list[tuple[CheckResult, ...]]]:
    """Run the existing ATP → preparation → truck/date/safety gates for one warehouse."""
    candidates: list[PlanCandidate] = []
    rejected: list[RejectedCandidate] = []
    reached: list[tuple[CheckResult, ...]] = []
    atp = check_atp(order, warehouse, cfg)
    stock = stock_check(atp)
    if not stock.passed or atp.stock_ready_date is None:
        checks: tuple[CheckResult, ...] = (stock,)
        return candidates, [_reject(warehouse.id, checks)], [checks]

    prep_hours = warehouse_labour_hours(workload, warehouse.efficiency)
    prep = schedule_preparation(prep_hours, atp.stock_ready_date, order.now, warehouse, cfg)
    first = (stock, prep.check)
    if not prep.check.passed or prep.goods_ready_at is None or prep.loading_start_at is None:
        return candidates, [_reject(warehouse.id, first)], [first]

    vehicle_sets = choose_vehicle_sets(order, warehouse, prep.loading_start_at.date())
    if not vehicle_sets:
        failed = CheckResult(
            "truck",
            False,
            "NO_TRUCK_FIT",
            {"message": "No compatible vehicle set can carry the entire order."},
        )
        checks = (*first, failed)
        return candidates, [_reject(warehouse.id, checks)], [checks]

    for vehicles in vehicle_sets:
        option, delivery_checks = plan_delivery(order, warehouse, vehicles, prep.loading_start_at, cfg)
        # The delivery function may detect absent official warehouse loading shifts.
        checks = (
            (stock, *delivery_checks)
            if (delivery_checks and delivery_checks[0].name == "preparation")
            else (*first, *delivery_checks)
        )
        reached.append(checks)
        if option is None or not all_passed(checks):
            rejected.append(_reject(warehouse.id, checks))
            continue
        if warehouse.route is None:
            raise AssertionError("A feasible delivery must include route data")
        assignments = option.vehicles
        if not assignments:
            raise AssertionError("A feasible delivery requires at least one vehicle")
        candidates.append(
            PlanCandidate(
                warehouse_id=warehouse.id,
                vehicles=assignments,
                target_date=option.target_date,
                goods_ready_at=prep.goods_ready_at,
                loading_start_at=min(v.loading_start_at for v in assignments),
                depart_at=min(v.depart_at for v in assignments),
                eta_at=max(v.eta_at for v in assignments),
                trip_end_at=max(v.trip_end_at for v in assignments),
                distance_km=warehouse.route.distance_km,
                drive_min=warehouse.route.drive_min,
                prep_hours=prep_hours,
                capacity_fill=prep.capacity_fill,
                complexity_points=int(atp.classification == "after_inbound") + int(prep.after_cutoff),
                planning_reserve_min=option.planning_reserve_min,
                route_provenance=warehouse.route.provenance,
                checks=checks,
                prep_by_day=prep.prep_by_day,
            )
        )
    return candidates, rejected, reached


def _unrestricted_order(order: OrderCtx, cfg: EngineConfig) -> OrderCtx:
    """Relax only the requested date; keep real warehouse/vehicle/driver gates."""
    return replace(
        order,
        date_mode="latest",
        date_from=None,
        date_to=order.now.date() + timedelta(days=cfg.search_days_max - 1),
    )


def _earliest_options(order: OrderCtx, warehouse: WarehouseCtx, cfg: EngineConfig) -> list[PlanCandidate]:
    relaxed = _unrestricted_order(order, cfg)
    workload = compute_workload(relaxed.lines, cfg)
    options, _, _ = _attempt(relaxed, warehouse, cfg, workload)
    return options


def plan_order(
    order: OrderCtx, warehouses: list[WarehouseCtx], cfg: EngineConfig, weights: RankWeights | None = None
) -> PlanningResult:
    """Return up to three ranked, explained options or an explicit infeasible result.

    This function never persists holds, changes customer dates, or approves plans.
    """
    workload = compute_workload(order.lines, cfg)
    feasible: list[PlanCandidate] = []
    rejected: list[RejectedCandidate] = []
    reached: list[tuple[CheckResult, ...]] = []
    for warehouse in sorted(warehouses, key=lambda w: w.id):
        options, failures, checks = _attempt(order, warehouse, cfg, workload)
        feasible.extend(options)
        rejected.extend(failures)
        reached.extend(checks)

    if feasible:
        earliest_by_wh: dict[int, datetime | None] = {}
        for wh in warehouses:
            if any(candidate.warehouse_id == wh.id for candidate in feasible):
                relaxed = _earliest_options(order, wh, cfg)
                earliest_by_wh[wh.id] = min((candidate.eta_at for candidate in relaxed), default=None)
        corrected: list[PlanCandidate] = []
        for candidate in feasible:
            earliest_eta = earliest_by_wh[candidate.warehouse_id]
            if earliest_eta is None:
                # A distant exact-date option may be feasible beyond the reserve-search horizon.
                corrected.append(candidate)
            else:
                corrected.append(
                    replace(
                        candidate,
                        planning_reserve_min=planning_reserve_min(order, earliest_eta, cfg),
                    )
                )
        ranked = rank_candidates(corrected, cfg, weights)
        names = {wh.id: wh.name for wh in warehouses}
        explained = tuple(
            replace(
                candidate,
                reason_codes=reason_codes_for(candidate, len(ranked), cfg),
                explanation=explanation_for(candidate, len(ranked), names[candidate.warehouse_id], cfg),
            )
            for candidate in ranked
        )
        winner = explained[0]
        return PlanningResult(
            "feasible",
            explained,
            tuple(rejected),
            None,
            None,
            cast(ReserveClassT, reserve_class(winner.planning_reserve_min, cfg)),
            winner.planning_reserve_min,
            (),
        )

    earliest = [
        option.target_date for warehouse in warehouses for option in _earliest_options(order, warehouse, cfg)
    ]
    # WarehouseCtx does not carry warehouse-to-warehouse route distances or pair lead times.
    # Never fabricate transfer suggestions; service must supply the missing route matrix.
    return PlanningResult(
        "infeasible",
        (),
        tuple(rejected),
        furthest_failed_check(reached),
        min(earliest, default=None),
        "infeasible",
        None,
        (),
    )
