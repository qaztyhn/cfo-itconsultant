"""M7 alert API: parameters and authentication only; RBAC and scope in service."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.v1.common import PageNo, PageSize
from app.deps import AuthUser, DbSession
from app.services import alert_service

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
async def list_alerts(
    user: AuthUser,
    db: DbSession,
    type: str | None = None,
    level: str | None = None,
    resolved: bool | None = None,
    order_id: Annotated[int | None, Query(gt=0)] = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> dict[str, object]:
    """US-RSK-03 AC1: critical first, warehouse and market restrictions."""
    return await alert_service.list_alerts(
        db,
        user,
        type_=type,
        level=level,
        resolved=resolved,
        order_id=order_id,
        page=page,
        page_size=page_size,
    )


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
    """US-RSK-03 AC2: first acknowledgment wins; dispatcher/admin only."""
    return await alert_service.acknowledge(db, alert_id, user)
