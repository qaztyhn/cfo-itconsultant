"""Endpoint hợp đồng nguồn (06 mục 16). Phân trang page_size ≤ 500, thứ tự (updated_at, id), X-Total-Count.

Owner: Dev 2 (luồng B) — M1.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, field_serializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.db import database_ready
from app.models import Stock
from app.orders_read import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, OrderPage, OrderStatus, list_orders
from app.reference_read import router as reference_router

router = APIRouter(dependencies=[Depends(require_api_key)])
health_router = APIRouter()
router.include_router(reference_router)


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


@router.post("/orders")
async def create_order() -> dict[str, object]:
    """POS: tạo đơn nháp (DRAFT)."""
    raise NotImplementedError


@router.put("/orders/{order_id}")
async def update_order(order_id: str) -> dict[str, object]:
    """POS: sửa đơn, tăng version."""
    raise NotImplementedError


@router.post("/orders/{order_id}/validate")
async def validate_order(order_id: str) -> dict[str, object]:
    """Sales Validation: khách, địa chỉ/tọa độ, dòng hàng, ngày và khung giờ (US-SRC-03)."""
    raise NotImplementedError


@router.post("/orders/{order_id}/submit")
async def submit_order(order_id: str) -> dict[str, object]:
    """Chuyển SUBMITTED_FOR_PLANNING — chỉ sau validate thành công (US-ORD-01 AC4)."""
    raise NotImplementedError


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str) -> dict[str, object]:
    """Hủy đơn ở nguồn."""
    raise NotImplementedError


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
