"""R3 T15: market-serialized Dispatcher rotation and single-trip handover.

Rotation turns are recorded by immutable approval/handover audit rows. Pre-T15
trip assignments without that evidence are considered as a legacy baseline.
All methods join the caller's transaction; no independent commits.
"""

from sqlalchemy import BigInteger, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core.db import get_sessionmaker
from app.core.errors import DomainError
from app.domain.models.audit import DecisionLog
from app.domain.models.hr import DispatcherStaff, Employee
from app.domain.models.ops import CustomerOrder, DeliveryTrip, TripStop
from app.domain.models.ref import AppUser, Location, Market


async def lock_market_rotation(session: AsyncSession, market_id: int) -> None:
    """One xact advisory lock serializes every approval/handover in a market."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"dispatcher_rotation:{market_id}"},
    )


async def choose_dispatcher(session: AsyncSession, market_id: int) -> int | None:
    """Call once per approved order, after acquiring lock_market_rotation.

    Decision log IDs order committed turns under the market lock and survive
    handovers of an individual trip. A rollback writes neither an audit row
    nor a trip, and an idempotent replay never calls this function.
    """
    eligible = (
        await session.scalars(
            select(Employee.id)
            .join(DispatcherStaff, DispatcherStaff.employee_id == Employee.id)
            .join(AppUser, AppUser.employee_id == Employee.id)
            .where(
                Employee.market_id == market_id,
                Employee.status == "active",
                DispatcherStaff.in_rotation.is_(True),
                AppUser.is_active.is_(True),
                AppUser.roles.any("dispatcher"),
            )
            .order_by(Employee.id)
            .with_for_update(of=(Employee, DispatcherStaff, AppUser))
        )
    ).all()
    if not eligible:
        return None

    assigned_id = DecisionLog.after["assigned_dispatcher_employee_id"].astext.cast(BigInteger)
    history = (
        await session.execute(
            select(assigned_id, func.max(DecisionLog.id))
            .join(CustomerOrder, CustomerOrder.id == DecisionLog.order_id)
            .where(
                CustomerOrder.market_id == market_id,
                DecisionLog.action.in_((Action.PLAN_APPROVED.value, Action.TRIP_DISPATCHER_HANDOVER.value)),
                assigned_id.in_(eligible),
            )
            .group_by(assigned_id)
        )
    ).all()
    last_audit = {employee_id: last for employee_id, last in history}
    # Old trips may have a valid assigned employee but no T15 audit evidence yet.
    # Only use these as fallback; newly written immutable turn evidence is primary.
    legacy = (
        await session.execute(
            select(
                DeliveryTrip.assigned_dispatcher_employee_id,
                func.max(DeliveryTrip.id),
            )
            .join(Location, Location.id == DeliveryTrip.warehouse_id)
            .where(
                Location.market_id == market_id,
                DeliveryTrip.assigned_dispatcher_employee_id.in_(eligible),
            )
            .group_by(DeliveryTrip.assigned_dispatcher_employee_id)
        )
    ).all()
    last_trip = {employee_id: last for employee_id, last in legacy}

    def priority(employee_id: int) -> tuple[int, int, int]:
        if employee_id in last_audit:
            return (2, last_audit[employee_id], employee_id)
        if employee_id in last_trip:
            return (1, last_trip[employee_id], employee_id)
        return (0, 0, employee_id)

    return min(eligible, key=priority)


async def handover(
    trip_id: int,
    actor: object,
    to_employee_id: int,
    reason_text: str,
    *,
    session: AsyncSession | None = None,
) -> dict[str, int | str | None]:
    """Authorized Dispatcher in the trip's market may reassign exactly one trip."""
    if "dispatcher" not in getattr(actor, "roles", ()):
        raise DomainError("FORBIDDEN", "Dispatcher role required.")
    actor_user_id = getattr(actor, "id", None)
    actor_employee_id = getattr(actor, "employee_id", None)
    if not isinstance(actor_user_id, int) or not isinstance(actor_employee_id, int):
        raise DomainError("FORBIDDEN", "Active Dispatcher account required.")
    if not isinstance(to_employee_id, int) or to_employee_id <= 0:
        raise DomainError("VALIDATION_ERROR", "Invalid receiving Dispatcher.")
    reason = reason_text.strip() if isinstance(reason_text, str) else ""
    if not reason:
        raise DomainError("REASON_REQUIRED", "A handover reason is required.")
    if session is None:
        async with get_sessionmaker()() as db, db.begin():
            return await handover(trip_id, actor, to_employee_id, reason, session=db)

    market = await session.scalar(
        select(Market)
        .join(Location, Location.market_id == Market.id)
        .join(DeliveryTrip, DeliveryTrip.warehouse_id == Location.id)
        .where(DeliveryTrip.id == trip_id)
    )
    if market is None or market.code.strip() != str(getattr(actor, "market", "")).strip():
        raise DomainError("NOT_FOUND", "Trip not found.")
    await lock_market_rotation(session, market.id)
    trip = await session.scalar(select(DeliveryTrip).where(DeliveryTrip.id == trip_id).with_for_update())
    if trip is None:
        raise DomainError("NOT_FOUND", "Trip not found.")
    recipient = await session.scalar(
        select(Employee.id)
        .join(DispatcherStaff, DispatcherStaff.employee_id == Employee.id)
        .join(AppUser, AppUser.employee_id == Employee.id)
        .where(
            Employee.id == to_employee_id,
            Employee.market_id == market.id,
            Employee.status == "active",
            DispatcherStaff.in_rotation.is_(True),
            AppUser.is_active.is_(True),
            AppUser.roles.any("dispatcher"),
        )
        .with_for_update(of=(Employee, DispatcherStaff, AppUser))
    )
    if recipient is None:
        raise DomainError("VALIDATION_ERROR", "Receiving Dispatcher is not eligible.")
    before_id = trip.assigned_dispatcher_employee_id
    if before_id == to_employee_id:
        raise DomainError("ILLEGAL_TRANSITION", "Trip is already assigned to this Dispatcher.")
    order_id = await session.scalar(select(TripStop.order_id).where(TripStop.trip_id == trip_id).limit(1))
    order = await session.get(CustomerOrder, order_id) if order_id is not None else None
    if order is None or order.market_id != market.id:
        raise DomainError("NOT_FOUND", "Trip order not found.")
    trip.assigned_dispatcher_employee_id = to_employee_id
    await session.flush()
    await record_decision(
        session,
        Action.TRIP_DISPATCHER_HANDOVER,
        "delivery_trip",
        str(trip.id),
        order_id=order.id,
        plan_id=order.approved_plan_id,
        reason_text=reason,
        before={"assigned_dispatcher_employee_id": before_id},
        after={"assigned_dispatcher_employee_id": to_employee_id},
        actor_user_id=actor_user_id,
        actor_employee_id=actor_employee_id,
        actor_role="dispatcher",
    )
    return {
        "trip_id": trip.id,
        "previous_dispatcher_employee_id": before_id,
        "assigned_dispatcher_employee_id": to_employee_id,
    }
