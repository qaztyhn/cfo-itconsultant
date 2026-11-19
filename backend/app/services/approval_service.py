"""Transactional plan approval (T16; 04 §7, 06 §6.3, DEC-HOLD-001).

Safety boundary: the source/roster/engine recheck MUST be supplied by a trusted
server adapter (T14/T12), never by the request payload. Missing recheck fails
closed. T16 owns locks, stock/labour recheck, state transition and audit.
The planning API is owned by T14 and is deliberately not edited here.
"""

import hashlib
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import MarketConfig, get_settings
from app.core.db import get_sessionmaker
from app.core.errors import DomainError
from app.domain.enums import OrderStatus
from app.domain.models.audit import DecisionLog
from app.domain.models.hr import Attendance, DriverStaff, EmployeeShiftSchedule, ShiftTemplate, WarehouseStaff
from app.domain.models.ops import (
    CustomerOrder,
    DateNegotiation,
    DeliveryTrip,
    EtaForecast,
    IdempotencyKey,
    Notification,
    OrderRouting,
    StockSnapshot,
    TripStop,
)
from app.domain.models.plan import (
    FulfilmentPlan,
    PlanningRun,
    PlanVehicle,
    PrepReservation,
    StockReservation,
    VehicleReservation,
)
from app.domain.models.ref import Market, Vehicle
from app.domain.transitions import transition
from app.services import alert_service, notify_service, reservation_service
from app.services.wms_mode import require_simulated_or_off


@dataclass(frozen=True)
class RecheckProof:
    """Trusted output of a fresh engine invocation under approval locks.

    The adapter must re-read source version, confirmed mappings, market shifts,
    vehicle/driver duties and all five gates; never accept client-provided proofs.
    """

    order_version: int
    source_version: int
    plan_id: int
    gates: dict[str, bool]
    checked_at: datetime


Recheck = Callable[[AsyncSession, int], Awaitable[RecheckProof]]
_GATE_NAMES = frozenset({"stock", "preparation", "truck", "site_date", "safety"})


def _fail(code: str, message: str, **details: object) -> DomainError:
    return DomainError(code, message, details)


def _roles(actor: object) -> set[str]:
    return set(getattr(actor, "roles", ()))


def _actor_id(actor: object) -> int:
    value = getattr(actor, "id", None)
    if not isinstance(value, int):
        raise _fail("AUTH_INVALID", "Active user required.")
    return value


def _reason(payload: dict[str, object]) -> tuple[str | None, str | None]:
    code = payload.get("reason_code")
    details = payload.get("reason_text")
    if code is not None and (not isinstance(code, str) or not code.strip()):
        raise _fail("VALIDATION_ERROR", "Invalid reason code.")
    if details is not None and not isinstance(details, str):
        raise _fail("VALIDATION_ERROR", "Invalid reason.")
    return code, details


def _digest(plan_id: int, payload: dict[str, object]) -> str:
    data = json.dumps(
        {"plan_id": plan_id, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()
    return hashlib.sha256(data).hexdigest()


async def _claim(
    session: AsyncSession, key: str, user_id: int, plan_id: int, payload: dict[str, object]
) -> tuple[IdempotencyKey, dict[str, object] | None]:
    if not isinstance(key, str) or not 1 <= len(key) <= 200:
        raise _fail("VALIDATION_ERROR", "Idempotency-Key is required.")
    endpoint = f"POST /plans/{plan_id}/approve"
    digest = _digest(plan_id, payload)
    await session.execute(
        insert(IdempotencyKey)
        .values(key=key, user_id=user_id, endpoint=endpoint, request_hash=digest)
        .on_conflict_do_nothing(index_elements=["key", "user_id"])
    )
    saved = await session.scalar(
        select(IdempotencyKey)
        .where(IdempotencyKey.key == key, IdempotencyKey.user_id == user_id)
        .with_for_update()
    )
    if saved is None or saved.request_hash != digest or saved.endpoint != endpoint:
        raise _fail("IDEMPOTENCY_CONFLICT", "Key was used for a different request.")
    if saved.response_body is not None and saved.response_status == 200:
        return saved, dict(saved.response_body)
    if saved.response_status is not None:
        raise _fail("IDEMPOTENCY_CONFLICT", "The prior request is not replayable.")
    return saved, None


async def _order_and_plan(
    session: AsyncSession, plan_id: int
) -> tuple[CustomerOrder, FulfilmentPlan, PlanningRun, Market]:
    selected = await session.get(FulfilmentPlan, plan_id)
    if selected is None:
        raise _fail("NOT_FOUND", "Plan not found.")
    order = await session.scalar(
        select(CustomerOrder).where(CustomerOrder.id == selected.order_id).with_for_update()
    )
    if order is None:
        raise _fail("NOT_FOUND", "Order not found.")
    run = await session.scalar(select(PlanningRun).where(PlanningRun.id == selected.run_id).with_for_update())
    plan = await session.scalar(select(FulfilmentPlan).where(FulfilmentPlan.id == plan_id).with_for_update())
    market = await session.get(Market, order.market_id)
    if run is None or plan is None or market is None:
        raise _fail("NOT_FOUND", "Planning context not found.")
    return order, plan, run, market


async def _advisory(session: AsyncSession, key: str) -> None:
    # Advisory locks are scoped to this transaction. Hash collisions merely
    # serialize unrelated resources and cannot allow over-commit.
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key})


