"""Gợi ý chuyển kho (04 mục 6.4; US-ATP-02) và ứng viên ánh xạ SKU (04 mục 6.5; US-PRD-01 AC3/AC4)."""

from datetime import time
from decimal import Decimal

import pytest

from app.engine.mapping_candidates import MappingCandidate, build_candidates, suggest_group
from app.engine.transfer import suggest_transfers
from app.engine.types import WarehouseCtx


def _wh(wid: int, stock: dict[int, str]) -> WarehouseCtx:
    return WarehouseCtx(
        wid, f"WH{wid}", time(15), Decimal(1), {p: Decimal(q) for p, q in stock.items()}, (), {}, (), (), None
    )


TARGET = _wh(1, {7: "0"})
SHORT = {7: Decimal(40)}


def test_US_ATP_02_AC1_only_sources_with_enough_available_stock() -> None:
    a, b = _wh(2, {7: "20"}), _wh(3, {7: "100"})
    res = suggest_transfers(TARGET, SHORT, [a, b], {}, {(2, 1): Decimal(5), (3, 1): Decimal(300)}, 1)
    assert [(s.from_warehouse_id, s.to_warehouse_id, s.lead_days, s.distance_km) for s in res] == [
        (3, 1, 1, Decimal(300))
    ]
    assert res[0].lines == ((7, Decimal(40)),)


def test_US_ATP_02_AC2_sorted_by_lead_days_then_distance_max_three() -> None:
    sources = [_wh(i, {7: "100"}) for i in range(2, 7)]
    lead = {(2, 1): 2, (3, 1): 1, (4, 1): 1, (5, 1): 1, (6, 1): 3}
    dist = {
        (2, 1): Decimal(10),
        (3, 1): Decimal(400),
        (4, 1): Decimal(50),
        (5, 1): Decimal(200),
        (6, 1): Decimal(1),
    }
    res = suggest_transfers(TARGET, SHORT, sources, lead, dist, 1)
    assert [s.from_warehouse_id for s in res] == [4, 5, 3]


def test_source_must_cover_every_short_product_and_target_excluded() -> None:
    shortage = {7: Decimal(40), 8: Decimal(5)}
    partial, full = _wh(2, {7: "100"}), _wh(3, {7: "40", 8: "5"})
    res = suggest_transfers(
        TARGET, shortage, [TARGET, partial, full], {}, {(3, 1): Decimal(1), (2, 1): Decimal(1)}, 1
    )
    assert [s.from_warehouse_id for s in res] == [3]


def test_default_lead_days_and_missing_distance_rejected() -> None:
    res = suggest_transfers(TARGET, SHORT, [_wh(2, {7: "40"})], {}, {(2, 1): Decimal(9)}, 2)
    assert res[0].lead_days == 2
    with pytest.raises(ValueError):
        suggest_transfers(TARGET, SHORT, [_wh(2, {7: "40"})], {}, {}, 1)


def test_no_shortage_no_suggestion() -> None:
    assert suggest_transfers(TARGET, {}, [_wh(2, {7: "40"})], {}, {(2, 1): Decimal(1)}, 1) == ()


# --- mapping candidates ------------------------------------------------------------------------------


def test_US_PRD_01_AC3_gtin_match_is_strongest_candidate() -> None:
    res = build_candidates(
        "7310000000123", [123], [(55, Decimal("0.9")), (123, Decimal("0.7"))], Decimal("0.45")
    )
    assert res[0] == MappingCandidate(123, "gtin", Decimal(1))
    assert [(c.global_product_id, c.reason) for c in res] == [(123, "gtin"), (55, "name_sim")]


def test_US_PRD_01_AC4_name_similarity_at_or_above_threshold_with_score() -> None:
    res = build_candidates(
        None, [], [(1, Decimal("0.60")), (2, Decimal("0.45")), (3, Decimal("0.44"))], Decimal("0.45")
    )
    assert res == (
        MappingCandidate(1, "name_sim", Decimal("0.60")),
        MappingCandidate(2, "name_sim", Decimal("0.45")),
    )


def test_gtin_matches_ignored_without_local_gtin() -> None:
    assert build_candidates(None, [9], [], Decimal("0.45")) == ()


RULES = [
    (10, "Cement%", None, None, "N3"),
    (20, "Timber%", Decimal(0), Decimal(50), "N2"),
    (30, "Timber%", Decimal(50), None, "N5"),
    (100, "%", None, None, "N1"),
]


@pytest.mark.parametrize(
    ("category", "weight", "group"),
    [
        ("Cement & mortar", "25", "N3"),
        ("Timber C24", "12", "N2"),
        ("Timber C24", "80", "N5"),
        ("Paint", "10", "N1"),
    ],
)
def test_suggest_group_first_matching_rule_by_priority(category: str, weight: str, group: str) -> None:
    assert suggest_group(category, Decimal(weight), RULES) == group


def test_suggest_group_none_when_no_rule_matches() -> None:
    assert suggest_group("Glass", Decimal(1), RULES[:3]) is None
    assert (
        suggest_group("cement bag", Decimal(1), RULES[:1]) is None
    )  # LIKE phân biệt hoa thường như PostgreSQL
