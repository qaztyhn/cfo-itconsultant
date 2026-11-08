"""Fixed-SKU stock normalization (DEC-SRC-Q10-SKU-001): one row per (warehouse, SKU), all-or-nothing."""

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


def run(snapshot: StockSnapshotDTO) -> list[tuple[str, int, str, Decimal, Decimal]]:
    return [
        (r.warehouse_code, r.global_product_id, r.source_sku, r.on_hand, r.reserved)
        for r in normalize_stock(snapshot, MAPPINGS, DECLARED)
    ]


def test_each_sku_is_converted_once_per_warehouse() -> None:
    result = run(
        snap(row("GBG", "CEM-PAL", "5", "1"), row("GBG", "CEM-25", "100", "10"), row("STO", "TILE", "7"))
    )
    assert result == [
        ("GBG", 1, "CEM-25", Decimal("100"), Decimal("10")),
        ("GBG", 2, "CEM-PAL", Decimal("200"), Decimal("40")),  # 5 pallets x 40 bags, converted once
        ("STO", 3, "TILE", Decimal("3.5"), Decimal("0")),
    ]


def test_equal_converted_quantities_never_imply_shared_stock() -> None:
    """100 bags of one SKU and 2.5 pallets of another are two inventories (and two products), never merged."""
    rows = run(snap(row("GBG", "CEM-25", "100"), row("GBG", "CEM-PAL", "2.5")))
    assert [(r[1], r[3]) for r in rows] == [(1, Decimal("100")), (2, Decimal("100.0"))]


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
        normalize_stock(broken(snap(row("GBG", "CEM-25", "1"))), MAPPINGS, DECLARED)  # type: ignore[operator]


def test_duplicate_source_key_is_a_malformed_batch_not_extra_inventory() -> None:
    with pytest.raises(StockNormalizationError, match="duplicated"):
        run(snap(row("GBG", "CEM-25", "1"), row("GBG", "CEM-25", "2")))


def test_several_skus_of_one_warehouse_for_one_global_product_fail_closed() -> None:
    mappings = {**MAPPINGS, "CEM-25-ALT": StockMapping(1, "bag", Decimal("1"), True)}
    declared = {**DECLARED, "CEM-25-ALT": DeclaredUnit("bag", Decimal("1"))}
    with pytest.raises(StockNormalizationError, match="same global product"):
        normalize_stock(
            snap(row("GBG", "CEM-25", "100"), row("GBG", "CEM-25-ALT", "100")), mappings, declared
        )
    # the same two SKUs in different warehouses are fine: warehouses are independent inventories
    assert (
        len(
            normalize_stock(
                snap(row("GBG", "CEM-25", "1"), row("STO", "CEM-25-ALT", "1")), mappings, declared
            )
        )
        == 2
    )


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
def test_unresolved_or_inconsistent_sku_rejects_the_whole_batch(
    mappings: dict[str, StockMapping], declared: dict[str, DeclaredUnit], message: str
) -> None:
    items = (row("GBG", "CEM-25", "1"),)
    with pytest.raises(StockNormalizationError, match=message):
        normalize_stock(snap(*items), mappings, declared)


def test_one_bad_row_never_yields_a_partial_result() -> None:
    mappings = {k: v for k, v in MAPPINGS.items() if k != "TILE"}  # TILE unmapped
    with pytest.raises(StockNormalizationError):
        normalize_stock(snap(row("GBG", "CEM-25", "1"), row("GBG", "TILE", "1")), mappings, DECLARED)


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "0.0004", "1000000000", "1.0001"])
def test_quantities_the_database_would_round_or_reject_are_refused(value: str) -> None:
    with pytest.raises(StockNormalizationError):
        stored_quantity(Decimal(value))


def test_conversion_that_is_not_exact_in_numeric_12_3_is_refused() -> None:
    mappings = {"X": StockMapping(9, "bag", Decimal("0.0003"), True)}
    declared = {"X": DeclaredUnit("bag", Decimal("0.0003"))}
    with pytest.raises(StockNormalizationError, match="exactly"):
        normalize_stock(snap(row("GBG", "X", "1")), mappings, declared)


def test_quantities_keep_exact_decimal_precision() -> None:
    mappings = {"X": StockMapping(9, "bag", Decimal("0.001"), True)}
    declared = {"X": DeclaredUnit("bag", Decimal("0.001"))}
    [result] = normalize_stock(snap(row("GBG", "X", "123456.000")), mappings, declared)
    assert result.on_hand == Decimal("123.456")
    with pytest.raises(
        StockNormalizationError, match="exactly"
    ):  # 123.456789 would be rounded by NUMERIC(12,3)
        normalize_stock(snap(row("GBG", "X", "123456.789")), mappings, declared)
