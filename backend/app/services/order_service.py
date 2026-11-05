"""Đơn hàng (US-ORD-01..05).

prepare_for_planning: kiểm ánh xạ (thiếu → BLOCKED_UNMAPPED_SKU + mapping_task), chụp địa chỉ, sinh
order_no, gọi PlanningService. Danh sách/chi tiết/timeline theo phạm vi (ngoài phạm vi → 404), bản rút gọn
cho sales/CS/driver (06 mục 5.1). counts() cho chip/huy hiệu. replan()/cancel() đóng kế hoạch cũ qua
domain.transitions.

Owner: Dev 1 (A) — M2.
"""


async def prepare_for_planning(order_id: int) -> None:
    """TODO(#order-prepare_for_planning)."""
    raise NotImplementedError


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
