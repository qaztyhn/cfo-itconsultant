"""record_decision() — ghi audit.decision_log trong CÙNG transaction với nghiệp vụ (09 bất biến 14).

Hành động thuộc REASON_REQUIRED mà thiếu lý do → DomainError REASON_REQUIRED (422).
correlation_id lấy từ core.correlation (US-LOG-01 AC4).

Owner: Dev 1 (luồng A) — M0.
"""

from app.audit.actions import REASON_REQUIRED, Action
from app.core.errors import DomainError


def ensure_reason(action: Action, reason_code: str | None, reason_text: str | None) -> None:
    """Từ chối khi hành động cần lý do mà thiếu."""
    if action in REASON_REQUIRED and not (reason_code or reason_text):
        raise DomainError("REASON_REQUIRED", f"{action.value} requires a reason.")


async def record_decision(
    session: object,
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
) -> None:
    """INSERT vào audit.decision_log (không UPDATE/DELETE). TODO(#M0-audit)."""
    ensure_reason(action, reason_code, reason_text)
    raise NotImplementedError
