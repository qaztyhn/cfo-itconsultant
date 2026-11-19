from decimal import Decimal

import pytest

from app.adapters.ingestion_feed import StockFeedValue, read_feed
from app.adapters.rest_adapter import SourceReadError
from app.adapters.stock_batches import DeclaredUnit
from app.adapters.wms_batch_stock import (
    WmsBatchRejected,
    WmsBatchStockAdapter,
    snapshot_from_wms_batch,
)

NATIVE = {("GBG", "WMS-CEM-25"): ("SE-CEM-MOR-25", "bag")}


def _batch(**changes: object) -> dict[str, object]:
    return {
        "source_kind": "synthetic_demo",
        "market": "SE",
        "batch_id": 3,
        "complete": True,
        "item_count": 2,
        "as_of": "2026-11-04T10:05:00+01:00",
        "items": [
            {
                "warehouse_code": "GBG",
                "wms_sku": "WMS-CEM-25",
                "wms_unit": "bag",
                "on_hand": "100.000",
                "reserved": "60.000",
            },
            {
                "warehouse_code": "GBG",
                "wms_sku": "WMS-OTHER",
                "wms_unit": "pcs",
                "on_hand": "5.000",
                "reserved": "0.000",
            },
        ],
        **changes,
    }


def test_converts_native_rows_to_pos_skus_and_drops_unmapped_rows() -> None:
    snapshot = snapshot_from_wms_batch(_batch(), NATIVE)
    assert snapshot.batch_id == 3 and snapshot.item_count == 1
    assert snapshot.as_of.utcoffset() is not None
    (item,) = snapshot.items
    assert (item.warehouse_code, item.sku) == ("GBG", "SE-CEM-MOR-25")
    assert (item.on_hand, item.reserved) == (Decimal("100"), Decimal("60"))


@pytest.mark.parametrize(
    "changes",
    [
        {"complete": False},
        {"item_count": 5},
        {"batch_id": 0},
        {"batch_id": "3"},
        {"as_of": "2026-11-04T10:05:00"},
        {"as_of": "not-a-date"},
        {"items": [{"warehouse_code": "GBG"}], "item_count": 1},
    ],
)
def test_incomplete_or_malformed_batch_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(WmsBatchRejected):
        snapshot_from_wms_batch(_batch(**changes), NATIVE)


def test_unit_mismatch_and_duplicate_pos_mapping_are_rejected() -> None:
    with pytest.raises(WmsBatchRejected):
        snapshot_from_wms_batch(_batch(), {("GBG", "WMS-CEM-25"): ("SE-CEM-MOR-25", "pcs")})
    both = {
        ("GBG", "WMS-CEM-25"): ("SE-CEM-MOR-25", "bag"),
        ("GBG", "WMS-OTHER"): ("SE-CEM-MOR-25", "pcs"),
    }
    with pytest.raises(WmsBatchRejected):
        snapshot_from_wms_batch(_batch(), both)


PRODUCTS = [
    {
        "sku": "SE-CEM-MOR-25",
        "name": "Mortar",
        "category": "cement",
        "gtin": None,
        "sale_unit": "bag",
        "units_to_base": "1",
        "unit_price": "1",
        "weight_kg": None,
        "volume_m3": None,
        "updated_at": "2026-11-04T10:05:00+01:00",
    }
]


async def test_adapter_feeds_the_stock_reader_with_verified_snapshot_and_units() -> None:
    snapshot = snapshot_from_wms_batch(_batch(), NATIVE)
    adapter = WmsBatchStockAdapter("SE", snapshot, PRODUCTS)
    records = [record async for record in read_feed(adapter, "stock", None)]
    assert len(records) == 1 and records[0].reject_code is None
    value = records[0].value
    assert isinstance(value, StockFeedValue)
    assert value.snapshot == snapshot
    assert value.declared["SE-CEM-MOR-25"] == DeclaredUnit("bag", Decimal("1"))


async def test_adapter_serves_only_the_unit_catalogue() -> None:
    adapter = WmsBatchStockAdapter("SE", snapshot_from_wms_batch(_batch(), NATIVE), PRODUCTS)
    with pytest.raises(SourceReadError):
        async for _ in adapter.raw_pages("orders", None, key_fields=("id",)):
            pass