async def _reserve_locks(
    session: AsyncSession,
    warehouse_id: int,
    stocks: list[StockReservation],
    prep: list[PrepReservation],
    assignments: list[PlanVehicle],
) -> None:
    """Fixed global lock order: warehouse -> product -> labour date -> vehicle -> driver."""
    for item in sorted(stocks, key=lambda v: (v.warehouse_id, v.global_product_id)):
        await _advisory(session, f"stock:{item.warehouse_id}:{item.global_product_id}")
    for item in sorted(prep, key=lambda v: (v.warehouse_id, v.work_date)):
        await _advisory(session, f"labour:{item.warehouse_id}:{item.work_date.isoformat()}")
    vehicle_ids = sorted({v.vehicle_id for v in assignments})
    driver_ids = sorted({v.driver_employee_id for v in assignments})
    vehicles = (
        await session.scalars(
            select(Vehicle).where(Vehicle.id.in_(vehicle_ids)).order_by(Vehicle.id).with_for_update()
        )
    ).all()
    drivers = (
        await session.scalars(
            select(DriverStaff)
            .where(DriverStaff.employee_id.in_(driver_ids))
            .order_by(DriverStaff.employee_id)
            .with_for_update()
        )
    ).all()
    if len(vehicles) != len(vehicle_ids) or len(drivers) != len(driver_ids):
        raise _fail("RESOURCE_CONFLICT", "A selected vehicle or driver is no longer available.")
    for vehicle in vehicles:
        if vehicle.home_warehouse_id != warehouse_id or vehicle.status != "available":
            raise _fail("RESOURCE_CONFLICT", "Vehicle is no longer available.", conflict="vehicle")
    for driver in drivers:
        if driver.home_warehouse_id != warehouse_id:
            raise _fail(
                "RESOURCE_CONFLICT", "Driver is no longer assigned to the warehouse.", conflict="driver"
            )


async def _stock_available(
    session: AsyncSession,
    stock: list[StockReservation],
    order_id: int,
    now: datetime,
    cfg: MarketConfig,
    *,
    sales: bool,
) -> None:
    for entry in stock:
        snapshot = await session.get(StockSnapshot, (entry.warehouse_id, entry.global_product_id))
        if (
            snapshot is None
            or snapshot.as_of < now - timedelta(minutes=cfg.stale_stock_min)
            or snapshot.as_of > now + timedelta(minutes=cfg.stale_stock_min)
        ):
            raise _fail("RESOURCE_CONFLICT", "Stock snapshot unavailable or stale.", conflict="stock")
        committed = await session.scalar(
            select(func.coalesce(func.sum(StockReservation.qty), 0)).where(
                StockReservation.warehouse_id == entry.warehouse_id,
                StockReservation.global_product_id == entry.global_product_id,
                StockReservation.order_id != order_id,
                StockReservation.status == "committed",
            )
        )
        # Sales cannot resolve an outstanding competing order's provisional
        # commitment; delegate instead of silently choosing a winner.
        other_held = Decimal(0)
        if sales:
            other_held = Decimal(
                await session.scalar(
                    select(func.coalesce(func.sum(StockReservation.qty), 0))
                    .join(PlanningRun, StockReservation.run_id == PlanningRun.id)
                    .where(
                        StockReservation.warehouse_id == entry.warehouse_id,
                        StockReservation.global_product_id == entry.global_product_id,
                        StockReservation.order_id != order_id,
                        StockReservation.status == "held",
                        PlanningRun.hold_expires_at > now,
                    )
                )
                or 0
            )
        available = snapshot.on_hand - snapshot.wms_reserved - Decimal(committed or 0) - other_held
        if entry.qty <= 0 or available < entry.qty:
            raise _fail("RESOURCE_CONFLICT", "Insufficient stock at approval.", conflict="stock")


