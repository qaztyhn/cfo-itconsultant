"""M8 operational KPI, baseline and immutable decision-log REST endpoints.

Handlers authenticate, validate query/body parameters and delegate all market,
location, business calculations and record-level RBAC to kpi_service.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.v1.common import PageNo, PageSize
from app.deps import AuthUser, DbSession
from app.services import kpi_service

router = APIRouter(tags=["kpi"])

FromDate = Annotated[date | None, Query(alias="from")]
ToDate = Annotated[date | None, Query(alias="to")]
WarehouseId = Annotated[int | None, Query(gt=0)]
StoreId = Annotated[int | None, Query(gt=0)]
OrderId = Annotated[int | None, Query(gt=0)]


class BaselineInput(BaseModel):
    value: Decimal = Field(ge=0)


@router.get("/kpi/summary")
async def kpi_summary(
    user: AuthUser,
    db: DbSession,
    date_from: FromDate = None,
    date_to: ToDate = None,
    warehouse_id: WarehouseId = None,
    store_id: StoreId = None,
) -> dict[str, object]:
    """US-KPI-01 AC1–4: source-based market-local metrics; unknown is null."""
    return await kpi_service.summary(
        db,
        user,
        date_from=date_from,
        date_to=date_to,
        warehouse_id=warehouse_id,
        store_id=store_id,
    )


@router.get("/kpi/daily")
async def kpi_daily(
    user: AuthUser,
    db: DbSession,
    metric: str,
    date_from: FromDate = None,
    date_to: ToDate = None,
) -> dict[str, object]:
    """US-KPI-01 AC1: daily series from trusted source event dates."""
    return await kpi_service.daily(db, user, metric=metric, date_from=date_from, date_to=date_to)


@router.get("/kpi/diagnostics")
async def kpi_diagnostics(user: AuthUser, db: DbSession) -> dict[str, object]:
    """Existing diagnostic keys; unavailable until source definitions approved."""
    return await kpi_service.diagnostics(db, user)


@router.put("/kpi/baseline/{metric}")
async def put_baseline(metric: str, body: BaselineInput, user: AuthUser, db: DbSession) -> dict[str, object]:
    """US-KPI-02 AC1: admin-only baseline write with existing decision audit."""
    return await kpi_service.put_baseline(db, user, metric=metric, value=body.value)


@router.get("/audit/decisions")
async def audit_decisions(
    user: AuthUser,
    db: DbSession,
    order_id: OrderId = None,
    action: str | None = None,
    date_from: FromDate = None,
    date_to: ToDate = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> dict[str, object]:
    """US-LOG-01: read-only paginated audit, with server-side PII redaction."""
    return await kpi_service.decision_log(
        db,
        user,
        order_id=order_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
