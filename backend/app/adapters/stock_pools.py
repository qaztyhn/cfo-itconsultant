"""D1-D/Q10 exact physical-pool normalization; no persistence, clock or market-specific policy."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, DecimalException, localcontext

from app.adapters.base import StockSnapshotDTO


class StockNormalizationError(ValueError):
    """Safe batch quarantine reason, without raw source content or PII."""


@dataclass(frozen=True)
class StockMapping:
    global_product_id: int
    units_to_base: Decimal
    confirmed: bool


@dataclass(frozen=True)
class GlobalStock:
    warehouse_code: str
    global_product_id: int
    on_hand: Decimal
    reserved: Decimal
    pool_ids: tuple[str, ...]
    as_of: datetime
    batch_id: int


def stored_quantity(value: Decimal) -> Decimal:
    # Existing 05 ops.stock_snapshot is NUMERIC(12,3). Never rely on DB rounding stock upwards.
    if (
        not value.is_finite()
        or value < 0
        or value >= Decimal("1e9")
        or value != value.quantize(Decimal("0.001"))
    ):
        raise StockNormalizationError("Stock quantity is not exactly representable in CFO storage")
    return value


def normalize(snapshot: StockSnapshotDTO, mappings: Mapping[str, StockMapping]) -> tuple[GlobalStock, ...]:
    if (
        snapshot.complete is not True
        or type(snapshot.batch_id) is not int
        or snapshot.batch_id <= 0
        or type(snapshot.row_count) is not int
        or snapshot.row_count != len(snapshot.items)
        or snapshot.as_of.tzinfo is None
        or snapshot.as_of.utcoffset() is None
    ):
        raise StockNormalizationError("Stock batch is not authoritative/complete")
    pools: dict[tuple[str, str], tuple[int, Decimal, Decimal]] = {}
    seen: set[tuple[str, str]] = set()
    for item in snapshot.items:
        pool_id = item.physical_stock_pool_id
        if pool_id is None or not pool_id.strip() or not item.warehouse_code.strip() or not item.sku.strip():
            raise StockNormalizationError("Stock physical identity is missing")
        key = (item.warehouse_code, item.sku)
        if key in seen:
            raise StockNormalizationError("Stock source key is duplicated")
        seen.add(key)
        mapping = mappings.get(item.sku)
        if mapping is None or mapping.confirmed is not True:
            raise StockNormalizationError("Stock mapping is missing or unconfirmed")
        factor = mapping.units_to_base
        if (
            type(mapping.global_product_id) is not int
            or mapping.global_product_id <= 0
            or not factor.is_finite()
            or factor <= 0
        ):
            raise StockNormalizationError("Stock mapping/conversion is invalid")
        try:
            with localcontext() as context:
                context.prec = max(
                    28,
                    len(factor.as_tuple().digits)
                    + max(len(item.on_hand.as_tuple().digits), len(item.reserved.as_tuple().digits))
                    + 2,
                )
                on_hand = stored_quantity(item.on_hand * factor)
                reserved = stored_quantity(item.reserved * factor)
        except DecimalException:
            raise StockNormalizationError("Stock conversion cannot be represented exactly") from None
        pool_key = (item.warehouse_code, pool_id)
        state = (mapping.global_product_id, on_hand, reserved)
        if pool_key in pools and pools[pool_key] != state:
            raise StockNormalizationError("Stock pool aliases disagree on product or converted quantity")
        pools[pool_key] = state  # Identical aliases count once; distinct physical pools may sum.
    totals: dict[tuple[str, int], tuple[Decimal, Decimal, list[str]]] = {}
    for (warehouse, pool), (product, on_hand, reserved) in pools.items():
        old_hand, old_reserved, names = totals.get((warehouse, product), (Decimal(0), Decimal(0), []))
        totals[(warehouse, product)] = (
            stored_quantity(old_hand + on_hand),
            stored_quantity(old_reserved + reserved),
            names + [pool],
        )
    return tuple(
        GlobalStock(
            warehouse, product, on_hand, reserved, tuple(sorted(names)), snapshot.as_of, snapshot.batch_id
        )
        for (warehouse, product), (on_hand, reserved, names) in sorted(totals.items())
    )