async def _labour_available(
    session: AsyncSession,
    prep: list[PrepReservation],
    order_id: int,
    market: Market,
    cfg: MarketConfig,
    *,
    sales: bool,
) -> None:
    local_today = clock.now().astimezone(ZoneInfo(market.timezone)).date()
    for item in prep:
        roster = (
            await session.execute(
                select(EmployeeShiftSchedule, ShiftTemplate)
                .join(WarehouseStaff, WarehouseStaff.employee_id == EmployeeShiftSchedule.employee_id)
                .outerjoin(ShiftTemplate, ShiftTemplate.id == EmployeeShiftSchedule.shift_template_id)
                .where(
                    EmployeeShiftSchedule.warehouse_id == item.warehouse_id,
                    EmployeeShiftSchedule.work_date == item.work_date,
                    EmployeeShiftSchedule.status == "scheduled",
                    WarehouseStaff.counts_in_capacity.is_(True),
                )
            )
        ).all()
        used_staff: set[int] = set()
        capacity = Decimal(0)
        for shift, template in roster:
            if shift.employee_id in used_staff:
                continue
            presence = await session.scalar(
                select(Attendance.status).where(
                    Attendance.employee_id == shift.employee_id, Attendance.work_date == item.work_date
                )
            )
            if presence != "present" and not (presence == "planned" and item.work_date > local_today):
                continue
            if template is not None:
                useful = template.useful_hours_per_staff
            elif shift.start_time is not None and shift.end_time is not None:
                start = datetime.combine(item.work_date, shift.start_time)
                end = datetime.combine(item.work_date, shift.end_time)
                if end <= start:
                    end += timedelta(days=1)
                useful = Decimal(str((end - start).total_seconds() / 3600))
                if shift.break_start is not None and shift.break_end is not None:
                    b_start = datetime.combine(item.work_date, shift.break_start)
                    b_end = datetime.combine(item.work_date, shift.break_end)
                    if b_end <= b_start:
                        b_end += timedelta(days=1)
                    useful -= Decimal(str((b_end - b_start).total_seconds() / 3600))
            else:
                continue
            used_staff.add(shift.employee_id)
            capacity += max(Decimal(0), useful) * Decimal(str(cfg.delivery_share))
        if not used_staff:
            raise _fail("RESOURCE_CONFLICT", "No official warehouse capacity.", conflict="labour")
        capacity = max(Decimal(0), capacity - Decimal(str(cfg.final_inspection_hours)))
        booked = await session.scalar(
            select(func.coalesce(func.sum(PrepReservation.hours), 0)).where(
                PrepReservation.warehouse_id == item.warehouse_id,
                PrepReservation.work_date == item.work_date,
                PrepReservation.order_id != order_id,
                PrepReservation.status == "committed",
            )
        )
        if sales:
            held = await session.scalar(
                select(func.coalesce(func.sum(PrepReservation.hours), 0))
                .join(PlanningRun, PrepReservation.run_id == PlanningRun.id)
                .where(
                    PrepReservation.warehouse_id == item.warehouse_id,
                    PrepReservation.work_date == item.work_date,
                    PrepReservation.order_id != order_id,
                    PrepReservation.status == "held",
                    PlanningRun.hold_expires_at > clock.now(),
                )
            )
            booked = Decimal(booked or 0) + Decimal(held or 0)
        if item.hours <= 0 or capacity - Decimal(booked or 0) < item.hours:
            raise _fail("RESOURCE_CONFLICT", "Insufficient official warehouse capacity.", conflict="labour")


