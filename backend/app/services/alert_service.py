"""Cảnh báo (US-RSK-03).

raise_alert dùng dedupe_key; chỉ chặn trùng khi alert còn mở (ux_alert_open_dedupe). list theo phạm vi,
critical trước; ack ghi acknowledged_by/at.

Owner: Dev 1 (A) — M7.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.domain.models.ops import Alert


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
