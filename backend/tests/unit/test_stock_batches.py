"""CFO stock normalization: fixed unit, pre-defined scope, verified independence, all-or-nothing.

DEC-SRC-Q10-SKU-001, DEC-CFO-STOCK-SCOPE-001 (B), DEC-CFO-STOCK-INDEPENDENCE-001 (A).
"""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.adapters.base import StockItemDTO, StockSnapshotDTO
from app.adapters.stock_batches import (
    DeclaredUnit,
    StockMapping,
    StockNormalizationError,
    normalize_stock,
    stored_quantity,
)

AS_OF = datetime(2026, 11, 8, 9, tzinfo=UTC)


def snap(*items: StockItemDTO, batch_id: int = 17, as_of: datetime = AS_OF) -> StockSnapshotDTO:
    return StockSnapshotDTO(as_of, tuple(items), batch_id, len(items))


def row(warehouse: str, sku: str, on_hand: str, reserved: str = "0") -> StockItemDTO:
    return StockItemDTO(warehouse, sku, Decimal(on_hand), Decimal(reserved))


MAPPINGS = {
    "CEM-25": StockMapping(1, "bag", Decimal("1"), True),
    "CEM-PAL": StockMapping(2, "pallet", Decimal("40"), True),
    "TILE": StockMapping(3, "box", Decimal("0.5"), True),
}
DECLARED = {sku: DeclaredUnit(m.sale_unit, m.units_to_base) for sku, m in MAPPINGS.items()}
ALL = frozenset({*MAPPINGS, "CEM-25-ALT"})


def run(
    snapshot: StockSnapshotDTO,
    *,
    scope: frozenset[str] = ALL,
    independent: tuple[frozenset[str], ...] = (),
    mappings: dict[str, StockMapping] | None = None,
    declared: dict[str, DeclaredUnit] | None = None,
) -> list[tuple[str, int, tuple[str, ...], Decimal, Decimal]]:
    result = normalize_stock(
        snapshot,
        MAPPINGS if mappings is None else mappings,
        DECLARED if declared is None else declared,
        scope=scope,
        verified_independent=independent,
    )
    return [(r.warehouse_code, r.global_product_id, r.source_skus, r.on_hand, r.reserved) for r in result]


# ---- fixed unit, one conversion per SKU --------------------------------------------------------------------


def test_each_sku_is_converted_once_per_warehouse() -> None:
    result = run(
        snap(row("GBG", "CEM-PAL", "5", "1"), row("GBG", "CEM-25", "100", "10"), row("STO", "TILE", "7"))
    )
    assert result == [
        ("GBG", 1, ("CEM-25",), Decimal("100"), Decimal("10")),
        ("GBG", 2, ("CEM-PAL",), Decimal("200"), Decimal("40")),  # 5 pallets x 40 bags, converted once
        ("STO", 3, ("TILE",), Decimal("3.5"), Decimal("0")),
    ]


def test_equal_converted_quantities_never_imply_shared_stock_or_get_merged() -> None:
    rows = run(snap(row("GBG", "CEM-25", "100"), row("GBG", "CEM-PAL", "2.5")))
    assert [(r[1], r[3]) for r in rows] == [(1, Decimal("100")), (2, Decimal("100.0"))]  # two products


def test_same_sku_in_two_warehouses_stays_separate() -> None:
    rows = run(snap(row("GBG", "CEM-25", "100"), row("STO", "CEM-25", "200")))
    assert [(r[0], r[3]) for r in rows] == [("GBG", Decimal(100)), ("STO", Decimal(200))]


def test_complete_empty_batch_is_an_authoritative_empty_result() -> None:
    assert run(snap()) == []


@pytest.mark.parametrize(
    "broken",
    [
        lambda s: replace(s, batch_id=None),
        lambda s: replace(s, batch_id=0),
        lambda s: replace(s, batch_id=True),  # bool is not a batch id
        lambda s: replace(s, item_count=None),
        lambda s: replace(s, item_count=2),
        lambda s: replace(s, as_of=datetime(2026, 11, 8, 9)),  # noqa: DTZ001 - naive on purpose
    ],
)
def test_batch_must_be_authoritative_and_complete(broken: object) -> None:
    with pytest.raises(StockNormalizationError, match="authoritative"):
        run(broken(snap(row("GBG", "CEM-25", "1"))))  # type: ignore[operator]


def test_duplicate_source_key_is_a_malformed_batch_even_outside_the_scope() -> None:
    with pytest.raises(StockNormalizationError, match="duplicated"):
        run(snap(row("GBG", "TILE", "1"), row("GBG", "TILE", "2")), scope=frozenset({"CEM-25"}))


