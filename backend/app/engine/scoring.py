"""Bước 4 — xếp hạng (04 mục 6.2; BR-RNK-01..03; US-PLN-06). KHÔNG quy tiền (09 bất biến 8).

n_km = minmax(distance_km) với vùng bỏ qua (max−min) < max(dz_km_abs, dz_km_pct × min);
n_fill = minmax(capacity_fill) với vùng bỏ qua < dz_fill; score = w_km·n_km + w_fill·n_fill.
Thứ tự (v1.2): vehicle_count tăng → score tăng; hòa (|Δ| < tie_eps): planning_reserve lớn hơn →
complexity thấp hơn → ETA sớm hơn → total_capacity_kg nhỏ hơn (xe nhỏ hơn mà vẫn đủ chứa) → mã xe nhỏ hơn.
Một ứng viên → 0. Top 3, tối đa 2 mỗi kho. Ví dụ bắt buộc test: 0,50 / 0,50 / 0,26.

Owner: Dev 1 (luồng A).
"""

from dataclasses import replace
from decimal import Decimal
from functools import cmp_to_key

from app.engine.types import EngineConfig, PlanCandidate, RankWeights

MAX_CANDIDATES = 3
MAX_PER_WAREHOUSE = 2


def minmax_normalise(values: list[Decimal], dead_zone: Decimal) -> list[Decimal]:
    """Chuẩn hóa min–max về [0,1]; chênh lệch < dead_zone → tất cả 0."""
    if not values:
        return []
    low, high = min(values), max(values)
    spread = high - low
    if spread < dead_zone or spread == 0:
        return [Decimal(0) for _ in values]
    return [(v - low) / spread for v in values]


def _total_m3(c: PlanCandidate) -> Decimal:
    return sum((v.capacity_m3 for v in c.vehicles), Decimal(0))


def _vehicle_codes(c: PlanCandidate) -> tuple[str, ...]:
    return tuple(sorted(v.vehicle_code for v in c.vehicles))


def _compare(a: PlanCandidate, b: PlanCandidate, eps: Decimal) -> int:
    """vehicle_count ↑ → score ↑ (hòa nếu |Δ| < eps) → reserve ↓ → complexity ↑ → ETA ↑ → tải ↑ → mã xe ↑."""
    keys: list[tuple[object, object]] = [(a.vehicle_count, b.vehicle_count)]
    if abs(a.score - b.score) >= eps:
        keys.append((a.score, b.score))
    keys += [
        (-a.planning_reserve_min, -b.planning_reserve_min),
        (a.complexity_points, b.complexity_points),
        (a.eta_at, b.eta_at),
        (a.total_capacity_kg, b.total_capacity_kg),
        (_total_m3(a), _total_m3(b)),
        (_vehicle_codes(a), _vehicle_codes(b)),
    ]
    for left, right in keys:
        if left != right:
            return -1 if left < right else 1  # type: ignore[operator]
    return 0


def score_candidates(
    cands: list[PlanCandidate], cfg: EngineConfig, weights: RankWeights | None = None
) -> list[PlanCandidate]:
    """Gán score = w_km·n_km + w_fill·n_fill trên toàn bộ ứng viên khả thi (một ứng viên → 0)."""
    if len(cands) <= 1:
        return [replace(c, score=Decimal(0)) for c in cands]
    w_km, w_fill = (weights.w_km, weights.w_fill) if weights else (cfg.w_km, cfg.w_fill)
    km = [c.distance_km for c in cands]
    n_km = minmax_normalise(km, max(cfg.dz_km_abs, cfg.dz_km_pct * min(km)))
    n_fill = minmax_normalise([c.capacity_fill for c in cands], cfg.dz_fill)
    return [replace(c, score=w_km * k + w_fill * f) for c, k, f in zip(cands, n_km, n_fill, strict=True)]


def rank_candidates(
    cands: list[PlanCandidate], cfg: EngineConfig, weights: RankWeights | None = None
) -> tuple[PlanCandidate, ...]:
    """Tính score, xếp hạng (ít xe trước), cắt top 3 (≤ 2 mỗi kho).

    Giờ công không là tiêu chí (09 bất biến 7).
    """

    def order(a: PlanCandidate, b: PlanCandidate) -> int:
        return _compare(a, b, cfg.tie_eps)

    scored = sorted(score_candidates(cands, cfg, weights), key=cmp_to_key(order))
    chosen: list[PlanCandidate] = []
    per_wh: dict[int, int] = {}
    for c in scored:
        if per_wh.get(c.warehouse_id, 0) >= MAX_PER_WAREHOUSE:
            continue
        per_wh[c.warehouse_id] = per_wh.get(c.warehouse_id, 0) + 1
        chosen.append(replace(c, rank=len(chosen) + 1))
        if len(chosen) == MAX_CANDIDATES:
            break
    return tuple(chosen)
