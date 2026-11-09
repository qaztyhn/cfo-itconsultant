"""CS contact-log persistence. Service-only slice of docs/06 §11.

The legacy orders router still owns its unimplemented REST stubs. Wire this
service in a separate review after in-flight CS DTO PR #189 merges, rather than
changing a contested router file. Never log or audit customer-facing free text.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.errors import DomainError
from app.domain.models.hr import Employee
from app.domain.models.ops import CustomerContactLog, CustomerOrder
from app.domain.models.ref import Market

CHANNELS = frozenset({"phone", "email", "chat"})
REASONS = frozenset({"where_is_my_order", "change_request", "complaint", "delay_inquiry", "other"})


def _roles(actor: object) -> frozenset[str]:
    return frozenset(getattr(actor, "roles", ()))


async def _order(
    session: AsyncSession, actor: object, order_id: int, *, write: bool
) -> tuple[CustomerOrder, Market]:
    roles = _roles(actor)
    if write:
        allowed = "customer_service" in roles
    else:
        allowed = bool(roles.intersection({"customer_service", "dispatcher"}))
    if not allowed:
        raise DomainError("FORBIDDEN", "Customer contact log permission required.")
    code = getattr(actor, "market", None)
    if not isinstance(code, str) or not code:
        raise DomainError("FORBIDDEN", "An assigned market is required.")
    row = (
        await session.execute(
            select(CustomerOrder, Market)
            .join(Market, Market.id == CustomerOrder.market_id)
            .where(CustomerOrder.id == order_id, Market.code == code)
        )
    ).one_or_none()
    if row is None:
        raise DomainError("NOT_FOUND", "Order not found.")
    return row


async def create(
    session: AsyncSession,
    actor: object,
    order_id: int,
    *,
    channel: str,
    reason_code: str,
    note: str | None = None,
) -> dict[str, object]:
    """Save a confirmed CS interaction and PII-free audit in the caller transaction."""
    order, market = await _order(session, actor, order_id, write=True)
    employee_id = getattr(actor, "employee_id", None)
    user_id = getattr(actor, "id", None)
    if type(employee_id) is not int or type(user_id) is not int:
        raise DomainError("FORBIDDEN", "Active CS employee is required.")
    employee = await session.get(Employee, employee_id)
    if employee is None or employee.market_id != market.id or employee.status != "active":
        raise DomainError("FORBIDDEN", "Active CS employee is required.")
    if channel not in CHANNELS or reason_code not in REASONS:
        raise DomainError("VALIDATION_ERROR", "Invalid contact channel or reason code.")
    if note is not None and (not isinstance(note, str) or len(note) > 2000):
        raise DomainError("VALIDATION_ERROR", "Invalid note length.")
    event = CustomerContactLog(
        order_id=order.id,
        customer_id=order.customer_id,
        employee_id=employee_id,
        channel=channel,
        reason_code=reason_code,
        note=note,
        contacted_at=clock.now(),
    )
    session.add(event)
    await session.flush()
    await record_decision(
        session,
        Action.CUSTOMER_CONTACT_RECORDED,
        "customer_contact_log",
        str(event.id),
        order_id=order.id,
        actor_user_id=user_id,
        actor_employee_id=employee_id,
        actor_role="customer_service",
        snapshot={"channel": channel, "reason_code": reason_code},
    )
    return {
        "id": event.id,
        "order_id": order.id,
        "channel": event.channel,
        "reason_code": event.reason_code,
        "contacted_at": event.contacted_at,
    }


async def list_logs(
    session: AsyncSession, actor: object, order_id: int, *, page: int = 1, page_size: int = 50
) -> dict[str, object]:
    """Read market-scoped structured entries; omit unreviewed free-text notes."""
    order, _ = await _order(session, actor, order_id, write=False)
    if not (1 <= page and 1 <= page_size <= 200):
        raise DomainError("VALIDATION_ERROR", "Invalid pagination.")
    base = select(CustomerContactLog).where(CustomerContactLog.order_id == order.id)
    total = await session.scalar(
        select(func.count()).select_from(CustomerContactLog).where(CustomerContactLog.order_id == order.id)
    )
    entries = (
        await session.scalars(
            base.order_by(CustomerContactLog.contacted_at.desc(), CustomerContactLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            {
                "id": entry.id,
                "order_id": order.id,
                "channel": entry.channel,
                "reason_code": entry.reason_code,
                "contacted_at": entry.contacted_at,
            }
            for entry in entries
        ],
        "page": page,
        "page_size": page_size,
        "total": int(total or 0),
    }