# ---- DEC-CFO-STOCK-SCOPE-001: pre-defined SKU scope --------------------------------------------------------


def test_rows_outside_the_scope_are_ignored_and_never_block() -> None:
    items = snap(row("GBG", "CEM-25", "100"), row("GBG", "TILE", "999999999999"), row("GBG", "UNKNOWN", "1"))
    # TILE is mapped but bad quantity-wise, UNKNOWN has no mapping at all: neither is in the pilot scope.
    assert run(items, scope=frozenset({"CEM-25"})) == [("GBG", 1, ("CEM-25",), Decimal(100), Decimal(0))]


@pytest.mark.parametrize(
    ("mappings", "declared", "message"),
    [
        ({}, DECLARED, "no confirmed mapping"),
        ({"CEM-25": replace(MAPPINGS["CEM-25"], confirmed=False)}, DECLARED, "no confirmed mapping"),
        (MAPPINGS, {}, "no declared source unit"),
        (MAPPINGS, {**DECLARED, "CEM-25": DeclaredUnit("pallet", Decimal(1))}, "differs"),  # unit changed
        (MAPPINGS, {**DECLARED, "CEM-25": DeclaredUnit("bag", Decimal(2))}, "differs"),  # factor changed
        (
            {"CEM-25": replace(MAPPINGS["CEM-25"], units_to_base=Decimal(0))},
            {"CEM-25": DeclaredUnit("bag", Decimal(0))},
            "factor",
        ),
        ({"CEM-25": replace(MAPPINGS["CEM-25"], units_to_base=Decimal("NaN"))}, DECLARED, "factor"),
        ({"CEM-25": replace(MAPPINGS["CEM-25"], global_product_id=0)}, DECLARED, "differs"),
    ],
)
def test_one_unresolved_in_scope_sku_rejects_the_whole_batch(
    mappings: dict[str, StockMapping], declared: dict[str, DeclaredUnit], message: str
) -> None:
    with pytest.raises(StockNormalizationError, match=message):
        run(snap(row("GBG", "CEM-25", "1")), mappings=mappings, declared=declared)


def test_a_bad_in_scope_row_never_yields_a_partial_result() -> None:
    mappings = {k: v for k, v in MAPPINGS.items() if k != "TILE"}  # TILE is in scope but unmapped
    with pytest.raises(StockNormalizationError, match="no confirmed mapping"):
        run(snap(row("GBG", "CEM-25", "1"), row("GBG", "TILE", "1")), mappings=mappings)


def test_the_scope_is_never_derived_from_the_batch_so_an_empty_scope_returns_nothing() -> None:
    assert run(snap(row("GBG", "CEM-25", "1"), row("GBG", "TILE", "1")), scope=frozenset()) == []
    with pytest.raises(StockNormalizationError, match="empty SKU"):
        run(snap(row("GBG", "CEM-25", "1")), scope=frozenset({" "}))


# ---- DEC-CFO-STOCK-INDEPENDENCE-001: aggregate only verified independent inventory -------------------------

ALT = StockMapping(1, "bag", Decimal("1"), True)  # a second local SKU of the same global product (id 1)
MAPPINGS_ALT = {**MAPPINGS, "CEM-25-ALT": ALT}
DECLARED_ALT = {**DECLARED, "CEM-25-ALT": DeclaredUnit("bag", Decimal("1"))}


def two_skus(**kw: object) -> list[tuple[str, int, tuple[str, ...], Decimal, Decimal]]:
    items = snap(row("GBG", "CEM-25", "100", "10"), row("GBG", "CEM-25-ALT", "100", "5"))
    return run(items, mappings=MAPPINGS_ALT, declared=DECLARED_ALT, **kw)  # type: ignore[arg-type]


def test_several_skus_of_one_global_product_are_rejected_unless_independence_is_verified() -> None:
    with pytest.raises(StockNormalizationError, match="verified independence"):
        two_skus()  # default: nothing verified -> fail closed, never summed, never max, never last-row-wins


def test_verified_independent_skus_are_summed_after_conversion() -> None:
    verified = (frozenset({"CEM-25", "CEM-25-ALT"}),)
    # equal quantities are summed because independence was verified, not because they are equal
    assert two_skus(independent=verified) == [("GBG", 1, ("CEM-25", "CEM-25-ALT"), Decimal(200), Decimal(15))]