def _stored_gates(plan: FulfilmentPlan) -> bool:
    checks = plan.checks
    if not isinstance(checks, dict):
        return False
    return all(
        isinstance(checks.get(name), dict) and checks[name].get("passed") is True for name in _GATE_NAMES
    )


def _proof_valid(proof: RecheckProof, plan: FulfilmentPlan, order: CustomerOrder) -> bool:
    return (
        proof.plan_id == plan.id
        and proof.order_version == order.version
        and proof.source_version == order.source_version
        and proof.checked_at.tzinfo is not None
        and proof.checked_at <= clock.now()
        and proof.gates.keys() == _GATE_NAMES
        and all(proof.gates.values())
    )


async def _approve(
    session: AsyncSession,
    plan_id: int,
    actor: object,
    payload: dict[str, object],
    key: str,
    recheck: Recheck | None,
) -> dict[str, object]:
    uid = _actor_id(actor)
    identity, replay = await _claim(session, key, uid, plan_id, payload)
    if replay is not None:
        # A previously successful request must not disclose data after role or
        # store access has been revoked.
        order, _, _, market = await _order_and_plan(session, plan_id)
        roles = _roles(actor)
        if not roles.intersection({"dispatcher", "sales"}):
            raise _fail("FORBIDDEN", "Approval permission revoked.")
        if getattr(actor, "market", None) != market.code:
            raise _fail("NOT_FOUND", "Plan not found.")
        if "dispatcher" not in roles and order.origin_store_id not in getattr(actor, "location_ids", ()):
            raise _fail("NOT_FOUND", "Plan not found.")
        return replay

    order, plan, run, market = await _order_and_plan(session, plan_id)
    roles = _roles(actor)
    if not roles.intersection({"dispatcher", "sales"}):
        raise _fail("FORBIDDEN", "Only Dispatcher or eligible Sales can approve.")
    if getattr(actor, "market", None) != market.code:
        raise _fail("NOT_FOUND", "Plan not found.")
    sales = "dispatcher" not in roles
    if sales and (
        order.origin_store_id is None or order.origin_store_id not in getattr(actor, "location_ids", ())
    ):
        raise _fail("NOT_FOUND", "Plan not found.")
    if (
        order.status != "PLANNED"
        or plan.status != "proposed"
        or run.kind == "replan_suggestion"
        or run.result != "feasible"
    ):
        raise _fail("PLAN_NOT_APPROVABLE", "This plan cannot be approved from the current order state.")
    if order.version != run.order_version or plan.order_id != order.id:
        raise _fail("PLAN_NOT_APPROVABLE", "Order data changed; re-run planning.")
    latest = await session.scalar(
        select(PlanningRun.id)
        .where(PlanningRun.order_id == order.id)
        .order_by(PlanningRun.run_no.desc(), PlanningRun.id.desc())
        .limit(1)
    )
    if latest != run.id:
        raise _fail("PLAN_NOT_APPROVABLE", "Only the latest planning run may be approved.")
    if run.hold_expires_at is None or run.hold_expires_at <= clock.now():
        raise _fail("HOLD_EXPIRED", "Planning hold expired. Plan Again.", run_id=run.id)
    route = await session.scalar(
        select(OrderRouting.route).where(
            OrderRouting.market_id == order.market_id,
            OrderRouting.external_ref == order.external_ref,
        )
    )
    if route != "cfo":
        raise _fail("PLAN_NOT_APPROVABLE", "Order is not routed through CFO.")
    code, reason_text = _reason(payload)
    if plan.rank > 1 and not ((code and code.strip()) or (reason_text and reason_text.strip())):
        raise _fail("REASON_REQUIRED", "Alternative plan approval requires a reason.")
    cfg = MarketConfig.model_validate(market.config)
    selected = (
        await session.scalars(
            select(PlanVehicle).where(PlanVehicle.plan_id == plan.id).order_by(PlanVehicle.seq)
        )
    ).all()
    if not selected or len(selected) != plan.vehicle_count:
        raise _fail("PLAN_NOT_APPROVABLE", "Plan vehicles are incomplete.")
    if payload.get("drivers"):
        # Changing a driver invalidates the original plan/hold and requires
        # engine + vehicle-reservation recreation; do not silently ignore it.
        raise _fail("PLAN_NOT_APPROVABLE", "Re-run planning to change a driver safely.")
    if sales and (
        plan.rank != 1
        or plan.vehicle_count != 1
        or run.kind != "initial"
        or run.reserve_class != "safe"
        or plan.manual_reason_code is not None
        or plan.target_date != order.date_to
    ):
        raise _fail("PLAN_NOT_APPROVABLE", "Sales can only confirm an unchanged safe rank-1 plan.")
    if plan.target_date != order.date_to:
        neg_id = payload.get("date_negotiation_id")
        if not isinstance(neg_id, int):
            raise _fail("DATE_AGREEMENT_REQUIRED", "Customer agreement required for this date.")
        agreement = await session.get(DateNegotiation, neg_id)
        if (
            agreement is None
            or agreement.order_id != order.id
            or agreement.proposed_date != plan.target_date
            or agreement.outcome != "agreed"
        ):
            raise _fail("DATE_AGREEMENT_REQUIRED", "The agreed date does not match the selected plan.")
    if not _stored_gates(plan):
        raise _fail("PLAN_NOT_APPROVABLE", "Stored planning gates are incomplete.")
    if recheck is None:
        raise _fail("PLAN_NOT_APPROVABLE", "Fresh five-gate approval recheck is not connected.")
    stock = (
        await session.scalars(
            select(StockReservation)
            .where(
                StockReservation.run_id == run.id,
                StockReservation.warehouse_id == plan.warehouse_id,
                StockReservation.status == "held",
            )
            .order_by(StockReservation.global_product_id)
        )
    ).all()
    prep = (
        await session.scalars(
            select(PrepReservation)
            .where(
                PrepReservation.run_id == run.id,
                PrepReservation.warehouse_id == plan.warehouse_id,
                PrepReservation.status == "held",
            )
            .order_by(PrepReservation.work_date)
        )
    ).all()
    veh_res = (
        await session.scalars(
            select(VehicleReservation).where(
                VehicleReservation.plan_id == plan.id, VehicleReservation.status == "held"
            )
        )
    ).all()
    if not stock or not prep or len(veh_res) != len(selected):
        raise _fail("PLAN_NOT_APPROVABLE", "Live reservations are incomplete.")
    for assignment in selected:
        if not any(
            r.plan_vehicle_id == assignment.id
            and r.vehicle_id == assignment.vehicle_id
            and r.driver_employee_id == assignment.driver_employee_id
            for r in veh_res
        ):
            raise _fail("PLAN_NOT_APPROVABLE", "Vehicle hold does not match the selected plan.")
    await _reserve_locks(session, plan.warehouse_id, stock, prep, selected)
    # Re-evaluate the expiry AFTER waiting on advisory/row locks.
    if run.hold_expires_at <= clock.now():
        raise _fail("HOLD_EXPIRED", "Planning hold expired. Plan Again.", run_id=run.id)
    await _stock_available(session, stock, order.id, clock.now(), cfg, sales=sales)
    await _labour_available(session, prep, order.id, market, cfg, sales=sales)
    proof = await recheck(session, plan.id)
    if not _proof_valid(proof, plan, order):
        raise _fail("RESOURCE_CONFLICT", "Fresh engine/source gate validation failed.", conflict="five_gates")

    # DEC-WMS-RESERVE-SYNC: a local hold and five passing gates are NOT a WMS
    # reserve ACK. Production/staging and the real disposable demo must never
    # commit APPROVED before a durable reservation intent, exact WMS ACK,
    # post-ACK stock refresh and recovery ledger are integrated and verified.
    # Existing isolated unit/PG tests remain backward-compatible solely as
    # pre-WMS internal transaction tests, NOT as evidence of final approval.
    require_simulated_or_off()  # 409 PLAN_NOT_APPROVABLE nếu mode không hợp lệ hoặc mô phỏng bị cấm
    if get_settings().app_env != "test" or os.environ.get("DEMO_DISPOSABLE") == "1":
        # Persisted synthetic ACK by itself is NOT sufficient. Inspect the
        # current ledger under the order lock, then fail closed until an
        # authenticated native-SKU→CFO stock-batch linkage is verified.
        if get_settings().app_env == "test" and os.environ.get("DEMO_DISPOSABLE") == "1":
            from app.services.wms_finalization_gate import inspect_wms_gate

            wms_state = await inspect_wms_gate(session, order, plan)
            raise _fail("PLAN_NOT_APPROVABLE", wms_state.reason)
        raise _fail(
            "PLAN_NOT_APPROVABLE",
            "WMS reservation acknowledgment and durable recovery are not configured.",
        )

    plan.status = "approved"
    await session.flush()
    await reservation_service.commit_plan(plan.id, resources_validated=True, session=session)
    await session.execute(
        update(FulfilmentPlan)
        .where(
            FulfilmentPlan.run_id == run.id,
            FulfilmentPlan.id != plan.id,
            FulfilmentPlan.status == "proposed",
        )
        .values(status="superseded")
    )
    promise_start = max(v.eta_at for v in selected)
    promise_end = promise_start + timedelta(hours=cfg.promise_window_hours)
    order.approved_plan_id = plan.id
    order.committed_date = plan.target_date
    order.promise_start = promise_start
    order.promise_end = promise_end
    order.approved_at = clock.now()
    await transition(
        session,
        order.id,
        OrderStatus.APPROVED,
        "sales" if sales else "dispatcher",
        sales_approved_plan_id=plan.id if sales else None,
    )
    trips: list[int] = []
    for vehicle in selected:
        trip = DeliveryTrip(
            plan_vehicle_id=vehicle.id,
            warehouse_id=plan.warehouse_id,
            vehicle_id=vehicle.vehicle_id,
            driver_employee_id=vehicle.driver_employee_id,
            depart_planned_at=vehicle.depart_at,
        )
        session.add(trip)
        await session.flush()
        session.add(TripStop(trip_id=trip.id, order_id=order.id, seq=1, eta_planned_at=vehicle.eta_at))
        trips.append(trip.id)
    session.add(
        EtaForecast(
            order_id=order.id,
            version=1,
            trigger="approval",
            planned_eta=promise_start,
            forecast_eta=promise_start,
            commitment_deadline=promise_end,
            reserve_total_min=max(0, plan.planning_reserve_min),
            slack_min=max(0, plan.planning_reserve_min),
            consumption_pct=Decimal(0),
            risk_status="ON_TRACK",
            risk_color="green",
        )
    )
    if plan.rank > 1:
        await record_decision(
            session,
            Action.ALT_SELECTED,
            "fulfilment_plan",
            str(plan.id),
            order_id=order.id,
            plan_id=plan.id,
            reason_code=code,
            reason_text=reason_text,
            actor_user_id=uid,
            actor_employee_id=getattr(actor, "employee_id", None),
            actor_role="sales" if sales else "dispatcher",
        )
    await record_decision(
        session,
        Action.PLAN_APPROVED,
        "fulfilment_plan",
        str(plan.id),
        order_id=order.id,
        plan_id=plan.id,
        actor_user_id=uid,
        actor_employee_id=getattr(actor, "employee_id", None),
        actor_role="sales" if sales else "dispatcher",
        snapshot={"run_id": run.id, "order_version": order.version, "source_version": order.source_version},
        after={"status": "approved", "trip_ids": trips, "committed_date": plan.target_date.isoformat()},
    )
    # T21 (historical T23 handoff): stage exactly one CONFIRMED in this
    # approval transaction after the order has its committed plan and window.
    # The E2 worker owns delivery after commit; never connect to SMTP here.
    notification_id = await notify_service.enqueue(order.id, "CONFIRMED", plan.id, session=session)
    notification = await session.get(Notification, notification_id)
    if (
        notification is None
        or notification.order_id != order.id
        or notification.plan_id != plan.id
        or notification.template != "CONFIRMED"
    ):
        raise _fail("PLAN_NOT_APPROVABLE", "Approved CONFIRMED notification is missing or inconsistent.")
    response: dict[str, object] = {
        "order": {
            "id": order.id,
            "status": "APPROVED",
            "committed": {
                "date": plan.target_date.isoformat(),
                "promise_start": promise_start.isoformat(),
                "promise_end": promise_end.isoformat(),
            },
        },
        "plan": {"id": plan.id, "status": "approved", "rank": plan.rank},
        "trip_ids": trips,
        "notifications": [
            {"id": notification.id, "template": notification.template, "status": notification.status}
        ],
    }
    identity.response_status = 200
    identity.response_body = response
    await session.flush()
    return response


