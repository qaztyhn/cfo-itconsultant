"""Bước 4 — xếp hạng (04 mục 6.2; BR-RNK-01..03; US-PLN-06). KHÔNG quy tiền (09 bất biến 8).

n_km = minmax(distance_km) với vùng bỏ qua (max−min) < max(dz_km_abs, dz_km_pct × min);
n_fill = minmax(capacity_fill) với vùng bỏ qua < dz_fill; score = w_km·n_km + w_fill·n_fill.
Thứ tự (v1.2): vehicle_count tăng → score tăng; hòa (|Δ| < tie_eps): planning_reserve lớn hơn →
complexity thấp hơn → ETA sớm hơn → total_capacity_kg nhỏ hơn (xe nhỏ hơn mà vẫn đủ chứa) → mã xe nhỏ hơn.
Một ứng viên → 0. Top 3, tối đa 2 mỗi kho. Ví dụ bắt buộc test: 0,50 / 0,50 / 0,26.

Owner: Dev 1 (luồng A).
"""

from decimal import Decimal

from app.engine.types import EngineConfig, PlanCandidate, RankWeights


def minmax_normalise(values: list[Decimal], dead_zone: Decimal) -> list[Decimal]:
    """Chuẩn hóa min–max về [0,1]; chênh lệch < dead_zone → tất cả 0. TODO(#M4-scoring)."""
    raise NotImplementedError


def rank_candidates(
    cands: list[PlanCandidate], cfg: EngineConfig, weights: RankWeights | None = None
) -> tuple[PlanCandidate, ...]:
    """Tính score, xếp hạng, cắt top 3 (≤ 2 mỗi kho). TODO(#M4-scoring)."""
    raise NotImplementedError
