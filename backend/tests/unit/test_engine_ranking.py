"""Bước 3 (gate), 4 (xếp hạng), 5 (giải thích) — 04 mục 6.2; US-PLN-06, US-PLN-07 AC1; 08 mục 6.2."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.explain import explanation_for, reason_codes_for, rejection_message
from app.engine.gate import all_passed, furthest_failed_check
from app.engine.scoring import minmax_normalise, rank_candidates
from app.engine.types import CheckResult, PlanCandidate, RankWeights, RejectedCandidate, VehicleAssignment
from tests.unit.engine_factory import CFG

T = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
OK = (
    CheckResult("stock", True, "STOCK_OK", {"message": "ok"}),
    CheckResult("preparation", True, "PREP_OK", {"message": "ok"}),
    CheckResult("truck", True, "TRUCK_OK", {"message": "ok"}),
    CheckResult("site_date", True, "DATE_OK", {"message": "ok"}),
    CheckResult("safety", True, "SAFETY_OK", {"message": "ok"}),
)


def _veh(code: str, kg: str = "6000", m3: str = "40") -> VehicleAssignment:
    return VehicleAssignment(
        1, 1, code, Decimal(kg), Decimal(m3), 1, Decimal(1), Decimal(1), ((1, Decimal(1)),), T, T, T, T
    )


def cand(
    wh: int, km: str, fill: str, *, vehicles: tuple[VehicleAssignment, ...] | None = None,
    reserve: int = 3000, complexity: int = 0, eta: datetime = T,
) -> PlanCandidate:  # fmt: skip
    return PlanCandidate(
        warehouse_id=wh, vehicles=vehicles or (_veh(f"W{wh}-12-01"),), target_date=date(2026, 11, 12),
        goods_ready_at=T, loading_start_at=T, depart_at=T, eta_at=eta, trip_end_at=T, distance_km=Decimal(km),
        drive_min=30, prep_hours=Decimal(12), capacity_fill=Decimal(fill), complexity_points=complexity,
        planning_reserve_min=reserve, route_provenance="ors", checks=OK, prep_by_day={},
    )  # fmt: skip


# --- gate --------------------------------------------------------------------------------------------


def test_all_passed_requires_five_passing_checks() -> None:
    assert all_passed(OK)
    assert not all_passed(OK[:4])
    assert not all_passed((*OK[:4], CheckResult("safety", False, "OVER_LOAD", {"message": "x"})))


def test_US_PLN_07_furthest_failed_check_across_warehouses() -> None:
    stock_fail = (CheckResult("stock", False, "STOCK_SHORT", {}),)
    truck_fail = (*OK[:2], CheckResult("truck", False, "NO_TRUCK_FIT", {}))
    assert furthest_failed_check([stock_fail, truck_fail, stock_fail]) == "truck"
    assert furthest_failed_check([stock_fail, stock_fail]) == "stock"
    assert furthest_failed_check([]) is None
    assert furthest_failed_check([OK]) is None


# --- scoring -----------------------------------------------------------------------------------------


def test_minmax_normalise_and_dead_zone() -> None:
    assert minmax_normalise([Decimal(10), Decimal(40), Decimal(25)], Decimal(2)) == [
        Decimal(0),
        Decimal(1),
        Decimal("0.5"),
    ]
    assert minmax_normalise([Decimal(10), Decimal(11)], Decimal(2)) == [Decimal(0), Decimal(0)]


def test_US_PLN_06_AC1_example_scores_050_050_026_malmo_first() -> None:
    a, b, c = cand(1, "10", "0.85"), cand(2, "40", "0.40"), cand(3, "12", "0.60")
    ranked = rank_candidates([a, b, c], CFG)
    assert [r.warehouse_id for r in ranked][0] == 3
    scores = {r.warehouse_id: r.score.quantize(Decimal("0.01")) for r in ranked}
    assert scores == {1: Decimal("0.50"), 2: Decimal("0.50"), 3: Decimal("0.26")}
    assert [r.rank for r in ranked] == [1, 2, 3]


def test_US_PLN_06_AC2_km_within_2km_dead_zone_all_zero() -> None:
    ranked = rank_candidates([cand(1, "10", "0.50"), cand(2, "11", "0.90")], CFG)
    by_wh = {r.warehouse_id: r.score for r in ranked}
    assert by_wh == {1: Decimal(0), 2: Decimal("0.5")}  # chỉ n_fill tạo khác biệt


def test_fill_dead_zone_under_005() -> None:
    ranked = rank_candidates([cand(1, "10", "0.50"), cand(2, "40", "0.53")], CFG)
    assert {r.warehouse_id: r.score for r in ranked} == {1: Decimal(0), 2: Decimal("0.5")}


def test_US_PLN_06_AC3_single_candidate_score_zero() -> None:
    (only,) = rank_candidates([cand(1, "40", "0.9")], CFG)
    assert only.score == 0 and only.rank == 1


def test_US_PLN_06_AC4_multi_level_tie_break() -> None:
    base = dict(km="10", fill="0.5")
    # cùng điểm 0 (vùng bỏ qua) → reserve lớn hơn thắng
    r = rank_candidates([cand(1, **base, reserve=1000), cand(2, **base, reserve=2000)], CFG)  # type: ignore[arg-type]
    assert r[0].warehouse_id == 2
    # cùng reserve → complexity thấp hơn
    r = rank_candidates([cand(1, **base, complexity=1), cand(2, **base, complexity=0)], CFG)  # type: ignore[arg-type]
    assert r[0].warehouse_id == 2
    # cùng complexity → ETA sớm hơn
    r = rank_candidates([cand(1, **base, eta=T + timedelta(hours=1)), cand(2, **base, eta=T)], CFG)  # type: ignore[arg-type]
    assert r[0].warehouse_id == 2
    # cùng ETA → tổng tải xe nhỏ hơn (xe nhỏ hơn vẫn đủ chứa)
    big, small = (_veh("W1-18-01", "9000"),), (_veh("W2-12-01", "6000"),)
    r = rank_candidates([cand(1, **base, vehicles=big), cand(2, **base, vehicles=small)], CFG)  # type: ignore[arg-type]
    assert r[0].warehouse_id == 2
    # cùng tải → mã xe nhỏ hơn (kết quả luôn xác định)
    r = rank_candidates(
        [cand(1, **base, vehicles=(_veh("ZZ-12-01"),)), cand(2, **base, vehicles=(_veh("AA-12-01"),))], CFG  # type: ignore[arg-type]
    )
    assert r[0].warehouse_id == 2


def test_US_PLN_06_AC7_one_vehicle_before_two_regardless_of_score() -> None:
    two = cand(1, "10", "0.10", vehicles=(_veh("A-1"), _veh("A-2")))
    one = cand(2, "90", "0.95")
    ranked = rank_candidates([two, one], CFG)
    assert [r.warehouse_id for r in ranked] == [2, 1]


def test_US_PLN_06_AC5_top3_and_at_most_two_per_warehouse() -> None:
    cands = [cand(1, "10", "0.5"), cand(1, "11", "0.5"), cand(1, "12", "0.5"), cand(2, "50", "0.5")]
    ranked = rank_candidates(cands, CFG)
    assert len(ranked) == 3 and sum(r.warehouse_id == 1 for r in ranked) == 2


def test_US_PLN_08_AC2_custom_weights_change_score() -> None:
    a, b, c = cand(1, "10", "0.85"), cand(2, "40", "0.40"), cand(3, "12", "0.60")
    ranked = rank_candidates([a, b, c], CFG, RankWeights(Decimal("0.8"), Decimal("0.2")))
    scores = {r.warehouse_id: r.score.quantize(Decimal("0.01")) for r in ranked}
    assert scores == {1: Decimal("0.20"), 2: Decimal("0.80"), 3: Decimal("0.14")}


def test_US_PLN_06_AC6_labour_hours_not_a_ranking_criterion() -> None:
    a, b = cand(1, "10", "0.5"), replace(cand(2, "10", "0.5"), prep_hours=Decimal(99))
    assert {r.score for r in rank_candidates([a, b], CFG)} == {Decimal(0)}


# --- explain -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "code"), [(3, "LOWEST_SCORE_OF_3"), (2, "LOWEST_SCORE_OF_2"), (1, "ONLY_FEASIBLE")]
)
def test_US_PLN_06_AC5_rank1_reason_codes(total: int, code: str) -> None:
    c = replace(cand(3, "12", "0.60", reserve=3 * 1440), rank=1)
    codes = reason_codes_for(c, total, CFG)
    assert codes[0] == code and "STOCK_OK" in codes and "TRUCK_OK" in codes and "RESERVE_SAFE" in codes


def test_reason_codes_tight_reserve_and_after_inbound() -> None:
    checks = (CheckResult("stock", True, "STOCK_AFTER_INBOUND", {"message": "m"}), *OK[1:])
    c = replace(cand(1, "10", "0.5", reserve=600), rank=2, checks=checks)
    codes = reason_codes_for(c, 3, CFG)
    assert "LOWEST_SCORE_OF_3" not in codes and "STOCK_AFTER_INBOUND" in codes and "RESERVE_TIGHT" in codes


def test_explanation_from_fixed_template_without_cost_words() -> None:
    c = replace(cand(3, "12", "0.60", reserve=3 * 1440), rank=1)
    text = explanation_for(c, 3, "Malmö DC", CFG)
    assert text.startswith("Lowest score of 3 feasible options.")
    assert "Malmö DC" in text and "60%" in text and "12 km" in text and "3 d" in text and "safe" in text
    for forbidden in ("cheap", "cost", "SEK", "price"):
        assert forbidden.lower() not in text.lower()


def test_rejection_message_contains_code_and_detail() -> None:
    r = RejectedCandidate(2, "GBG-03-02", "truck", "NO_TRUCK_FIT", {"message": "Needs capability crane."})
    msg = rejection_message(r)
    assert "NO_TRUCK_FIT" in msg and "crane" in msg and "GBG-03-02" in msg
