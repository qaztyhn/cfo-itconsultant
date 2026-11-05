"""Ánh xạ SKU, chỉ IT (09 bất biến 9; US-PRD-01..05).

Tạo/cập nhật mapping_task (blocked_order_count), tính ứng viên (engine.mapping_candidates + pg_trgm),
confirm (chọn hoặc tạo global; N6 không được có FRAGILE → 422) → mở khóa đơn BLOCKED_UNMAPPED_SKU → lập kế
hoạch; reject bắt buộc lý do. Ghi MAPPING_CONFIRMED/MAPPING_REJECTED.

Owner: Dev 1 (A) — M2.
"""


async def ensure_task(market_code: str, local_sku: str, order_id: int) -> int:
    """TODO(#mapping-ensure_task)."""
    raise NotImplementedError


async def confirm(task_id: int, actor_id: int, payload: dict[str, object]) -> None:
    """TODO(#mapping-confirm)."""
    raise NotImplementedError


async def reject(task_id: int, actor_id: int, reason_text: str) -> None:
    """TODO(#mapping-reject)."""
    raise NotImplementedError
