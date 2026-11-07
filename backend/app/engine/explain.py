"""Bước 5 — giải thích bằng mẫu câu cố định, không AI (04 mục 6.2; 09 mục 8).

reason_codes của hạng 1: LOWEST_SCORE_OF_3 | LOWEST_SCORE_OF_2 | ONLY_FEASIBLE (+ STOCK_*, TRUCK_OK,
RESERVE_SAFE/RESERVE_TIGHT). Cấm chữ "cheapest/cost/SEK". Mỗi ứng viên bị loại có detail.message.

Owner: Dev 1 (luồng A).
"""

from decimal import Decimal

from app.engine.types import EngineConfig, PlanCandidate, RejectedCandidate

_LEAD = {
    "LOWEST_SCORE_OF_3": "Lowest score of 3 feasible options.",
    "LOWEST_SCORE_OF_2": "Lowest score of 2 feasible options.",
    "ONLY_FEASIBLE": "Only feasible option.",
}


def _lead_code(total_feasible: int) -> str:
    if total_feasible >= 3:
        return "LOWEST_SCORE_OF_3"
    return "LOWEST_SCORE_OF_2" if total_feasible == 2 else "ONLY_FEASIBLE"


def reserve_class(reserve_min: int, cfg: EngineConfig) -> str:
    """safe nếu ≥ reserve_safe_days × 1440 phút; tight nếu ≥ 0; ngược lại infeasible (04 mục 6.2 bước 2f)."""
    if reserve_min >= cfg.reserve_safe_days * 1440:
        return "safe"
    return "tight" if reserve_min >= 0 else "infeasible"


def reason_codes_for(c: PlanCandidate, total_feasible: int, cfg: EngineConfig) -> tuple[str, ...]:
    """Mã lý do: hạng 1 có LOWEST_SCORE_OF_3 | LOWEST_SCORE_OF_2 | ONLY_FEASIBLE, rồi STOCK_*, TRUCK_OK,
    RESERVE_SAFE/RESERVE_TIGHT. Không có mã "cheapest/cost" (09 bất biến 8)."""
    codes: list[str] = [_lead_code(total_feasible)] if c.rank == 1 else []
    codes += [ch.code for ch in c.checks if ch.name == "stock" and ch.passed]
    codes += [ch.code for ch in c.checks if ch.name == "truck" and ch.passed]
    cls = reserve_class(c.planning_reserve_min, cfg)
    if cls in ("safe", "tight"):
        codes.append(f"RESERVE_{cls.upper()}")
    return tuple(codes)


def _reserve_text(minutes: int) -> str:
    days, rest = divmod(max(minutes, 0), 1440)
    return f"{days} d {rest // 60} h"


def explanation_for(c: PlanCandidate, total_feasible: int, warehouse_name: str, cfg: EngineConfig) -> str:
    """Câu giải thích tiếng Anh từ mẫu cố định (không AI, không chữ chỉ tiền)."""
    lead = (
        _LEAD[_lead_code(total_feasible)] if c.rank == 1 else f"Option {c.rank} of {total_feasible} feasible."
    )
    stock = next((ch for ch in c.checks if ch.name == "stock"), None)
    stock_text = (
        f"stock from {stock.detail.get('stock_ready_date')} after inbound"
        if stock is not None and stock.code == "STOCK_AFTER_INBOUND"
        else "stock available"
    )
    fill = (c.capacity_fill * 100).quantize(Decimal(1))
    vehicles = ", ".join(v.vehicle_code for v in c.vehicles)
    return (
        f"{lead} Warehouse {warehouse_name}: {stock_text}, capacity fill {fill}%, "
        f"{c.vehicle_count} vehicle(s) ({vehicles}), delivery {c.distance_km.normalize():f} km, "
        f"planning reserve {_reserve_text(c.planning_reserve_min)} "
        f"({reserve_class(c.planning_reserve_min, cfg)})."
    )


def rejection_message(r: RejectedCandidate) -> str:
    """Câu giải thích cho ứng viên bị loại (03 mục 5.2): mã + detail.message có số."""
    who = f"warehouse {r.warehouse_id}" + (f", vehicle {r.vehicle_code}" if r.vehicle_code else "")
    return f"{r.failed_check} · {r.code} ({who}): {r.detail.get('message', '')}".rstrip()