def test_conversion_happens_once_per_sku_before_summing() -> None:
    mappings = {**MAPPINGS_ALT, "CEM-25-ALT": StockMapping(1, "pallet", Decimal("40"), True)}
    declared = {**DECLARED_ALT, "CEM-25-ALT": DeclaredUnit("pallet", Decimal("40"))}
    items = snap(row("GBG", "CEM-25", "100"), row("GBG", "CEM-25-ALT", "2"))
    [result] = run(
        items, mappings=mappings, declared=declared, independent=(frozenset({"CEM-25", "CEM-25-ALT"}),)
    )
    assert result[3] == Decimal(180)  # 100 bags + 2 pallets x 40 bags


@pytest.mark.parametrize(
    "independent",
    [
        (frozenset({"CEM-25"}),),  # only one of the two is vouched for
        (frozenset({"CEM-25"}), frozenset({"CEM-25-ALT"})),  # independence is not transitive/by union
        (frozenset({"CEM-25-ALT", "TILE"}),),
    ],
)
def test_partially_verified_groups_do_not_authorise_the_sum(independent: tuple[frozenset[str], ...]) -> None:
    with pytest.raises(StockNormalizationError, match="verified independence"):
        two_skus(independent=independent)


def test_a_third_unverified_sku_blocks_the_whole_group() -> None:
    mappings = {**MAPPINGS_ALT, "CEM-25-B": StockMapping(1, "bag", Decimal("1"), True)}
    declared = {**DECLARED_ALT, "CEM-25-B": DeclaredUnit("bag", Decimal("1"))}
    items = snap(row("GBG", "CEM-25", "1"), row("GBG", "CEM-25-ALT", "1"), row("GBG", "CEM-25-B", "1"))
    with pytest.raises(StockNormalizationError, match="verified independence"):
        run(
            items, mappings=mappings, declared=declared,
            scope=frozenset({"CEM-25", "CEM-25-ALT", "CEM-25-B"}),
            independent=(frozenset({"CEM-25", "CEM-25-ALT"}),),
        )  # fmt: skip


def test_an_out_of_scope_sibling_sku_is_not_part_of_the_group() -> None:
    items = snap(row("GBG", "CEM-25", "100"), row("GBG", "CEM-25-ALT", "100"))
    assert run(items, mappings=MAPPINGS_ALT, declared=DECLARED_ALT, scope=frozenset({"CEM-25"})) == [
        ("GBG", 1, ("CEM-25",), Decimal(100), Decimal(0))
    ]


def test_verified_skus_in_different_warehouses_are_never_merged() -> None:
    items = snap(row("GBG", "CEM-25", "100"), row("STO", "CEM-25-ALT", "100"))
    rows = run(
        items,
        mappings=MAPPINGS_ALT,
        declared=DECLARED_ALT,
        independent=(frozenset({"CEM-25", "CEM-25-ALT"}),),
    )
    assert [(r[0], r[3]) for r in rows] == [("GBG", Decimal(100)), ("STO", Decimal(100))]


def test_a_sum_that_the_database_would_round_or_overflow_is_refused() -> None:
    mappings = {**MAPPINGS_ALT}
    items = snap(row("GBG", "CEM-25", "999999999"), row("GBG", "CEM-25-ALT", "1"))
    with pytest.raises(StockNormalizationError, match="exactly"):
        run(
            items,
            mappings=mappings,
            declared=DECLARED_ALT,
            independent=(frozenset({"CEM-25", "CEM-25-ALT"}),),
        )


# ---- exact quantities --------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "0.0004", "1000000000", "1.0001"])
def test_quantities_the_database_would_round_or_reject_are_refused(value: str) -> None:
    with pytest.raises(StockNormalizationError):
        stored_quantity(Decimal(value))


def test_conversion_that_is_not_exact_in_numeric_12_3_is_refused() -> None:
    mappings = {"X": StockMapping(9, "bag", Decimal("0.0003"), True)}
    declared = {"X": DeclaredUnit("bag", Decimal("0.0003"))}
    with pytest.raises(StockNormalizationError, match="exactly"):
        run(snap(row("GBG", "X", "1")), scope=frozenset({"X"}), mappings=mappings, declared=declared)


def test_quantities_keep_exact_decimal_precision() -> None:
    mappings = {"X": StockMapping(9, "bag", Decimal("0.001"), True)}
    declared = {"X": DeclaredUnit("bag", Decimal("0.001"))}
    scope = frozenset({"X"})
    [result] = run(snap(row("GBG", "X", "123456.000")), scope=scope, mappings=mappings, declared=declared)
    assert result[3] == Decimal("123.456")
    with pytest.raises(
        StockNormalizationError, match="exactly"
    ):  # 123.456789 would be rounded by NUMERIC(12,3)
        run(snap(row("GBG", "X", "123456.789")), scope=scope, mappings=mappings, declared=declared)
