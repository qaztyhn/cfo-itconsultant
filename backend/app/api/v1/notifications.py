"""Customer notification endpoints; never send email from a request handler.

Roles and market scope are checked by notify_service. Order-specific paths
are registered here exactly once; the obsolete orders-router stubs are removed.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.common import PageNo, PageSize
from app.core.errors import DomainError
from app.deps import AuthUser, DbSession
from app.domain.models.ops import Notification
from app.services import notify_service
from app.services.notify_service import DelaySendInput, DraftInput

router = APIRouter(tags=["notifications"])


class DiscardInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_text: str = Field(min_length=1, max_length=2000)


@router.get("/notifications")
async def list_notifications(
    user: AuthUser,
    db: DbSession,
    order_id: Annotated[int | None, Query(gt=0)] = None,
    template: str | None = None,
    status: str | None = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> dict[str, object]:
    return await notify_service.list_notifications(
        db,
        user,
        order_id=order_id,
        template=template,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/notifications/{notification_id}")
async def get_notification(notification_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
    return await notify_service.get_notification(db, notification_id, user)


@router.post("/notifications/{notification_id}/send")
async def send_notification(
    notification_id: int,
    payload: DelaySendInput,
    user: AuthUser,
    db: DbSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    """Dispatcher approval queues a DELAY; the worker sends only after commit."""
    if idempotency_key is None:
        raise DomainError("VALIDATION_ERROR", "Idempotency-Key header is required.", http_status=400)
    return await notify_service.send_draft(
        notification_id, user, payload.model_dump(mode="json"), idempotency_key, session=db
    )


@router.post("/notifications/{notification_id}/discard")
async def discard_notification(
    notification_id: int, payload: DiscardInput, user: AuthUser, db: DbSession
) -> dict[str, object]:
    """Suppress a draft, never forward the internal free-text reason to a recipient."""
    return await notify_service.discard_draft(notification_id, user, payload.reason_text, session=db)


@router.get("/orders/{order_id}/notifications")
async def order_notifications(order_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
    """06 section 10: dispatcher/CS order history, admin excluded from this route."""
    if not {"dispatcher", "customer_service"}.intersection(user.roles):
        raise DomainError("FORBIDDEN", "Order notification history requires dispatcher or CS.")
    await notify_service._scope_order(db, order_id, user)
    return await notify_service.list_notifications(db, user, order_id=order_id)


@router.post("/orders/{order_id}/delay-notice")
async def manual_delay_notice(
    order_id: int, payload: DraftInput, user: AuthUser, db: DbSession
) -> dict[str, object]:
    """Only creates the reviewed draft. The separate Send action is mandatory."""
    result = await notify_service.create_delay_draft(
        order_id, payload.model_dump(mode="json"), session=db, actor=user
    )
    if result is None:
        return {"id": None, "status": "unchanged"}
    notification = await db.get(Notification, result)
    assert notification is not None
    return {"id": result, "status": notification.status}
