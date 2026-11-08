"""Endpoint hợp đồng nguồn (06 mục 16). Phân trang page_size ≤ 500, thứ tự (updated_at, id), X-Total-Count.

Owner: Dev 2 (luồng B) — M1.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from app.auth import require_api_key
from app.db import database_ready
from app.orders_read import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, OrderPage, OrderStatus, list_orders

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


@router.get("/customers")
async def list_customers(updated_since: str | None = None) -> dict[str, object]:
    """Khách."""
    raise NotImplementedError


@router.get("/products")
async def list_products(updated_since: str | None = None) -> dict[str, object]:
    """Sản phẩm nội bộ (mã, tên, loại, GTIN, đơn vị, quy đổi, giá, cân nặng, thể tích)."""
    raise NotImplementedError


@router.get("/stock")
async def stock_snapshot() -> dict[str, object]:
    """Ảnh chụp tồn kho toàn bộ kèm as_of."""
    raise NotImplementedError


@router.get("/inbound")
async def inbound() -> dict[str, object]:
    """Hàng nhập chưa về (inbound_ref, warehouse_code, sku, qty, eta_date, confirmed)."""
    raise NotImplementedError


@router.get("/fleet/calendar")
async def fleet_calendar(date_from: str, date_to: str) -> dict[str, object]:
    """Khoảng bận của xe."""
    raise NotImplementedError


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


@router.get("/addresses")
async def addresses(q: str = "") -> dict[str, object]:
    """Địa chỉ seed sẵn kèm tọa độ (thay geocoding thật)."""
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
