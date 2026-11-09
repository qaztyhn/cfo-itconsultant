"""CS contact log persistence; scoped, append-only and audit-safe (docs/06 §11).

This service never sends a notification or exposes contact phone/email, GPS,
internal planning, or other orders outside the actor's market. The caller owns
the transaction; errors roll back the log and the audit together.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core.errors import DomainError
from app.domain.models.hr import Employee
from app.domain.models.ops import CustomerContactLog, CustomerOrder
from app.services import order_read_service


CHANNELS = frozenset({"phone", "email", "chat"})
REASONS = frozenset({"where_is_my_order", "change_request", "complaint", "delay_inquiry", "other"})


def _roles(actor: object) -> tuple[str, ...]:
    return tuple(getattr(actor, "roles", ()) or ())


async def _scoped_order(session: AsyncSession, actor: object, order_id: int, *, write: bool) -> CustomerOrder:
    roles = _roles(actor)
    if write:
        if "customer_service" not in roles:
            raise DomainError("FORBIDDEN", "Customer service role is required.")
    elif "customer_service" not in roles and "dispatcher" not in roles:
        raise DomainError("FORBIDDEN", "Contact history is not available to this role.")
    # Do not substitute admin privilege, broad OrderOut or arbitrary user-supplied
    # market identifiers for the explicit CS/Dispatcher contact log roles.
    scope = await order_read_service.resolve_order_scope(session, actor)
    if scope.market_id is None:
        raise DomainError("FORBIDDEN", "Market-scoped contact access is required.")
    order = await session.scalar(
        select(CustomerOrder).where(
            CustomerOrder.id == order_id,
            CustomerOrder.market_id == scope.market_id,
        )
    )
    if order is None:
        raise DomainError("NOT_FOUND", "Order not found.")
    return order


def _view(log: CustomerContactLog, *, can_read_note: bool) -> dict[str, object]:
    """Server-selected response allowlist: Dispatcher never receives a note or employee id."""
    item: dict[str, object] = {
        "id": log.id,
        "order_id": log.order_id,
        "channel": log.channel,
        "reason_code": log.reason_code,
        "contacted_at": log.contacted_at,
    }
    if can_read_note:
        item["note"] = log.note
        item["employee_id"] = log.employee_id
    return item


async def create(
    session: AsyncSession,
    actor: object,
    order_id: int,
    *,
    channel: str,
    reason_code: str,
    note: str | None,
) -> dict[str, object]:
    order = await _scoped_order(session, actor, order_id, write=True)
    employee_id = getattr(actor, "employee_id", None)
    actor_id = getattr(actor, "id", None)
    if type(employee_id) is not int or type(actor_id) is not int:
        raise DomainError("FORBIDDEN", "Verified CS employee and account required.")
    employee = await session.get(Employee, employee_id)
    if employee is None or employee.status != "active" or employee.market_id != order.market_id:
        raise DomainError("FORBIDDEN", "Active in-market CS employee required.")
    if channel not in CHANNELS or reason_code not in REASONS:
        raise DomainError("VALIDATION_ERROR", "Invalid contact channel or reason code.")
    if note is not None and (not isinstance(note, str) or len(note) > 1000):
        raise DomainError("VALIDATION_ERROR", "Invalid contact note.")
    log = CustomerContactLog(
        order_id=order.id,
        customer_id=order.customer_id,
        employee_id=employee_id,
        channel=channel,
        reason_code=reason_code,
        note=note,
    )
    session.add(log)
    await session.flush()
    await session.refresh(log, attribute_names=["contacted_at"])
    await record_decision(
        session,
        Action.CUSTOMER_CONTACT_RECORDED,
        entity="customer_contact_log",
        entity_id=str(log.id),
        order_id=order.id,
        actor_user_id=actor_id,
        actor_employee_id=employee_id,
        actor_role="customer_service",
        snapshot={"channel": channel, "reason_code": reason_code},
    )
    return _view(log, can_read_note=True)


async def list_logs(
    session: AsyncSession,
    actor: object,
    order_id: int,
    *,
    page: int,
    page_size: int,
) -> dict[str, object]:
    await _scoped_order(session, actor, order_id, write=False)
    condition = CustomerContactLog.order_id == order_id
    total = await session.scalar(select(func.count()).select_from(CustomerContactLog).where(condition))
    logs = (
        await session.scalars(
            select(CustomerContactLog)
            .where(condition)
            .order_by(CustomerContactLog.contacted_at.desc(), CustomerContactLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    can_read_note = "customer_service" in _roles(actor)
    return {
        "items": [_view(log, can_read_note=can_read_note) for log in logs],
        "page": page,
        "page_size": page_size,
        "total": int(total or 0),
    }
