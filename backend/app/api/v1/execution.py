"""Thực thi (06 mục 8).

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M6.
"""

from fastapi import APIRouter

router = APIRouter(tags=["execution"])


@router.post("/orders/{order_id}/events")
async def record_event(order_id: int) -> dict[str, object]:
    """POST /orders/{order_id}/events — Idempotency-Key; warehouse/driver theo loại sự kiện."""
    raise NotImplementedError


@router.get("/warehouses/{warehouse_id}/prep-queue")
async def prep_queue(warehouse_id: int) -> dict[str, object]:
    """GET /warehouses/{warehouse_id}/prep-queue — Hàng đợi chuẩn bị."""
    raise NotImplementedError


@router.get("/prep-queue")
async def prep_queue_v2() -> dict[str, object]:
    """GET /prep-queue — Phụ lục A: capacity theo ca + orders (không thiết bị)."""
    raise NotImplementedError


@router.get("/warehouses/{warehouse_id}/capacity")
async def warehouse_capacity(warehouse_id: int) -> dict[str, object]:
    """GET /warehouses/{warehouse_id}/capacity — Công suất theo ngày."""
    raise NotImplementedError


@router.get("/driver/trips")
async def driver_trips() -> dict[str, object]:
    """GET /driver/trips — Chuyến của tài xế đang đăng nhập."""
    raise NotImplementedError


@router.get("/driver/trips/{trip_id}")
async def driver_trip(trip_id: int) -> dict[str, object]:
    """GET /driver/trips/{trip_id} — Chi tiết chuyến."""
    raise NotImplementedError
