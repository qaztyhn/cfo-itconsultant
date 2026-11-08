"""Reservation lifecycle (05 §7, BR-RES-01..04, US-RES-01).

Callers may inject an AsyncSession to join one planning/approval transaction.
No stock/capacity advisory locks are acquired while placing a provisional hold.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import MarketConfig
from app.core.db import get_sessionmaker
from app.core.errors import DomainError
from app.domain.models.ops import CustomerOrder, OrderLine, OrderRouting
from app.domain.models.plan import (
    FulfilmentPlan,
    PlanningRun,
    PlanVehicle,
    PrepReservation,
    StockReservation,
    VehicleReservation,
)
from app.domain.models.ref import Market

_RESERVATIONS = (StockReservation, PrepReservation, VehicleReservation)
_ACTIVE = ("held", "committed")
_PRECISION = Decimal("0.001")  # prep_reservation.hours numeric(8,3)


def _error(code: str, message: str, **details: object) -> DomainError:
    return DomainError(code, message, details)


async def _locked_run(session: AsyncSession, run_id: int) -> PlanningRun:
    run = await session.scalar(select(PlanningRun).where(PlanningRun.id == run_id).with_for_update())
    if run is None:
        raise _error("NOT_FOUND", "Planning run not found.")
    return run


async def _config(session: AsyncSession, order_id: int) -> tuple[CustomerOrder, Market, MarketConfig]:
    record = (
        await session.execute(
            select(CustomerOrder, Market)
            .join(Market, Market.id == CustomerOrder.market_id)
            .where(CustomerOrder.id == order_id)
        )
    ).one_or_none()
    if record is None:
        raise _error("NOT_FOUND", "Order not found.")
    order, market = record
    config = MarketConfig.model_validate(market.config)
    if config.hold.ttl_min <= 0 or not 0 <= config.hold.max_extensions <= 2:
        raise _error("VALIDATION_ERROR", "Invalid market hold configuration.")
    return order, market, config


def _prep_by_day(plan: FulfilmentPlan) -> dict[date, Decimal]:
    """T14 handoff: workload.prep_by_day maps ISO dates to decimal hours.

    Never infer preparation reservations from the delivery date or total hours.
    The maximum per day across alternatives holds once per order/warehouse/day.
    """
    workload = plan.workload
    days = workload.get("prep_by_day") if isinstance(workload, dict) else None
    if not isinstance(days, dict) or not days:
        raise _error("VALIDATION_ERROR", "Plan is missing its preparation calendar.", plan_id=plan.id)
    result: dict[date, Decimal] = {}
    for raw_day, raw_hours in days.items():
        try:
            day = date.fromisoformat(raw_day) if isinstance(raw_day, str) else None
            hours = Decimal(str(raw_hours))
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise _error("VALIDATION_ERROR", "Invalid preparation reservation.", plan_id=plan.id) from exc
        if day is None or not hours.is_finite() or hours <= 0:
            raise _error("VALIDATION_ERROR", "Invalid preparation reservation.", plan_id=plan.id)
        result[day] = hours.quantize(_PRECISION, rounding=ROUND_CEILING)
    return result


async def _has_any(session: AsyncSession, run_id: int) -> bool:
    for model in _RESERVATIONS:
        if await session.scalar(select(model.id).where(model.run_id == run_id).limit(1)) is not None:
            return True
    return False


async def _other_active(session: AsyncSession, order_id: int, run_id: int) -> bool:
    for model in _RESERVATIONS:
        if (
            await session.scalar(
                select(model.id)
                .where(model.order_id == order_id, model.run_id != run_id, model.status.in_(_ACTIVE))
                .limit(1)
            )
            is not None
        ):
            return True
    return False


async def _hold(session: AsyncSession, run_id: int) -> None:
    run = await _locked_run(session, run_id)
    now = clock.now()
    if run.kind == "replan_suggestion" or run.result != "feasible":
        raise _error("PLAN_NOT_APPROVABLE", "This planning run cannot hold resources.")
    order, _, cfg = await _config(session, run.order_id)
    if order.version != run.order_version or order.status not in ("SUBMITTED", "PLANNED"):
        raise _error("ILLEGAL_TRANSITION", "Planning run is not current.")
    route = await session.scalar(
        select(OrderRouting.route).where(
            OrderRouting.market_id == order.market_id,
            OrderRouting.external_ref == order.external_ref,
        )
    )
    if route != "cfo":
        raise _error("PLAN_NOT_APPROVABLE", "Order is not assigned to CFO planning.")
    if run.hold_expires_at is not None:
        if run.hold_expires_at <= now:
            raise _error("HOLD_EXPIRED", "Planning hold expired.", run_id=run.id)
        if await _has_any(session, run.id):
            return  # idempotent: do not duplicate resources or audit
        raise _error("ILLEGAL_TRANSITION", "Hold deadline exists without reservations.")
    if await _has_any(session, run.id) or await _other_active(session, order.id, run.id):
        raise _error("ILLEGAL_TRANSITION", "Release the previous hold before re-running.")
    plans = (
        await session.scalars(
            select(FulfilmentPlan).where(FulfilmentPlan.run_id == run.id).order_by(FulfilmentPlan.rank)
        )
    ).all()
    if not plans or len(plans) > 3 or any(p.status != "proposed" or p.order_id != order.id for p in plans):
        raise _error("PLAN_NOT_APPROVABLE", "Planning run has no valid proposed plans.")
    lines = (await session.scalars(select(OrderLine).where(OrderLine.order_id == order.id))).all()
    if not lines or any(
        ln.global_product_id is None or ln.qty_base is None or ln.qty_base <= 0 for ln in lines
    ):
        raise _error("SKU_UNMAPPED", "All order lines require a confirmed quantity.")
    quantities: dict[int, Decimal] = defaultdict(Decimal)
    for ln in lines:
        assert ln.global_product_id is not None and ln.qty_base is not None
        quantities[ln.global_product_id] += ln.qty_base

    by_warehouse: dict[int, dict[date, Decimal]] = {}
    for plan in plans:
        calendar = _prep_by_day(plan)
        held = by_warehouse.setdefault(plan.warehouse_id, {})
        for day, hours in calendar.items():
            held[day] = max(held.get(day, Decimal(0)), hours)
        vehicles = (
            await session.scalars(
                select(PlanVehicle).where(PlanVehicle.plan_id == plan.id).order_by(PlanVehicle.seq)
            )
        ).all()
        if not vehicles or len(vehicles) != plan.vehicle_count:
            raise _error("VALIDATION_ERROR", "Vehicle allocation is incomplete.", plan_id=plan.id)
        for vehicle in vehicles:
            if vehicle.trip_end_at <= vehicle.loading_start_at:
                raise _error("VALIDATION_ERROR", "Invalid vehicle interval.", plan_id=plan.id)
            session.add(
                VehicleReservation(
                    run_id=run.id,
                    plan_id=plan.id,
                    plan_vehicle_id=vehicle.id,
                    order_id=order.id,
                    vehicle_id=vehicle.vehicle_id,
                    driver_employee_id=vehicle.driver_employee_id,
                    during=Range(vehicle.loading_start_at, vehicle.trip_end_at, bounds="[)"),
                    status="held",
                )
            )
    for warehouse_id, calendar in sorted(by_warehouse.items()):
        for product_id, qty in sorted(quantities.items()):
            session.add(
                StockReservation(
                    run_id=run.id,
                    order_id=order.id,
                    warehouse_id=warehouse_id,
                    global_product_id=product_id,
                    qty=qty,
                    status="held",
                )
            )
        for day, hours in sorted(calendar.items()):
            session.add(
                PrepReservation(
                    run_id=run.id,
                    order_id=order.id,
                    warehouse_id=warehouse_id,
                    work_date=day,
                    resource="labour",
                    hours=hours,
                    status="held",
                )
            )
    run.hold_expires_at = now + timedelta(minutes=cfg.hold.ttl_min)
    run.hold_extensions = 0
    await session.flush()  # DB EXCLUDE prevents overlapping vehicles/drivers across orders
    await record_decision(
        session,
        Action.RESERVATION_HELD,
        "planning_run",
        str(run.id),
        order_id=order.id,
        actor_user_id=run.triggered_by,
        after={"hold_expires_at": run.hold_expires_at.isoformat(), "plans": [p.id for p in plans]},
    )


async def hold(run_id: int, *, session: AsyncSession | None = None) -> None:
    """Book all proposed alternatives without stock/capacity advisory locks."""
    if session is not None:
        await _hold(session, run_id)
        return
    async with get_sessionmaker()() as db, db.begin():
        await _hold(db, run_id)


def _actor_id(actor: object) -> int | None:
    value = getattr(actor, "id", None)
    return value if isinstance(value, int) else None


async def _extend(session: AsyncSession, run_id: int, actor: object) -> None:
    run = await _locked_run(session, run_id)
    now = clock.now()
    order, market, cfg = await _config(session, run.order_id)
    roles = set(getattr(actor, "roles", ()))
    if "dispatcher" not in roles and "sales" not in roles:
        raise _error("FORBIDDEN", "This role cannot extend a planning hold.")
    if getattr(actor, "market", market.code) != market.code:
        raise _error("NOT_FOUND", "Planning run not found.")
    if "dispatcher" not in roles and order.origin_store_id not in getattr(actor, "location_ids", ()):
        raise _error("NOT_FOUND", "Planning run not found.")
    if run.kind == "replan_suggestion" or run.hold_expires_at is None or run.hold_expires_at <= now:
        raise _error("HOLD_EXPIRED", "Planning hold expired.", run_id=run.id)
    if run.hold_extensions >= cfg.hold.max_extensions:
        raise _error("HOLD_EXTENSION_LIMIT", "Maximum hold extensions reached.", run_id=run.id)
    proposed = await session.scalar(
        select(FulfilmentPlan.id).where(
            FulfilmentPlan.run_id == run.id,
            FulfilmentPlan.status == "proposed",
        )
    )
    if proposed is None or not await _has_any(session, run.id):
        raise _error("PLAN_NOT_APPROVABLE", "No active proposed plan to extend.")
    before = run.hold_expires_at
    run.hold_expires_at = before + timedelta(minutes=cfg.hold.ttl_min)
    run.hold_extensions += 1
    await session.flush()
    await record_decision(
        session,
        Action.HOLD_EXTENDED,
        "planning_run",
        str(run.id),
        order_id=run.order_id,
        actor_user_id=_actor_id(actor),
        actor_employee_id=getattr(actor, "employee_id", None),
        actor_role="dispatcher" if "dispatcher" in roles else "sales",
        before={"hold_expires_at": before.isoformat()},
        after={"hold_expires_at": run.hold_expires_at.isoformat(), "hold_extensions": run.hold_extensions},
    )


async def extend(run_id: int, actor: object, *, session: AsyncSession | None = None) -> None:
    """Extend a still-live hold by one configured TTL (maximum two times)."""
    if session is not None:
        await _extend(session, run_id, actor)
        return
    async with get_sessionmaker()() as db, db.begin():
        await _extend(db, run_id, actor)


async def _expire_due(session: AsyncSession) -> int:
    now = clock.now()
    runs = (
        await session.scalars(
            select(PlanningRun)
            .where(
                PlanningRun.hold_expires_at <= now,
                PlanningRun.kind != "replan_suggestion",
            )
            .order_by(PlanningRun.id)
            .with_for_update(skip_locked=True)
        )
    ).all()
    processed = 0
    for run in runs:
        counts: dict[str, int] = {}
        for name, model in (
            ("stock", StockReservation),
            ("prep", PrepReservation),
            ("vehicle", VehicleReservation),
        ):
            changed = (
                await session.scalars(
                    update(model)
                    .where(model.run_id == run.id, model.status == "held")
                    .values(status="expired")
                    .returning(model.id)
                    .execution_options(synchronize_session=False)
                )
            ).all()
            counts[name] = len(changed)
        plans = (
            await session.scalars(
                update(FulfilmentPlan)
                .where(FulfilmentPlan.run_id == run.id, FulfilmentPlan.status == "proposed")
                .values(status="expired")
                .returning(FulfilmentPlan.id)
                .execution_options(synchronize_session=False)
            )
        ).all()
        if plans or any(counts.values()):
            processed += 1
            await record_decision(
                session,
                Action.HOLD_EXPIRED,
                "planning_run",
                str(run.id),
                order_id=run.order_id,
                after={"expired_plans": sorted(plans), "resources": counts},
            )
    return processed


async def expire_due(*, session: AsyncSession | None = None) -> int:
    """Expire holds and proposed plans atomically; retries are idempotent."""
    if session is not None:
        return await _expire_due(session)
    async with get_sessionmaker()() as db, db.begin():
        return await _expire_due(db)


async def _commit_plan(session: AsyncSession, plan_id: int, resources_validated: bool) -> None:
    plan = await session.get(FulfilmentPlan, plan_id)
    if plan is None:
        raise _error("NOT_FOUND", "Plan not found.")
    run = await _locked_run(session, plan.run_id)
    if not resources_validated or plan.status not in ("approved", "manual"):
        raise _error("PLAN_NOT_APPROVABLE", "Approval must first validate and lock resources.")
    if run.kind == "replan_suggestion":
        raise _error("PLAN_NOT_APPROVABLE", "Suggested replan needs direct approval allocation.")
    stock = (await session.scalars(select(StockReservation).where(StockReservation.run_id == run.id))).all()
    prep = (await session.scalars(select(PrepReservation).where(PrepReservation.run_id == run.id))).all()
    vehicles = (
        await session.scalars(select(VehicleReservation).where(VehicleReservation.run_id == run.id))
    ).all()
    resources = (stock, prep, vehicles)
    if not stock or not prep or not vehicles or not any(v.plan_id == plan_id for v in vehicles):
        raise _error("PLAN_NOT_APPROVABLE", "Plan has no complete reservation set.")
    if not any(r.status == "held" for group in resources for r in group):
        if any(r.status == "committed" for group in resources for r in group):
            return  # commit retry: no duplicate audit, no resource mutation
        raise _error("HOLD_EXPIRED", "Planning hold expired.", run_id=run.id)
    if run.hold_expires_at is None or run.hold_expires_at <= clock.now():
        raise _error("HOLD_EXPIRED", "Planning hold expired.", run_id=run.id)
    chosen_days = _prep_by_day(plan)
    for res in stock:
        if res.status == "held":
            res.status = "committed" if res.warehouse_id == plan.warehouse_id else "released"
    for res in prep:
        if res.status != "held":
            continue
        hours = chosen_days.get(res.work_date)
        if res.warehouse_id != plan.warehouse_id or hours is None:
            res.status = "released"
        else:
            res.hours = hours
            res.status = "committed"
    for res in vehicles:
        if res.status == "held":
            res.status = "committed" if res.plan_id == plan_id else "released"
    await session.flush()
    await record_decision(
        session,
        Action.RESERVATION_COMMITTED,
        "fulfilment_plan",
        str(plan_id),
        order_id=plan.order_id,
        plan_id=plan_id,
        after={"warehouse_id": plan.warehouse_id, "status": "committed"},
    )


async def commit_plan(
    plan_id: int, *, resources_validated: bool = False, session: AsyncSession | None = None
) -> None:
    """Called inside T16 approval transaction, *after* resource locks and recheck.

    T15 deliberately does not implement approval locks or automatic approvals.
    """
    if session is not None:
        await _commit_plan(session, plan_id, resources_validated)
        return
    async with get_sessionmaker()() as db, db.begin():
        await _commit_plan(db, plan_id, resources_validated)


async def _release_order(session: AsyncSession, order_id: int) -> None:
    order = await session.scalar(select(CustomerOrder).where(CustomerOrder.id == order_id).with_for_update())
    if order is None:
        raise _error("NOT_FOUND", "Order not found.")
    counts: dict[str, int] = {}
    for name, model in (
        ("stock", StockReservation),
        ("prep", PrepReservation),
        ("vehicle", VehicleReservation),
    ):
        released = (
            await session.scalars(
                update(model)
                .where(model.order_id == order_id, model.status.in_(_ACTIVE))
                .values(status="released")
                .returning(model.id)
                .execution_options(synchronize_session=False)
            )
        ).all()
        counts[name] = len(released)
    if any(counts.values()):
        await record_decision(
            session,
            Action.RESERVATION_RELEASED,
            "customer_order",
            str(order_id),
            order_id=order_id,
            after={"released": counts},
        )


async def release_order(order_id: int, *, session: AsyncSession | None = None) -> None:
    """Release held/committed resources; preserve consumed ones and audit history.

    T16/transition() is responsible for closing plans, trips and order promises.
    """
    if session is not None:
        await _release_order(session, order_id)
        return
    async with get_sessionmaker()() as db, db.begin():
        await _release_order(db, order_id)
