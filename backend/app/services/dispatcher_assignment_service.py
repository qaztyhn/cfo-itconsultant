"""R3 T15: market-serialized Dispatcher rotation and single-trip handover.

Rotation turns are recorded by immutable approval/handover audit rows. Pre-T15
trip assignments without that evidence are considered as a legacy baseline.
All methods join the caller's transaction; no independent commits.
"""

from sqlalchemy import BigInteger, Select, func, select, text
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


def _eligible_dispatchers(market_id: int) -> Select[Employee]:
    return (
        select(Employee)
        .join(DispatcherStaff, DispatcherStaff.employee_id == Employee.id)
        .join(AppUser, AppUser.employee_id == Employee.id)
        .where(
            Employee.market_id == market_id,
            Employee.status == "active",
            DispatcherStaff.in_rotation.is_(True),
            AppUser.is_active.is_(True),
            AppUser.roles.contains(["dispatcher"]),
        )
    )


async def choose_dispatcher(session: AsyncSession, market_id: int) -> int | None:
    """Call once per approved order, after acquiring lock_market_rotation.

    Decision log IDs order committed turns under the market lock and survive
    handovers of an individual trip. A rollback writes neither an audit row
    nor a trip, and an idempotent replay never calls this function.
    """
    eligible = (
        await session.scalars(
            _eligible_dispatchers(market_id)
            .with_only_columns(Employee.id)
            .order_by(Employee.id)
            .with_for_update(read=True, of=(Employee, DispatcherStaff, AppUser))
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
    # FOR SHARE on candidate rows intentionally coexists with the FK KEY SHARE
    # taken by an in-flight approval idempotency insert on ref.app_user.
    # FOR UPDATE would deadlock while the other approval waits for market lock.
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


def _dispatcher_identity(actor: object) -> tuple[int, int]:
    if "dispatcher" not in getattr(actor, "roles", ()):
        raise DomainError("FORBIDDEN", "Dispatcher role required.")
    actor_user_id = getattr(actor, "id", None)
    actor_employee_id = getattr(actor, "employee_id", None)
    if not isinstance(actor_user_id, int) or not isinstance(actor_employee_id, int):
        raise DomainError("FORBIDDEN", "Active Dispatcher account required.")
    return actor_user_id, actor_employee_id


async def _trip_market(session: AsyncSession, trip_id: int, actor: object) -> Market:
    market = await session.scalar(
        select(Market)
        .join(Location, Location.market_id == Market.id)
        .join(DeliveryTrip, DeliveryTrip.warehouse_id == Location.id)
        .where(DeliveryTrip.id == trip_id)
    )
    if market is None or market.code.strip() != str(getattr(actor, "market", "")).strip():
        raise DomainError("NOT_FOUND", "Trip not found.")
    return market


async def _trip_order(session: AsyncSession, trip_id: int, market_id: int) -> CustomerOrder:
    order_id = await session.scalar(select(TripStop.order_id).where(TripStop.trip_id == trip_id).limit(1))
    order = await session.get(CustomerOrder, order_id) if order_id is not None else None
    if order is None or order.market_id != market_id:
        raise DomainError("NOT_FOUND", "Trip order not found.")
    return order


async def eligible_receivers(session: AsyncSession, trip_id: int, actor: object) -> list[tuple[int, str]]:
    _dispatcher_identity(actor)
    market = await _trip_market(session, trip_id, actor)
    trip = await session.get(DeliveryTrip, trip_id)
    if trip is None:
        raise DomainError("NOT_FOUND", "Trip not found.")
    await _trip_order(session, trip.id, market.id)
    recipients = (
        await session.execute(
            _eligible_dispatchers(market.id)
            .with_only_columns(Employee.id, Employee.first_name, Employee.last_name)
            .where(Employee.id.is_distinct_from(trip.assigned_dispatcher_employee_id))
            .distinct()
            .order_by(Employee.id)
        )
    ).all()
    return [
        (employee_id, f"{first_name} {last_name}".strip())
        for employee_id, first_name, last_name in recipients
    ]


async def handover(
    trip_id: int,
    actor: object,
    to_employee_id: int,
    reason_text: str,
    *,
    session: AsyncSession | None = None,
) -> dict[str, int | str | None]:
    """Authorized Dispatcher in the trip's market may reassign exactly one trip."""
    actor_user_id, actor_employee_id = _dispatcher_identity(actor)
    if not isinstance(to_employee_id, int) or to_employee_id <= 0:
        raise DomainError("VALIDATION_ERROR", "Invalid receiving Dispatcher.")
    reason = reason_text.strip() if isinstance(reason_text, str) else ""
    if not reason:
        raise DomainError("REASON_REQUIRED", "A handover reason is required.")
    if session is None:
        async with get_sessionmaker()() as db, db.begin():
            return await handover(trip_id, actor, to_employee_id, reason, session=db)

    market = await _trip_market(session, trip_id, actor)
    await lock_market_rotation(session, market.id)
    trip = await session.scalar(select(DeliveryTrip).where(DeliveryTrip.id == trip_id).with_for_update())
    if trip is None:
        raise DomainError("NOT_FOUND", "Trip not found.")
    recipient = await session.scalar(
        _eligible_dispatchers(market.id)
        .with_only_columns(Employee.id)
        .where(Employee.id == to_employee_id)
        .with_for_update(read=True, of=(Employee, DispatcherStaff, AppUser))
    )
    if recipient is None:
        raise DomainError("VALIDATION_ERROR", "Receiving Dispatcher is not eligible.")
    before_id = trip.assigned_dispatcher_employee_id
    if before_id == to_employee_id:
        raise DomainError("ILLEGAL_TRANSITION", "Trip is already assigned to this Dispatcher.")
    order = await _trip_order(session, trip.id, market.id)
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
