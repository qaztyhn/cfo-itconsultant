from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.adapters.base import StockItemDTO, StockSnapshotDTO
from app.adapters.stock_pools import StockMapping, StockNormalizationError, normalize

NOW = datetime(2026, 11, 4, tzinfo=UTC)
MAPPINGS = {"bags": StockMapping(1, Decimal(1), True), "pallets": StockMapping(1, Decimal(40), True)}


def item(sku: str, pool: str, on_hand: str, reserved: str, warehouse: str = "WH") -> StockItemDTO:
    return StockItemDTO(warehouse, sku, Decimal(on_hand), Decimal(reserved), pool)


def batch(*items: StockItemDTO) -> StockSnapshotDTO:
    return StockSnapshotDTO(NOW, items, batch_id=1, complete=True, row_count=len(items))


def test_US_INT_03_AC1_D1_aliases_count_once_only_after_exact_unit_conversion() -> None:
    result = normalize(
        batch(item("bags", "pool", "100", "20"), item("pallets", "pool", "2.5", "0.5")), MAPPINGS
    )
    assert len(result) == 1
    assert result[0].on_hand == Decimal(100) and result[0].reserved == Decimal(20)
    assert result[0].pool_ids == ("pool",) and result[0].batch_id == 1


def test_US_INT_03_AC1_D1_distinct_pools_sum_and_pool_scope_is_warehouse() -> None:
    data = batch(
        item("bags", "pool1", "100", "20"),
        item("pallets", "pool2", "2.5", "0.5"),
        item("bags", "pool1", "7", "1", "OTHER"),
    )
    result = {row.warehouse_code: row for row in normalize(data, MAPPINGS)}
    assert result["WH"].on_hand == Decimal(200) and result["WH"].reserved == Decimal(40)
    assert result["OTHER"].on_hand == Decimal(7)
    assert normalize(batch(), MAPPINGS) == ()  # Only a proven complete empty batch is authoritative zero.


@pytest.mark.parametrize(
    "changed",
    [
        {"complete": False},
        {"batch_id": None},
        {"row_count": 1},
        {"as_of": NOW.replace(tzinfo=None)},
    ],
)
def test_US_INT_03_AC1_D1_unknown_incomplete_batch_never_normalizes_to_zero(
    changed: dict[str, object],
) -> None:
    with pytest.raises(StockNormalizationError):
        normalize(replace(batch(), **changed), MAPPINGS)


@pytest.mark.parametrize(
    "data,mapping",
    [
        (batch(item("bags", "pool", "100", "20"), item("pallets", "pool", "3", "0.5")), MAPPINGS),
        (
            batch(item("bags", "pool", "100", "20"), item("pallets", "pool", "2.5", "0.5")),
            {**MAPPINGS, "pallets": StockMapping(2, Decimal(40), True)},
        ),
        (batch(item("bags", "", "1", "0")), MAPPINGS),
        (batch(item("bags", "pool", "1", "0")), {}),
        (batch(item("bags", "pool", "1", "0")), {"bags": StockMapping(1, Decimal(1), False)}),
        (batch(item("bags", "pool", "1", "0")), {"bags": StockMapping(1, Decimal(0), True)}),
        (batch(item("bags", "pool", "1.0001", "0")), MAPPINGS),
        (batch(item("bags", "pool", "1000000000", "0")), MAPPINGS),
        (batch(item("bags", "pool", "-1", "0")), MAPPINGS),
        (batch(item("bags", "pool", "1", "-1")), MAPPINGS),
        (batch(item("bags", "pool", "1", "0"), item("bags", "pool", "1", "0")), MAPPINGS),
    ],
)
def test_US_INT_03_AC1_D1_ambiguous_alias_mapping_or_unrepresentable_storage_is_quarantined(
    data: StockSnapshotDTO, mapping: dict[str, StockMapping]
) -> None:
    with pytest.raises(StockNormalizationError):
        normalize(data, mapping)


def test_D1_alias_reserved_mismatch_and_aggregate_overflow_are_rejected() -> None:
    with pytest.raises(StockNormalizationError):
        normalize(batch(item("bags", "pool", "100", "20"), item("pallets", "pool", "2.5", "0.4")), MAPPINGS)
    with pytest.raises(StockNormalizationError):
        normalize(
            batch(item("bags", "pool1", "600000000", "0"), item("pallets", "pool2", "15000000", "0")),
            MAPPINGS,
        )
