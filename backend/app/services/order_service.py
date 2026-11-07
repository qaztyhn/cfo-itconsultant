"""Đơn hàng (US-ORD-01..05).

prepare_for_planning: kiểm ánh xạ (thiếu → BLOCKED_UNMAPPED_SKU + mapping_task), chụp địa chỉ, sinh
order_no, gọi PlanningService. Danh sách/chi tiết/timeline theo phạm vi (ngoài phạm vi → 404), bản rút gọn
cho sales/CS/driver (06 mục 5.1). counts() cho chip/huy hiệu. replan()/cancel() đóng kế hoạch cũ qua
domain.transitions.

Owner: Dev 1 (A) — M2.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.domain.enums import OrderStatus
from app.domain.models.ops import CustomerOrder, OrderLine
from app.domain.transitions import SYSTEM_ROLE, transition
from app.services import mapping_service

_QTY = Decimal("0.001")  # order_line.qty_base numeric(12,3)


_LOCAL_PRODUCTS = text("""
SELECT p.local_sku, p.global_product_id, p.units_to_base
FROM ref.v_product_local p JOIN ref.market m ON m.code = p.market_code
WHERE m.id = :market_id AND p.mapping_status = 'confirmed' AND p.local_sku = ANY(:skus)
""")

BLOCK_REASON_PREFIX = "UNMAPPED_SKU: "


@dataclass(frozen=True)
class PrepareResult:
    """Kết quả chuẩn bị: status SUBMITTED = sẵn sàng lập kế hoạch; BLOCKED_UNMAPPED_SKU kèm danh sách SKU."""

    status: OrderStatus
    unmapped_skus: tuple[str, ...] = ()


async def prepare_for_planning(session: AsyncSession, order_id: int) -> PrepareResult:
    """Kiểm ánh xạ các dòng của đơn SUBMITTED (US-PRD-01 AC1/AC2; FR-PRD-02; BR-PRD-01).

    - Dòng có SKU đã `confirmed` → điền global_product_id, qty_base = qty_sale × units_to_base.
    - Còn SKU chưa xác nhận (pending/suggested/rejected hoặc không có trong danh mục) → đơn
      BLOCKED_UNMAPPED_SKU qua transition() (vai trò system), block_reason nêu SKU, mapping_task được
      tạo/cập nhật cho từng SKU.
    - Đủ ánh xạ → đơn giữ SUBMITTED, block_reason xóa; caller gọi PlanningService.plan (M4, chưa có).

    Đơn không ở SUBMITTED → 409 ILLEGAL_TRANSITION. Chạy trong transaction của caller; không commit.
    order_no và bản chụp địa chỉ/liên hệ được ghi khi nhập đơn (cột NOT NULL của customer_order).
    """
    order = await session.scalar(select(CustomerOrder).where(CustomerOrder.id == order_id).with_for_update())
    if order is None:
        raise DomainError("NOT_FOUND", "Order not found.")
    if order.status != OrderStatus.SUBMITTED:
        raise DomainError(
            "ILLEGAL_TRANSITION", "Order is not awaiting preparation.", {"from_status": order.status}
        )
    lines = (
        await session.scalars(
            select(OrderLine).where(OrderLine.order_id == order_id).order_by(OrderLine.line_no)
        )
    ).all()
    skus = [line.local_sku for line in lines]
    mapped = {
        row.local_sku: row
        for row in await session.execute(_LOCAL_PRODUCTS, {"market_id": order.market_id, "skus": skus})
    }
    unmapped: list[str] = []
    for line in lines:
        product = mapped.get(line.local_sku)
        if product is None:
            unmapped.append(line.local_sku)
            continue
        line.global_product_id = product.global_product_id
        line.qty_base = (line.qty_sale * product.units_to_base).quantize(_QTY)
    if not unmapped:
        order.block_reason = None
        await session.flush()
        return PrepareResult(OrderStatus.SUBMITTED)
    order.block_reason = BLOCK_REASON_PREFIX + ", ".join(unmapped)
    await session.flush()
    await transition(session, order_id, OrderStatus.BLOCKED_UNMAPPED_SKU, SYSTEM_ROLE)
    for sku in unmapped:
        await mapping_service.ensure_task(session, order.market_id, sku)
    return PrepareResult(OrderStatus.BLOCKED_UNMAPPED_SKU, tuple(unmapped))


async def list_orders(user: object, filters: dict[str, object]) -> dict[str, object]:
    """TODO(#order-list_orders)."""
    raise NotImplementedError


async def get_order(user: object, order_id: int) -> dict[str, object]:
    """TODO(#order-get_order)."""
    raise NotImplementedError


async def timeline(user: object, order_id: int) -> list[dict[str, object]]:
    """TODO(#order-timeline)."""
    raise NotImplementedError


async def counts(user: object) -> dict[str, object]:
    """TODO(#order-counts)."""
    raise NotImplementedError


async def replan(order_id: int, actor: object, reason_code: str, reason_text: str) -> None:
    """TODO(#order-replan)."""
    raise NotImplementedError


async def cancel(order_id: int, actor: object, reason_text: str) -> None:
    """TODO(#order-cancel)."""
    raise NotImplementedError
