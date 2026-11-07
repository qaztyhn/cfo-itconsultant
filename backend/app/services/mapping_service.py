"""Ánh xạ SKU, chỉ IT (09 bất biến 9; US-PRD-01..05).

Tạo/cập nhật mapping_task (blocked_order_count), tính ứng viên (engine.mapping_candidates + pg_trgm),
confirm (chọn hoặc tạo global; N6 không được có FRAGILE → 422) → mở khóa đơn BLOCKED_UNMAPPED_SKU → lập kế
hoạch; reject bắt buộc lý do. Ghi MAPPING_CONFIRMED/MAPPING_REJECTED.

Owner: Dev 1 (A) — M2.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_UPSERT_TASK = text("""
INSERT INTO ref.mapping_task AS t (market_id, local_sku, blocked_order_count)
VALUES (:market_id, :local_sku, (
    SELECT count(DISTINCT o.id) FROM ops.customer_order o JOIN ops.order_line l ON l.order_id = o.id
    WHERE o.market_id = :market_id AND o.status = 'BLOCKED_UNMAPPED_SKU' AND l.local_sku = :local_sku))
ON CONFLICT (market_id, local_sku) DO UPDATE SET blocked_order_count = EXCLUDED.blocked_order_count
RETURNING t.id
""")


async def ensure_task(session: AsyncSession, market_id: int, local_sku: str) -> int:
    """Tạo hoặc cập nhật mapping_task cho (market, SKU); trả id (US-PRD-01 AC1/AC2).

    blocked_order_count được TÍNH LẠI = số đơn đang BLOCKED_UNMAPPED_SKU của market có dòng chứa SKU, thay vì
    cộng dồn, nên gọi lại cho cùng một đơn (nhập lại, chạy lại) không đếm trùng. Gọi SAU khi đơn đã chuyển
    trạng thái, trong cùng transaction. Không đổi status/assigned_to của task đã có. Không commit.
    """
    result = await session.execute(_UPSERT_TASK, {"market_id": market_id, "local_sku": local_sku})
    return int(result.scalar_one())


async def confirm(task_id: int, actor_id: int, payload: dict[str, object]) -> None:
    """TODO(#mapping-confirm)."""
    raise NotImplementedError


async def reject(task_id: int, actor_id: int, reason_text: str) -> None:
    """TODO(#mapping-reject)."""
    raise NotImplementedError