async def _reserve_before_approval(plan_id: int, actor: object) -> None:
    """Giữ hàng WMS mô phỏng trước transaction duyệt; kiểm tra quyền như _approve."""
    from app.services.wms_reserve_phase import reserve_simulated

    async with get_sessionmaker()() as db:
        order, plan, _, market = await _order_and_plan(db, plan_id)
    roles = _roles(actor)
    if not roles.intersection({"dispatcher"}):
        raise _fail("FORBIDDEN", "Approval permission denied.")
    if getattr(actor, "market", None) != market.code:
        raise _fail("NOT_FOUND", "Plan not found.")
    await reserve_simulated(order.id, plan.id)


async def approve(
    plan_id: int,
    actor: object,
    payload: dict[str, object],
    idempotency_key: str,
    *,
    session: AsyncSession | None = None,
    recheck: Recheck | None = None,
) -> dict[str, object]:
    """Approve in ONE transaction, or join the caller transaction.

    The trusted recheck callback must reconstruct the plan with current DB/source
    input and verify five engine gates. Never supply it from JSON/request data.
    """
    if session is not None:
        return await _approve(session, plan_id, actor, payload, idempotency_key, recheck)
    if require_simulated_or_off():
        await _reserve_before_approval(plan_id, actor)
    async with get_sessionmaker()() as db, db.begin():
        return await _approve(db, plan_id, actor, payload, idempotency_key, recheck)


