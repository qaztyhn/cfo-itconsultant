"""Bước 2a — time-phased ATP theo kho (04 mục 6.2; BR-ATP-01..04; US-ATP-01).

usable(w,p,d) = stock_available[p] + Σ inbound(confirmed, !received, eta + receiving_lead_days làm việc ≤ d).
stock_ready_date = ngày sớm nhất ≥ hôm nay mà mọi dòng đủ; không có trong search_days_max → STOCK_SHORT
và trả phần thiếu cho gợi ý chuyển kho. Dựa vào hàng nhập → complexity_points += 1.

Owner: Dev 1 (luồng A).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from app.engine.capacity import is_working_day
from app.engine.types import CheckResult, EngineConfig, InboundCtx, OrderCtx, WarehouseCtx


@dataclass(frozen=True)
class AtpResult:
    stock_ready_date: date | None
    classification: Literal["ready_now", "after_inbound", "short"]
    shortage: dict[int, Decimal]
    inbound_refs: tuple[str, ...]


def add_working_days(start: date, days: int, cfg: EngineConfig) -> date:
    """Ngày sau `days` ngày làm việc kể từ `start` (bỏ cuối tuần/ngày lễ của market)."""
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if is_working_day(current, cfg):
            remaining -= 1
    return current


def required_quantities(order: OrderCtx) -> dict[int, Decimal]:
    """Tổng qty_base theo sản phẩm global (nhiều dòng cùng sản phẩm được cộng)."""
    needed: dict[int, Decimal] = defaultdict(Decimal)
    for line in order.lines:
        needed[line.product.global_product_id] += line.qty_base
    return dict(needed)


def _usable_from(inbound: InboundCtx, cfg: EngineConfig) -> date:
    return add_working_days(inbound.eta_date, cfg.receiving_lead_days, cfg)


def check_atp(order: OrderCtx, wh: WarehouseCtx, cfg: EngineConfig) -> AtpResult:
    """ATP của một kho cho mọi dòng.

    `wh.stock_available` đã trừ wms_reserved và giữ chỗ của ĐƠN KHÁC; `wh.inbound` chỉ gồm hàng nhập
    confirmed, chưa received (service lọc — 09 bất biến 6). "Hôm nay" = ngày của `order.now`
    (service truyền giờ theo múi giờ market). Quét `search_days_max` ngày lịch kể từ hôm nay.
    """
    needed = required_quantities(order)
    today = order.now.date()
    stock = {p: wh.stock_available.get(p, Decimal(0)) for p in needed}
    if all(stock[p] >= q for p, q in needed.items()):
        return AtpResult(today, "ready_now", {}, ())

    short_products = {p for p, q in needed.items() if stock[p] < q}
    relevant = sorted(
        (i for i in wh.inbound if i.global_product_id in needed),
        key=lambda i: (_usable_from(i, cfg), i.inbound_ref),
    )
    horizon_end = today + timedelta(days=cfg.search_days_max - 1)
    usable = dict(stock)
    used_refs: list[str] = []
    for inbound in relevant:
        ready_on = max(_usable_from(inbound, cfg), today)
        if ready_on > horizon_end:
            break
        usable[inbound.global_product_id] += inbound.qty
        if inbound.global_product_id in short_products and inbound.inbound_ref not in used_refs:
            used_refs.append(inbound.inbound_ref)
        if all(usable[p] >= q for p, q in needed.items()):
            return AtpResult(ready_on, "after_inbound", {}, tuple(used_refs))
    shortage = {p: q - usable[p] for p, q in needed.items() if usable[p] < q}
    return AtpResult(None, "short", shortage, ())


def stock_check(atp: AtpResult) -> CheckResult:
    """Check `stock` của gate: STOCK_OK / STOCK_AFTER_INBOUND / STOCK_SHORT, luôn có detail.message."""
    if atp.classification == "ready_now":
        return CheckResult("stock", True, "STOCK_OK", {"message": "All lines available in stock."})
    if atp.classification == "after_inbound":
        return CheckResult(
            "stock",
            True,
            "STOCK_AFTER_INBOUND",
            {
                "message": f"Available from {atp.stock_ready_date} after confirmed inbound.",
                "stock_ready_date": str(atp.stock_ready_date),
                "inbound_refs": list(atp.inbound_refs),
            },
        )
    shortage = {str(p): str(q) for p, q in sorted(atp.shortage.items())}
    return CheckResult(
        "stock",
        False,
        "STOCK_SHORT",
        {"message": f"Short on {len(shortage)} product(s) within the search horizon.", "shortage": shortage},
    )
