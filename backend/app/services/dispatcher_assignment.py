"""T15: market-serialized Dispatcher rotation and audited per-trip handover.

All functions join the caller's PostgreSQL transaction. No commits here.
"""
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core.errors import DomainError
from app.domain.models.hr import DispatcherStaff, Employee
from app.domain.models.ops import DeliveryTrip, TripStop
from app.domain.models.ref import Location, Market


async def choose_dispatcher(session: AsyncSession, market_id: int) -> int | None:
    """One selection per APPROVED order, serialized with other approvals in the market.

    NULL last-assignment sorts first. A timestamp tie is broken by employee ID.
    Both the selection and insertion of ALL trips must happen under this lock.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:resource, 0))"),
        {"resource": f"dispatcher-rotation:{market_id}"},
    )
    latest = (
        select(
            DeliveryTrip.assigned_dispatcher_employee_id.label("employee_id"),
            func.max(DeliveryTrip.created_at).label("last_assigned"),
        )
        .join(Location, Location.id == DeliveryTrip.warehouse_id)
        .where(Location.market_id == market_id)
        .group_by(DeliveryTrip.assigned_dispatcher_employee_id)
        .subquery()
    )
    return await session.scalar(
        select(DispatcherStaff.employee_id)
        .join(Employee, Employee.id == DispatcherStaff.employee_id)
        .outerjoin(latest, latest.c.employee_id == DispatcherStaff.employee_id)
        .where(
            Employee.market_id == market_id,
            Employee.status == "active",
            DispatcherStaff.in_rotation.is_(True),
        )
        .order_by(latest.c.last_assigned.asc().nullsfirst(), DispatcherStaff.employee_id.asc())
        .limit(1)
    )


async def handover_trip(
    session: AsyncSession,
    trip_id: int,
    actor: object,
    *,
    to_employee_id: int,
    reason_text: str,
) -> dict[str, object]:
    """Change only one trip; row lock prevents competing handovers."""
    if "dispatcher" not in getattr(actor, "roles", ()):
        raise DomainError("FORBIDDEN", "Dispatcher role required.")
    user_id = getattr(actor, "id", None)
    actor_employee_id = getattr(actor, "employee_id", None)
    if not isinstance(user_id, int) or not isinstance(actor_employee_id, int):
        raise DomainError("FORBIDDEN", "Active dispatcher identity required.")
    if not isinstance(reason_text, str) or not reason_text.strip():
        raise DomainError("REASON_REQUIRED", "Handover reason is required.")
    if not isinstance(to_employee_id, int) or isinstance(to_employee_id, bool) or to_employee_id <= 0:
        raise DomainError("VALIDATION_ERROR", "Invalid receiving employee.")

    row = (
        await session.execute(
            select(DeliveryTrip, Market)
            .join(Location, Location.id == DeliveryTrip.warehouse_id)
            .join(Market, Market.id == Location.market_id)
            .where(DeliveryTrip.id == trip_id)
            .with_for_update(of=DeliveryTrip)
        )
    ).one_or_none()
    if row is None or row[1].code.strip() != str(getattr(actor, "market", "")).strip():
        raise DomainError("NOT_FOUND", "Trip not found.")
    trip, market = row
    actor_ok = await session.scalar(
        select(Employee.id)
        .join(DispatcherStaff, DispatcherStaff.employee_id == Employee.id)
        .where(Employee.id == actor_employee_id, Employee.market_id == market.id,
               Employee.status == "active")
    )
    if actor_ok is None:
        raise DomainError("FORBIDDEN", "Active market Dispatcher required.")
    recipient = await session.scalar(
        select(Employee.id)
        .join(DispatcherStaff, DispatcherStaff.employee_id == Employee.id)
        .where(Employee.id == to_employee_id, Employee.market_id == market.id,
               Employee.status == "active", DispatcherStaff.in_rotation.is_(True))
    )
    if recipient is None:
        raise DomainError("VALIDATION_ERROR", "Receiving Dispatcher is not eligible.")
    previous = trip.assigned_dispatcher_employee_id
    if previous == to_employee_id:
        raise DomainError("VALIDATION_ERROR", "Trip is already assigned to this Dispatcher.")
    trip.assigned_dispatcher_employee_id = to_employee_id
    order_id = await session.scalar(select(TripStop.order_id).where(TripStop.trip_id == trip.id).limit(1))
    await record_decision(
        session, Action.TRIP_DISPATCHER_HANDOVER, "delivery_trip", str(trip.id),
        order_id=order_id, reason_text=reason_text.strip(),
        before={"assigned_dispatcher_employee_id": previous},
        after={"assigned_dispatcher_employee_id": to_employee_id},
        actor_user_id=user_id, actor_employee_id=actor_employee_id, actor_role="dispatcher",
    )
    await session.flush()
    return {"trip_id": trip.id, "assigned_dispatcher_employee_id": to_employee_id}
