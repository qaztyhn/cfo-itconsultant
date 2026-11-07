"""Nạp ngữ cảnh từ DB cho engine lập kế hoạch (04 mục 6.1; 05 mục 6–7). Chỉ đọc, không khóa.

- `available_stock`: on_hand − wms_reserved − giữ chỗ hàng của ĐƠN KHÁC (committed + held còn hạn), không âm.
  Lúc lập kế hoạch KHÔNG khóa (09 bất biến 11; không `FOR UPDATE` trên ops.stock_snapshot — 09 mục 5).
- `confirmed_inbound`: hàng nhập confirmed, chưa received (hàng chưa xác nhận không tính — BR-ATP).
- `route_info`: đọc plan.route_matrix đã tính trước; engine không gọi API (09 mục 8). Thiếu cặp → None
  (engine áp dụng `routing.allow_fallback`).
Truy vấn gom theo tập kho/sản phẩm (không N+1).

Owner: Dev 1 (A) — M4.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ops import InboundShipment, StockSnapshot
from app.domain.models.plan import PlanningRun, RouteMatrix, StockReservation
from app.engine.types import InboundCtx, RouteInfo


async def available_stock(
    session: AsyncSession,
    warehouse_ids: Sequence[int],
    product_ids: Sequence[int],
    *,
    now: datetime,
    exclude_order_id: int | None,
) -> dict[int, dict[int, Decimal]]:
    """{kho: {sản phẩm: tồn khả dụng}} cho mọi cặp được hỏi (thiếu ảnh chụp → 0)."""
    on_hand: dict[tuple[int, int], Decimal] = {
        (w, p): oh - res
        for w, p, oh, res in (
            await session.execute(
                select(
                    StockSnapshot.warehouse_id,
                    StockSnapshot.global_product_id,
                    StockSnapshot.on_hand,
                    StockSnapshot.wms_reserved,
                ).where(
                    StockSnapshot.warehouse_id.in_(warehouse_ids),
                    StockSnapshot.global_product_id.in_(product_ids),
                )
            )
        ).all()
    }
    held_query = (
        select(
            StockReservation.warehouse_id, StockReservation.global_product_id, func.sum(StockReservation.qty)
        )
        .join(PlanningRun, PlanningRun.id == StockReservation.run_id)
        .where(
            StockReservation.warehouse_id.in_(warehouse_ids),
            StockReservation.global_product_id.in_(product_ids),
            or_(
                StockReservation.status == "committed",
                and_(StockReservation.status == "held", PlanningRun.hold_expires_at > now),
            ),
        )
        .group_by(StockReservation.warehouse_id, StockReservation.global_product_id)
    )
    if exclude_order_id is not None:
        held_query = held_query.where(StockReservation.order_id != exclude_order_id)
    reserved = {(w, p): q for w, p, q in (await session.execute(held_query)).all()}
    return {
        w: {
            p: max(Decimal(0), on_hand.get((w, p), Decimal(0)) - reserved.get((w, p), Decimal(0)))
            for p in product_ids
        }
        for w in warehouse_ids
    }


async def confirmed_inbound(
    session: AsyncSession, warehouse_ids: Sequence[int], product_ids: Sequence[int]
) -> dict[int, tuple[InboundCtx, ...]]:
    """{kho: hàng nhập confirmed & chưa received của các sản phẩm được hỏi}, sắp theo ETA rồi mã."""
    result = await session.execute(
        select(InboundShipment)
        .where(
            InboundShipment.warehouse_id.in_(warehouse_ids),
            InboundShipment.global_product_id.in_(product_ids),
            InboundShipment.confirmed.is_(True),
            InboundShipment.received.is_(False),
        )
        .order_by(InboundShipment.eta_date, InboundShipment.inbound_ref)
    )
    by_wh: dict[int, list[InboundCtx]] = defaultdict(list)
    for row in result.scalars():
        by_wh[row.warehouse_id].append(
            InboundCtx(row.global_product_id, row.qty, row.eta_date, row.inbound_ref)
        )
    return {w: tuple(items) for w, items in by_wh.items()}


async def route_info(
    session: AsyncSession, warehouse_ids: Sequence[int], to_lat: Decimal, to_lon: Decimal
) -> dict[int, RouteInfo | None]:
    """{kho: RouteInfo hoặc None} từ plan.route_matrix cho điểm giao (tọa độ numeric(8,5) khớp chính xác)."""
    result = await session.execute(
        select(RouteMatrix).where(
            RouteMatrix.warehouse_id.in_(warehouse_ids),
            RouteMatrix.to_lat == to_lat,
            RouteMatrix.to_lon == to_lon,
        )
    )
    found = {
        r.warehouse_id: RouteInfo(r.distance_km, r.duration_min, "ors" if r.provider == "ors" else "fallback")
        for r in result.scalars()
    }
    return {w: found.get(w) for w in warehouse_ids}
