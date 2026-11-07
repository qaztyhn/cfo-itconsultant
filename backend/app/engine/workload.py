"""Bước 1 — khối lượng việc, giống nhau mọi kho (04 mục 6.2; BR-PRP-01; US-PLN-01).

line_hours = (fixed_hours + prep_qty × labour_hours_per_unit) × min(Π cờ, flag_multiplier_cap);
prep_qty theo ĐƠN VỊ CƠ SỞ nhỏ nhất (v1.2): qty_base / base_units_per_prep_unit (20 bao / 40 = 0,5 pallet,
không làm tròn); hàng không chia nhỏ được (base_units_per_prep_unit None) → ceil(qty_base); 'line' → 1;
labour_hours = Σ line_hours + final_inspection_hours. KHÔNG tính giờ thiết bị (v1.1).
Ví dụ bắt buộc test: 20 pallet N3 + 15 pallet N2 + 3 dòng N1 = 10,15 h; cờ 1,25×1,30 = 1,625;
20 bao N3 = 0,325 h (US-PLN-01 AC4); hàng nguyên 2,4 → 3 (AC5).

Owner: Dev 1 (luồng A).
"""

from decimal import ROUND_CEILING, Decimal

from app.engine.types import EngineConfig, LineCtx, Workload


def prep_quantity(line: LineCtx) -> Decimal:
    """Số đơn vị chuẩn bị của một dòng, tính theo đơn vị cơ sở nhỏ nhất (v1.2)."""
    product = line.product
    if product.group.prep_unit == "line":
        return Decimal(1)
    if product.base_units_per_prep_unit is None:
        return line.qty_base.to_integral_value(rounding=ROUND_CEILING)
    return line.qty_base / product.base_units_per_prep_unit


def flag_multiplier(line: LineCtx, cap: Decimal) -> Decimal:
    """Tích hệ số cờ, kẹp tối đa `cap` (không cờ → 1)."""
    product = Decimal(1)
    for multiplier in line.product.flag_multipliers:
        product *= multiplier
    return min(product, cap)


def line_hours(line: LineCtx, cfg: EngineConfig) -> Decimal:
    """(fixed_hours + prep_qty × labour_hours_per_unit) × hệ số cờ — fixed_hours tính MỖI DÒNG."""
    group = line.product.group
    base = group.fixed_hours + prep_quantity(line) * group.labour_hours_per_unit
    return base * flag_multiplier(line, cfg.flag_multiplier_cap)


def compute_workload(lines: tuple[LineCtx, ...], cfg: EngineConfig) -> Workload:
    """Tổng giờ công của đơn (độc lập kho): Σ giờ dòng + final_inspection_hours. Không làm tròn ở engine."""
    per_line = tuple(line_hours(line, cfg) for line in lines)
    return Workload(labour_hours=sum(per_line, Decimal(0)) + cfg.final_inspection_hours, line_hours=per_line)


def warehouse_labour_hours(workload: Workload, efficiency: Decimal) -> Decimal:
    """Giờ công tại một kho = labour_hours × efficiency_factor (mặc định 1,0 — 09 bất biến 7)."""
    return workload.labour_hours * efficiency
