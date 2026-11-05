"""Đơn hàng (06 mục 5, Phụ lục A). Phạm vi theo vai trò; ngoài phạm vi → 404.

Router mỏng: validate, kiểm vai trò + phạm vi ở máy chủ, gọi service (09 mục 5, 7).
Mỗi endpoint cần test đường được phép và bị cấm (06 mục 3).

Owner: Dev 1 (A) — M2.
"""

from fastapi import APIRouter

router = APIRouter(tags=["orders"])


@router.get("/orders")
async def list_orders() -> dict[str, object]:
    """GET /orders — Lọc status, risk_color, committed_date_from/to, warehouse_id, store_id, date_mode, q,
    needs_manual, blocked."""
    raise NotImplementedError


@router.get("/orders/counts")
async def order_counts() -> dict[str, object]:
    """GET /orders/counts — Số đếm cho chip lọc và huy hiệu menu."""
    raise NotImplementedError


@router.get("/orders/{order_id}")
async def get_order(order_id: int) -> dict[str, object]:
    """GET /orders/{order_id} — Chi tiết; bản rút gọn cho sales/CS/driver."""
    raise NotImplementedError


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


@router.post("/orders/{order_id}/external-handoff")
async def external_handoff(order_id: int) -> dict[str, object]:
    """POST /orders/{order_id}/external-handoff — dispatcher; MANUAL_PLANNING → HANDLED_EXTERNALLY (06 mục
    6.6)."""
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
