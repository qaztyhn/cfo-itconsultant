"""Endpoint hợp đồng nguồn (06 mục 16). Phân trang page_size ≤ 500, thứ tự (updated_at, id), X-Total-Count.

Owner: Dev 2 (luồng B) — M1.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, field_serializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import lists_read as lists
from app.auth import require_api_key
from app.core import clock
from app.db import database_ready
from app.models import Stock
from app.order_create import create
from app.order_edit import cancel, update
from app.order_payloads import CancelIn, OrderEditIn, OrderIn
from app.order_validation import validate_or_submit
from app.orders_read import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, OrderOut, OrderPage, OrderStatus, list_orders

router = APIRouter(dependencies=[Depends(require_api_key)])
health_router = APIRouter()


@router.get("/orders", response_model=OrderPage)
async def list_orders_endpoint(
    request: Request,
    response: Response,
    updated_since: AwareDatetime | None = None,
    status: OrderStatus = "SUBMITTED_FOR_PLANNING",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> OrderPage:
    """Đơn kèm dòng, bản chụp địa chỉ/liên hệ, version, updated_at (06 mục 16; SRC-Q1/Q6/Q7)."""
    result = await list_orders(
        request.app.state.engine, status=status, updated_since=updated_since, page=page, page_size=page_size
    )
    response.headers["X-Total-Count"] = str(result.total)
    return result


@router.get("/customers", response_model=lists.CustomerPage)
async def list_customers(paging: lists.PagingDep) -> lists.CustomerPage:
    """Khách (D1-A)."""
    return await lists.customers(paging)


@router.get("/products", response_model=lists.ProductPage)
async def list_products(paging: lists.PagingDep) -> lists.ProductPage:
    """Sản phẩm nội bộ (mã, tên, loại, GTIN, đơn vị, quy đổi, giá, cân nặng, thể tích) (D1-A)."""
    return await lists.products(paging)


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


class StockItem(BaseModel):
    warehouse_code: str
    sku: str
    on_hand: Decimal
    reserved: Decimal

    @field_serializer("on_hand", "reserved")
    def _plain_number(self, value: Decimal) -> int | float:
        return _number(value)


class StockSnapshot(BaseModel):
    as_of: datetime | None
    items: list[StockItem]


@router.get("/stock", response_model=StockSnapshot)
async def stock_snapshot(request: Request) -> StockSnapshot:
    """Ảnh chụp tồn kho toàn bộ kèm as_of (06 mục 16).

    `as_of` là thời điểm CŨ NHẤT trong các dòng (không khẳng định dữ liệu mới hơn thực tế). Bảng không có dòng
    thì trả `as_of = null` và `items = []`: nguồn chưa lưu thời điểm của lô rỗng (SRC-Q9 chưa duyệt) nên KHÔNG
    được bịa `as_of`; adapter CFO yêu cầu `as_of` hợp lệ và sẽ từ chối thay vì coi là tồn kho 0.
    """
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session:
        rows = (
            (await session.execute(select(Stock).order_by(Stock.warehouse_code, Stock.sku))).scalars().all()
        )
    return StockSnapshot(
        as_of=min((r.as_of for r in rows), default=None),
        items=[
            StockItem(warehouse_code=r.warehouse_code, sku=r.sku, on_hand=r.on_hand, reserved=r.reserved)
            for r in rows
        ],
    )


@router.get("/inbound", response_model=lists.InboundPage)
async def inbound(paging: lists.PagingDep) -> lists.InboundPage:
    """Hàng nhập: inbound_ref, warehouse_code, sku, qty, eta_date, confirmed, received (D1-A)."""
    return await lists.inbound(paging)


@router.get("/fleet/calendar", response_model=lists.FleetPage)
async def fleet_calendar(
    paging: lists.PagingDep,
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: AwareDatetime | None = None,
) -> lists.FleetPage:
    """Khoảng bận của xe giao nửa mở [from, to) (D1-A)."""
    return await lists.fleet_calendar(paging, from_, to)


@router.post("/orders", status_code=201, response_model=OrderOut)
async def create_order(
    request: Request, payload: OrderIn, idempotency_key: Annotated[UUID | None, Header()] = None
) -> OrderOut:
    """POS: tạo đơn nháp (DRAFT)."""
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session, session.begin():
        return await create(
            session,
            payload,
            now=clock.now(request.app.state.settings.app_now),
            key=str(idempotency_key) if idempotency_key else None,
        )


@router.put("/orders/{order_id}", response_model=OrderOut)
async def update_order(request: Request, order_id: str, payload: OrderEditIn) -> OrderOut:
    """POS: sửa đơn, tăng version."""
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session, session.begin():
        return await update(session, order_id, payload, now=clock.now(request.app.state.settings.app_now))


@router.post("/orders/{order_id}/validate", response_model=OrderOut)
async def validate_order(request: Request, order_id: str) -> OrderOut:
    """Sales Validation: khách, địa chỉ/tọa độ, dòng hàng, ngày và khung giờ (US-SRC-03)."""
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session, session.begin():
        return await validate_or_submit(
            session, order_id, now=clock.now(request.app.state.settings.app_now), submit=False
        )


@router.post("/orders/{order_id}/submit", response_model=OrderOut)
async def submit_order(request: Request, order_id: str) -> OrderOut:
    """Chuyển SUBMITTED_FOR_PLANNING — chỉ sau validate thành công (US-ORD-01 AC4)."""
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session, session.begin():
        return await validate_or_submit(
            session, order_id, now=clock.now(request.app.state.settings.app_now), submit=True
        )


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(request: Request, order_id: str, payload: CancelIn) -> OrderOut:
    """Hủy đơn ở nguồn."""
    async with AsyncSession(request.app.state.engine, expire_on_commit=False) as session, session.begin():
        return await cancel(session, order_id, payload, now=clock.now(request.app.state.settings.app_now))


@router.get("/addresses", response_model=lists.AddressPage)
async def addresses(
    paging: lists.PagingDep, customer_id: str | None = None, q: str | None = None
) -> lists.AddressPage:
    """Địa chỉ seed sẵn kèm tọa độ (thay geocoding thật); lọc theo khách / văn bản địa chỉ (D1-A)."""
    return await lists.addresses(paging, customer_id, q)


@health_router.get("/health")
async def health(ready: Annotated[bool, Depends(database_ready)]) -> JSONResponse:
    """Public health probe; do not report healthy when the database is unavailable."""
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ok" if ready else "error",
            "db": "ok" if ready else "unavailable",
        },
    )
