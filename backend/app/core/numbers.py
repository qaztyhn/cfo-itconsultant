"""Hàm làm tròn duy nhất (09 mục 5): Decimal cho giờ công/khối lượng, phút nguyên cho thời gian.

Owner: Dev 1 (luồng A).
"""

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal


def q3(value: Decimal) -> Decimal:
    """Làm tròn 3 chữ số thập phân (giờ công numeric(8,3))."""
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def ceil_to_minutes(ts: datetime, step_min: int) -> datetime:
    """Làm tròn LÊN tới bội số `step_min` phút (ETA làm tròn lên 15 phút, 04 mục 6.2e)."""
    if step_min <= 0:
        raise ValueError("step_min must be positive")
    base = ts.replace(second=0, microsecond=0)
    extra = 1 if (ts.second or ts.microsecond) else 0
    minutes = base.minute + extra
    rem = minutes % step_min
    add = (step_min - rem) % step_min
    return base + timedelta(minutes=extra + add)
