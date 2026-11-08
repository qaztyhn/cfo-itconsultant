"""Cảnh báo (US-RSK-03).

raise_alert dùng dedupe_key; chỉ chặn trùng khi alert còn mở (ux_alert_open_dedupe). list theo phạm vi,
critical trước; ack ghi acknowledged_by/at.

Owner: Dev 1 (A) — M7.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import DomainError
from app.domain.models.ops import Alert, CustomerOrder
from app.domain.models.plan import FulfilmentPlan
from app.domain.models.ref import Market


async def raise_alert(
    session: AsyncSession,
    *,
    market_id: int,
    type_: str,
    level: str,
    message: str,
    dedupe_key: str,
    target_roles: Sequence[str],
    order_id: int | None = None,
) -> int | None:
    """Tạo cảnh báo; nếu đã có cảnh báo CÒN MỞ cùng `dedupe_key` thì không tạo (trả None).

    Dựa vào chỉ mục duy nhất một phần `ux_alert_open_dedupe` (resolved_at IS NULL) nên an toàn khi gọi
    đồng thời.
    Nội dung `message` không được chứa PII hay tọa độ GPS (09 bất biến 4, 16).
    """
    stmt = (
        insert(Alert)
        .values(
            market_id=market_id,
            order_id=order_id,
            level=level,
            type=type_,
            message=message,
            target_roles=list(target_roles),
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing(index_elements=[Alert.dedupe_key], index_where=Alert.resolved_at.is_(None))
        .returning(Alert.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def ack(session: AsyncSession, alert_id: int, *, employee_id: int, now: datetime) -> None:
    """Ghi acknowledged_by/at lần đầu (lần ack sau không ghi đè); không tồn tại → 404 NOT_FOUND."""
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise DomainError("NOT_FOUND", "Alert not found.")
    if alert.acknowledged_at is None:
        alert.acknowledged_by = employee_id
        alert.acknowledged_at = now


async def resolve(session: AsyncSession, dedupe_key: str, *, now: datetime) -> int:
    """Đóng cảnh báo đang mở của `dedupe_key` (điều kiện đã hết); trả số dòng đã đóng."""
    result = await session.execute(
        update(Alert)
        .where(Alert.dedupe_key == dedupe_key, Alert.resolved_at.is_(None))
        .values(resolved_at=now)
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


def _roles(actor: object) -> tuple[str, ...]:
    return tuple(getattr(actor, "roles", ()))


async def _visible_alerts(session: AsyncSession, actor: object):
    """Server-side role, market, target and warehouse checks BEFORE pagination.

    CS receives a reduced view; never expose arbitrary alert messages to CS.
    The warehouse scope is derived from the approved plan, not a caller filter.
    """
    roles = _roles(actor)
    permitted = {"admin", "dispatcher", "warehouse", "customer_service"}
    if not permitted.intersection(roles):
        raise DomainError("FORBIDDEN", "Alert access is not permitted.")
    market = getattr(actor, "market", "")
    stmt = select(Alert).outerjoin(CustomerOrder, CustomerOrder.id == Alert.order_id)
    if "admin" not in roles:
        if not isinstance(market, str) or not market:
            raise DomainError("FORBIDDEN", "Market scope is required.")
        stmt = stmt.join(Market, Market.id == Alert.market_id).where(Market.code == market)
    if "dispatcher" in roles or "admin" in roles:
        return stmt
    if "warehouse" in roles:
        ids = tuple(getattr(actor, "location_ids", ()))
        if not ids:
            raise DomainError("FORBIDDEN", "No managed warehouse scope.")
        return stmt.join(
            FulfilmentPlan,
            FulfilmentPlan.id == CustomerOrder.approved_plan_id,
        ).where(
            FulfilmentPlan.warehouse_id.in_(ids),
            Alert.target_roles.any("warehouse"),
        )
    # Customer service is a reduced, explicitly targeted view only.
    return stmt.where(Alert.target_roles.any("customer_service"))


async def list_alerts(
    session: AsyncSession,
    actor: object,
    *,
    type_: str | None = None,
    level: str | None = None,
    resolved: bool | None = None,
    order_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    """US-RSK-03 AC1: critical first; no cross-market or cross-location leak."""
    stmt = await _visible_alerts(session, actor)
    if type_ is not None:
        stmt = stmt.where(Alert.type == type_)
    if level is not None:
        stmt = stmt.where(Alert.level == level)
    if resolved is not None:
        stmt = stmt.where(Alert.resolved_at.is_not(None) if resolved else Alert.resolved_at.is_(None))
    if order_id is not None:
        stmt = stmt.where(Alert.order_id == order_id)
    total = int((await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))) or 0)
    rows = (
        await session.scalars(
            stmt.order_by(
                (Alert.level == "critical").desc(),
                Alert.created_at.desc(),
                Alert.id.desc(),
            ).limit(page_size).offset((page - 1) * page_size)
        )
    ).all()
    reduced = "customer_service" in _roles(actor) and not (
        {"admin", "dispatcher"} & set(_roles(actor))
    )
    return {
        "items": [
            {
                "id": a.id,
                "order_id": a.order_id,
                "type": a.type,
                "level": a.level,
                "message": None if reduced else a.message,
                "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


async def acknowledge(session: AsyncSession, alert_id: int, actor: object) -> dict[str, object]:
    """US-RSK-03 AC2: locked, idempotent, scope-safe first acknowledgement."""
    roles = _roles(actor)
    if not ({"dispatcher", "admin"} & set(roles)):
        raise DomainError("FORBIDDEN", "Only dispatcher or admin may acknowledge alerts.")
    visible = await _visible_alerts(session, actor)
    alert = await session.scalar(visible.where(Alert.id == alert_id).with_for_update(of=Alert))
    if alert is None:
        raise DomainError("NOT_FOUND", "Alert not found.")
    employee = getattr(actor, "employee_id", None)
    if not isinstance(employee, int):
        raise DomainError("FORBIDDEN", "Active employee assignment required.")
    if alert.acknowledged_at is None:
        await ack(session, alert.id, employee_id=employee, now=clock.now())
        await session.flush()
    return {
        "id": alert.id,
        "acknowledged_by": alert.acknowledged_by,
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
    }
