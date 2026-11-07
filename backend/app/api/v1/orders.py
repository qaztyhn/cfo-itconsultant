"""Đơn hàng (06 mục 5, Phụ lục A). Phạm vi theo vai trò; ngoài phạm vi → 404.

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M2.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.v1.common import Page, PageNo, PageSize, SortParam
from app.deps import AuthUser, DbSession
from app.services import order_read_service

router = APIRouter(tags=["orders"])


class Ref(BaseModel):
    id: int
    code: str | None = None


class DateRequestOut(BaseModel):
    mode: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    window: dict[str, str] | None = None


class OrderListItem(BaseModel):
    """06 mục 5.4; trường bị cấm theo vai trò không có mặt (exclude_unset)."""

    id: int
    order_no: str
    status: str
    customer_name: str
    site: str
    warehouse: Ref | None = None
    origin_store: Ref | None = None
    date_request: DateRequestOut | None = None
    committed_date: date | None = None
    promise_end: datetime | None = None
    risk_color: str | None = None
    block_reason: str | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    submitted_at: datetime


class NamedRef(BaseModel):
    id: int | None = None
    name: str
    type: str | None = None


class ContactOut(BaseModel):
    name: str
    phone: str | None
    email: str | None


class DeliveryOut(BaseModel):
    address: str
    lat: float
    lon: float
    receiving_restrictions: str | None
    special_requirements: str | None


class CommittedOut(BaseModel):
    date: date | None
    promise_start: datetime | None
    promise_end: datetime | None


class LineOut(BaseModel):
    line_no: int
    local_sku: str | None = None
    global_code: str | None = None
    name: str | None = None
    qty_sale: Decimal
    sale_unit: str | None = None
    qty_base: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None
    handling_group: str | None = None
    flags: list[str] | None = None


class TotalsOut(BaseModel):
    weight_kg: float | None = None
    volume_m3: float | None = None
    amount: Decimal | None = None
    currency: str | None = None


class RiskOut(BaseModel):
    status: str
    color: str
    forecast_eta: datetime
    planned_eta: datetime | None = None
    commitment_deadline: datetime | None = None
    slack_min: int | None = None
    consumption_pct: float | None = None


class OrderOut(BaseModel):
    """06 mục 5.1 với trường theo vai trò mục 5.3 (bỏ trường bị cấm, không trả null thay thế)."""

    id: int
    order_no: str
    external_ref: str | None = None
    status: str
    market: str
    customer: NamedRef
    contact: ContactOut
    delivery: DeliveryOut
    date_request: DateRequestOut
    committed: CommittedOut
    origin_store: NamedRef | None = None
    sales: NamedRef | None = None
    lines: list[LineOut]
    totals: TotalsOut
    block_reason: str | None = None
    approved_plan_id: int | None = None
    latest_run_id: int | None = None
    risk: RiskOut | None = None
    version: int
    submitted_at: datetime


class NavCounts(BaseModel):
    order_queue: int
    exceptions: int
    tracking_risk: int


class OrderCounts(BaseModel):
    all: int
    needs_plan: int
    awaiting_approval: int
    no_feasible_date: int
    in_execution: int
    replan_suggested: int
    delivered_today: int
    nav: NavCounts


_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "AUTH_INVALID"},
    403: {"description": "FORBIDDEN — role cannot read orders"},
    404: {"description": "NOT_FOUND — missing or outside the caller's scope"},
    422: {"description": "VALIDATION_ERROR"},
}


@router.get(
    "/orders", response_model=Page[OrderListItem], response_model_exclude_unset=True, responses=_ERRORS
)
async def list_orders(
    user: AuthUser,
    db: DbSession,
    status: Annotated[str | None, Query(description="One or more statuses, comma separated")] = None,
    risk_color: str | None = None,
    committed_date_from: date | None = None,
    committed_date_to: date | None = None,
    warehouse_id: int | None = None,
    store_id: int | None = None,
    date_mode: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    blocked: bool | None = None,
    sort: SortParam = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[OrderListItem]:
    """GET /orders — phạm vi 06 mục 5.2; mặc định sắp theo thứ tự đặt `submitted_at, id` (mục 5.4)."""
    scope = await order_read_service.resolve_order_scope(db, user)
    items, total = await order_read_service.list_orders(
        db,
        scope,
        status=status,
        risk_color=risk_color,
        committed_date_from=committed_date_from,
        committed_date_to=committed_date_to,
        warehouse_id=warehouse_id,
        store_id=store_id,
        date_mode=date_mode,
        q=q,
        blocked=blocked,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page[OrderListItem](
        items=[OrderListItem.model_validate(i) for i in items], page=page, page_size=page_size, total=total
    )


@router.get("/orders/counts", response_model=OrderCounts, responses=_ERRORS)
async def order_counts(user: AuthUser, db: DbSession) -> OrderCounts:
    """GET /orders/counts — số đếm chip/huy hiệu theo phạm vi (06 mục 5.4, Phụ lục A)."""
    scope = await order_read_service.resolve_order_scope(db, user)
    return OrderCounts.model_validate(await order_read_service.counts(db, scope))


@router.get(
    "/orders/{order_id}", response_model=OrderOut, response_model_exclude_unset=True, responses=_ERRORS
)
async def get_order(order_id: int, user: AuthUser, db: DbSession) -> OrderOut:
    """GET /orders/{id} — trường theo vai trò (06 mục 5.3); ngoài phạm vi → 404."""
    scope = await order_read_service.resolve_order_scope(db, user)
    return OrderOut.model_validate(await order_read_service.get_order(db, scope, order_id))


@router.get("/orders/{order_id}/timeline")
async def order_timeline(order_id: int) -> dict[str, object]:
    """GET /orders/{order_id}/timeline — dispatcher, warehouse, CS, admin."""
    raise NotImplementedError


@router.get("/orders/{order_id}/eta-forecasts")
async def order_eta_forecasts(order_id: int) -> dict[str, object]:
    """GET /orders/{order_id}/eta-forecasts — dispatcher, warehouse, CS."""
    raise NotImplementedError


@router.post("/orders/{order_id}/replan")
async def replan_order(order_id: int) -> dict[str, object]:
    """POST /orders/{order_id}/replan — dispatcher; đóng kế hoạch cũ (05 mục 6); ORDER_REPLAN."""
    raise NotImplementedError


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: int) -> dict[str, object]:
    """POST /orders/{order_id}/cancel — dispatcher; reason_text bắt buộc; chỉ trước DISPATCHED."""
    raise NotImplementedError


@router.get("/orders/{order_id}/notifications")
async def order_notifications(order_id: int) -> dict[str, object]:
    """GET /orders/{order_id}/notifications — dispatcher, CS."""
    raise NotImplementedError


@router.post("/orders/{order_id}/contact-logs")
async def create_contact_log(order_id: int) -> dict[str, object]:
    """POST /orders/{order_id}/contact-logs — customer_service (06 mục 11)."""
    raise NotImplementedError


@router.get("/orders/{order_id}/contact-logs")
async def list_contact_logs(order_id: int) -> dict[str, object]:
    """GET /orders/{order_id}/contact-logs — dispatcher, CS."""
    raise NotImplementedError


@router.post("/orders/{order_id}/delay-notice")
async def manual_delay_notice(order_id: int) -> dict[str, object]:
    """POST /orders/{order_id}/delay-notice — dispatcher tự soạn thông báo trễ."""
    raise NotImplementedError
