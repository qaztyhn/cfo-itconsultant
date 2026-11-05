"""Ứng viên ánh xạ SKU bằng quy tắc, không AI (04 mục 6.5; FR-PRD-03; US-PRD-01).

(1) GTIN trùng → reason 'gtin'; (2) tương đồng tên ≥ 0,45 cùng category → 'name_sim' kèm score
(điểm tương đồng được service tính bằng pg_trgm rồi truyền vào); (3) gợi ý nhóm theo
handling_group_rule (category_like, khoảng khối lượng, priority thấp trước). Chỉ IT xác nhận.

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class MappingCandidate:
    global_product_id: int
    reason: str
    score: Decimal


def build_candidates(
    local_gtin: str | None,
    gtin_matches: list[int],
    name_similarity: list[tuple[int, Decimal]],
    threshold: Decimal,
) -> tuple[MappingCandidate, ...]:
    """Gộp và sắp ứng viên. TODO(#M2-mapping)."""
    raise NotImplementedError


def suggest_group(
    category: str, weight_kg: Decimal, rules: list[tuple[int, str, Decimal | None, Decimal | None, str]]
) -> str | None:
    """Trả mã nhóm N1–N6 theo quy tắc đầu tiên khớp (rules đã sắp theo priority). TODO(#M2-mapping)."""
    raise NotImplementedError