async def manual_plan(
    order_id: int, actor: object, payload: dict[str, object], idempotency_key: str
) -> dict[str, object]:
    """No unsafe bypass: manual plans need the T14 fresh engine adapter."""
    raise _fail("PLAN_NOT_APPROVABLE", "Manual plan creation needs a verified five-gate engine adapter.")


_PRE_DISPATCH = ("APPROVED", "PREPARING", "GOODS_READY", "LOADED")


async def keep_current(
    run_id: int, actor: object, reason_text: str, *, session: AsyncSession | None = None
) -> None:
    """Dispatcher keeps the CURRENT approved plan against a replan suggestion (06 §6.6, DEC-HOLD-001).

    Mandatory reason; audit `REPLAN_KEPT`; the suggestion's alert is closed. Nothing else changes: the
    approved plan, its reservations, trips and the order state are untouched; never approved.
    Only the order's latest suggestion can be decided, once (decided suggestions are final: `409`).
    """
    if "dispatcher" not in _roles(actor):
        raise _fail("FORBIDDEN", "Only Dispatcher may keep the current plan.")
    reason = reason_text.strip() if isinstance(reason_text, str) else ""
    if not reason:
        raise _fail("REASON_REQUIRED", "Keep-current requires an auditable reason.")
    if session is None:
        async with get_sessionmaker()() as db, db.begin():
            return await keep_current(run_id, actor, reason, session=db)
    run = await session.get(PlanningRun, run_id)
    # Lock order first, then run: the same order as plan approval (no lock inversion/deadlock).
    order = (
        await session.scalar(select(CustomerOrder).where(CustomerOrder.id == run.order_id).with_for_update())
        if run is not None
        else None
    )
    market = await session.get(Market, order.market_id) if order is not None else None
    if (
        run is None
        or order is None
        or market is None
        or getattr(actor, "market", None) != market.code.strip()
    ):
        raise _fail("NOT_FOUND", "Planning run not found.")
    if run.kind != "replan_suggestion":
        raise _fail("ILLEGAL_TRANSITION", "Only a replan suggestion can be kept or declined.")
    await session.scalar(select(PlanningRun.id).where(PlanningRun.id == run.id).with_for_update())
    if order.approved_plan_id is None or order.status not in _PRE_DISPATCH:
        raise _fail("ILLEGAL_TRANSITION", "The order has no active pre-dispatch plan to keep.")
    latest = await session.scalar(
        select(func.max(PlanningRun.run_no)).where(
            PlanningRun.order_id == order.id, PlanningRun.kind == "replan_suggestion"
        )
    )
    if latest != run.run_no:
        raise _fail("ILLEGAL_TRANSITION", "A newer replan suggestion exists; this one is stale.")
    already = await session.scalar(
        select(DecisionLog.id).where(
            DecisionLog.action == Action.REPLAN_KEPT.value,
            DecisionLog.entity == "planning_run",
            DecisionLog.entity_id == str(run.id),
        )
    )
    if already is not None:
        raise _fail("ILLEGAL_TRANSITION", "This suggestion was already decided.")
    await alert_service.resolve(session, f"replan:{order.id}:{run.id}", now=clock.now())
    await record_decision(
        session,
        Action.REPLAN_KEPT,
        "planning_run",
        str(run.id),
        order_id=order.id,
        plan_id=order.approved_plan_id,
        reason_text=reason,
        snapshot={"trigger": run.params.get("trigger"), "kept_plan_id": order.approved_plan_id},
        actor_user_id=_actor_id(actor),
        actor_employee_id=getattr(actor, "employee_id", None),
        actor_role="dispatcher",
    )


