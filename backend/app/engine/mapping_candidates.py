"""Ứng viên ánh xạ SKU bằng quy tắc, không AI (04 mục 6.5; FR-PRD-03; US-PRD-01).

(1) GTIN trùng → reason 'gtin'; (2) tương đồng tên ≥ 0,45 cùng category → 'name_sim' kèm score
(điểm tương đồng được service tính bằng pg_trgm rồi truyền vào); (3) gợi ý nhóm theo
handling_group_rule (category_like, khoảng khối lượng, priority thấp trước). Chỉ IT xác nhận.

Owner: Dev 1 (luồng A).
"""

import re
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
    """Gộp và sắp ứng viên: GTIN trùng trước (score 1), rồi `name_sim` ≥ threshold theo điểm giảm dần.

    `name_similarity` đã lọc cùng category ở service (pg_trgm). Một sản phẩm chỉ xuất hiện một lần.
    """
    result: list[MappingCandidate] = []
    seen: set[int] = set()
    if local_gtin:
        for gid in sorted(set(gtin_matches)):
            result.append(MappingCandidate(gid, "gtin", Decimal(1)))
            seen.add(gid)
    similar = sorted(
        ((gid, score) for gid, score in name_similarity if score >= threshold and gid not in seen),
        key=lambda item: (-item[1], item[0]),
    )
    for gid, score in similar:
        if gid not in seen:
            result.append(MappingCandidate(gid, "name_sim", score))
            seen.add(gid)
    return tuple(result)


def _like(pattern: str, value: str) -> bool:
    """So khớp kiểu SQL LIKE (phân biệt hoa thường như PostgreSQL): % = chuỗi bất kỳ, _ = một ký tự."""
    regex = "".join(".*" if ch == "%" else "." if ch == "_" else re.escape(ch) for ch in pattern)
    return re.fullmatch(regex, value, flags=re.DOTALL) is not None


def suggest_group(
    category: str, weight_kg: Decimal, rules: list[tuple[int, str, Decimal | None, Decimal | None, str]]
) -> str | None:
    """Trả mã nhóm N1–N6 theo quy tắc đầu tiên khớp (rules đã sắp theo priority tăng).

    rule = (priority, category_like, min_weight_kg, max_weight_kg, group_code);
    khoảng khối lượng bao gồm hai đầu.
    """
    for _priority, category_like, min_kg, max_kg, group_code in rules:
        if not _like(category_like, category):
            continue
        if min_kg is not None and weight_kg < min_kg:
            continue
        if max_kg is not None and weight_kg > max_kg:
            continue
        return group_code
    return None
