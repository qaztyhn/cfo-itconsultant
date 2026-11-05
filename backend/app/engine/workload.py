"""Bước 1 — khối lượng việc, giống nhau mọi kho (04 mục 6.2; BR-PRP-01; US-PLN-01).

line_hours = (fixed_hours + prep_qty × labour_hours_per_unit) × min(Π cờ, flag_multiplier_cap);
prep_qty = qty_base / base_units_per_prep_unit (prep_unit 'line' → 1);
labour_hours = Σ line_hours + final_inspection_hours. KHÔNG tính giờ thiết bị (v1.1).
Ví dụ bắt buộc test: 20 pallet N3 + 15 pallet N2 + 3 dòng N1 = 10,15 h; cờ 1,25×1,30 = 1,625.

Owner: Dev 1 (luồng A).
"""

from decimal import Decimal

from app.engine.types import EngineConfig, LineCtx, Workload


def prep_quantity(line: LineCtx) -> Decimal:
    """Số đơn vị chuẩn bị của một dòng. TODO(#M4-workload)."""
    raise NotImplementedError


def flag_multiplier(line: LineCtx, cap: Decimal) -> Decimal:
    """Tích hệ số cờ, kẹp tối đa `cap`. TODO(#M4-workload)."""
    raise NotImplementedError


def compute_workload(lines: tuple[LineCtx, ...], cfg: EngineConfig) -> Workload:
    """Tổng giờ công của đơn (độc lập kho). TODO(#M4-workload)."""
    raise NotImplementedError