async def record_date_negotiation(order_id: int, actor: object, payload: dict[str, object]) -> int:
    """Implement independent date-negotiation record; no implicit date change."""
    if "dispatcher" not in _roles(actor):
        raise _fail("FORBIDDEN", "Only Dispatcher may record a date negotiation.")
    if not isinstance(getattr(actor, "employee_id", None), int):
        raise _fail("FORBIDDEN", "An employee assignment is required.")
    raw_date = payload.get("proposed_date")
    raw_contact = payload.get("contacted_at")
    outcome = payload.get("outcome")
    channel = payload.get("channel")
    if outcome not in ("agreed", "declined", "unreachable") or channel not in ("phone", "email", "in_person"):
        raise _fail("VALIDATION_ERROR", "Invalid outcome or contact channel.")
    try:
        proposed = date.fromisoformat(raw_date) if isinstance(raw_date, str) else None
        contacted = datetime.fromisoformat(raw_contact) if isinstance(raw_contact, str) else None
    except ValueError as exc:
        raise _fail("VALIDATION_ERROR", "Invalid date or timestamp.") from exc
    if proposed is None or contacted is None or contacted.tzinfo is None or contacted > clock.now():
        raise _fail("VALIDATION_ERROR", "Contact must have a valid timestamp and proposed date.")
    async with get_sessionmaker()() as db, db.begin():
        order = await db.get(CustomerOrder, order_id)
        market = await db.get(Market, order.market_id) if order is not None else None
        if order is None or market is None or getattr(actor, "market", None) != market.code:
            raise _fail("NOT_FOUND", "Order not found.")
        note = payload.get("note")
        if note is not None and not isinstance(note, str):
            raise _fail("VALIDATION_ERROR", "Invalid note.")
        row = DateNegotiation(
            order_id=order_id,
            proposed_date=proposed,
            contacted_at=contacted,
            outcome=outcome,
            channel=channel,
            recorded_by=actor.employee_id,
            note=note,
            remind_at=contacted + timedelta(hours=24) if outcome == "unreachable" else None,
        )
        db.add(row)
        await db.flush()
        await record_decision(
            db,
            Action.DATE_NEGOTIATION_RECORDED,
            "date_negotiation",
            str(row.id),
            order_id=order_id,
            actor_user_id=_actor_id(actor),
            actor_employee_id=actor.employee_id,
            actor_role="dispatcher",
            after={"outcome": outcome, "proposed_date": proposed.isoformat()},
        )
        return row.id
