"""Giờ nhân công thực tế cho AI (v1.2; 04 mục 6.3; FR-EXE-04; US-WH-04 AC6/AC7).

Kho bấm START_PREP (crew_size) → PREP_PAUSED → PREP_RESUMED (crew_size) → … → GOODS_READY. Mỗi đoạn làm
việc có (start, end, crew_size). actual_labour_hours = Σ crew_size × (end − start) giờ. Chia cho từng nhóm
N1–N6 theo tỷ lệ giờ kế hoạch, rồi chia số đơn vị cơ sở → giờ nhân công/đơn vị (không phụ thuộc số người).

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class LabourSegment:
    start: datetime
    end: datetime
    crew_size: int


@dataclass(frozen=True)
class GroupActual:
    group_code: str
    units: Decimal
    hours: Decimal
    hours_per_unit: Decimal


def actual_labour_hours(segments: list[LabourSegment]) -> Decimal:
    """Σ crew_size × độ dài đoạn (giờ). Đoạn có end ≤ start hoặc crew_size ≤ 0 → ValueError."""
    total = Decimal(0)
    for seg in segments:
        if seg.end <= seg.start or seg.crew_size <= 0:
            raise ValueError("invalid labour segment")
        hours = Decimal((seg.end - seg.start).total_seconds()) / Decimal(3600)
        total += hours * seg.crew_size
    return total


def allocate_to_groups(
    actual_hours: Decimal, planned_hours_by_group: dict[str, Decimal], base_units_by_group: dict[str, Decimal]
) -> tuple[GroupActual, ...]:
    """Chia giờ thực tế cho từng nhóm theo tỷ lệ giờ kế hoạch, rồi chia số đơn vị cơ sở của nhóm."""
    planned_total = sum(planned_hours_by_group.values(), Decimal(0))
    if planned_total <= 0:
        return ()
    result: list[GroupActual] = []
    for code in sorted(planned_hours_by_group):
        hours = actual_hours * planned_hours_by_group[code] / planned_total
        units = base_units_by_group.get(code, Decimal(0))
        per_unit = hours / units if units > 0 else Decimal(0)
        result.append(GroupActual(code, units, hours, per_unit))
    return tuple(result)
