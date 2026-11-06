"""record_decision() — ghi audit.decision_log trong CÙNG transaction với nghiệp vụ (09 bất biến 14).

Hành động thuộc REASON_REQUIRED mà thiếu lý do → DomainError REASON_REQUIRED (422).
correlation_id lấy từ core.correlation (US-LOG-01 AC4).

- Chỉ INSERT (bảng chỉ thêm; trigger forbid_mutation chặn UPDATE/DELETE — 09 bất biến 13).
- Không tự commit: dùng session/transaction của use case; rollback nghiệp vụ thì dòng nhật ký cũng mất.
- `ts` = clock.now() (thời điểm quyết định theo đồng hồ hệ thống/APP_NOW); `created_at` là lúc ghi bản ghi.
- Ngoài request (job) hoặc giá trị không phải UUID: sinh uuid4 mới để cột uuid NOT NULL không làm hỏng
  INSERT.

Owner: Dev 1 (luồng A) — M0.
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import REASON_REQUIRED, Action
from app.core import clock
from app.core.correlation import correlation_id_var, normalize_correlation_id
from app.core.errors import DomainError

_INSERT = text("""
INSERT INTO audit.decision_log (ts, correlation_id, actor_user_id, actor_employee_id, actor_role, action,
                                entity, entity_id, order_id, plan_id, reason_code, reason_text, snapshot,
                                before, after)
VALUES (:ts, CAST(:correlation_id AS uuid), :actor_user_id, :actor_employee_id, :actor_role, :action, :entity,
        :entity_id, :order_id, :plan_id, :reason_code, :reason_text, CAST(:snapshot AS jsonb),
        CAST(:before AS jsonb), CAST(:after AS jsonb))
RETURNING id
""")


def ensure_reason(action: Action, reason_code: str | None, reason_text: str | None) -> None:
    """Từ chối khi hành động cần lý do mà thiếu."""
    if action in REASON_REQUIRED and not (reason_code or (reason_text and reason_text.strip())):
        raise DomainError("REASON_REQUIRED", f"{action.value} requires a reason.")


def _json(value: dict[str, object] | None) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)


async def record_decision(
    session: AsyncSession,
    action: Action,
    entity: str,
    entity_id: str | None,
    order_id: int | None = None,
    plan_id: int | None = None,
    reason_code: str | None = None,
    reason_text: str | None = None,
    snapshot: dict[str, object] | None = None,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    *,
    actor_user_id: int | None = None,
    actor_employee_id: int | None = None,
    actor_role: str | None = None,
) -> int:
    """INSERT vào audit.decision_log (không UPDATE/DELETE); trả id dòng mới."""
    ensure_reason(action, reason_code, reason_text)
    result = await session.execute(
        _INSERT,
        {
            "ts": clock.now(),
            "correlation_id": normalize_correlation_id(correlation_id_var.get()),
            "actor_user_id": actor_user_id,
            "actor_employee_id": actor_employee_id,
            "actor_role": actor_role,
            "action": Action(action).value,
            "entity": entity,
            "entity_id": entity_id,
            "order_id": order_id,
            "plan_id": plan_id,
            "reason_code": reason_code,
            "reason_text": reason_text,
            "snapshot": _json(snapshot),
            "before": _json(before),
            "after": _json(after),
        },
    )
    return int(result.scalar_one())
