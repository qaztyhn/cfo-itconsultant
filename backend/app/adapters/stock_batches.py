"""Normalize a published source stock batch to CFO global products (DEC-SRC-Q10-SKU-001, Q9-ERROR-001).

Pure function: no persistence, clock, market policy or I/O. Contract:
- Source stock has exactly one row per (warehouse, SKU), always in that SKU's declared stock unit. There is
  no physical-pool or alias concept; equal converted quantities never imply shared stock.
- Each SKU's quantities are converted to base units **once** with `units_to_base`, after checking that the
  unit and factor declared by the source product feed equal CFO's confirmed mapping.
- All-or-nothing: any unresolved or ambiguous row raises and **no** partial result is returned, so the
  caller can never commit an apparently complete snapshot that misses inventory.
- Several local SKUs of one warehouse that map to the same global product are NOT added together: the
  independence of their inventory is not verifiable here, so the snapshot fails closed until a reviewed
  mapping contract defines how to verify it. Different warehouses are independent and never merged.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, DecimalException, localcontext

from app.adapters.base import StockSnapshotDTO


class StockNormalizationError(ValueError):
    """Safe reason for rejecting a whole batch; never carries source content or PII."""


@dataclass(frozen=True)
class StockMapping:
    """CFO's reviewed mapping of one local SKU (`ref.product_se`)."""

    global_product_id: int
    sale_unit: str
    units_to_base: Decimal
    confirmed: bool


@dataclass(frozen=True)
class DeclaredUnit:
    """Stock unit and factor the source product feed declares for the SKU."""

    sale_unit: str
    units_to_base: Decimal


@dataclass(frozen=True)
class GlobalStock:
    warehouse_code: str
    global_product_id: int
    source_sku: str
    on_hand: Decimal
    reserved: Decimal
    as_of: datetime
    batch_id: int


def stored_quantity(value: Decimal) -> Decimal:
    """`ops.stock_snapshot` is NUMERIC(12,3): refuse anything the database would round."""
    if (
        not value.is_finite()
        or value < 0
        or value >= Decimal("1e9")
        or value != value.quantize(Decimal("0.001"))
    ):
        raise StockNormalizationError("Stock quantity is not exactly representable in CFO storage")
    return value


def _factor(value: Decimal) -> Decimal:
    if not value.is_finite() or value <= 0:
        raise StockNormalizationError("Stock conversion factor is invalid")
    return value


def normalize_stock(
    snapshot: StockSnapshotDTO,
    mappings: Mapping[str, StockMapping],
    declared: Mapping[str, DeclaredUnit],
) -> tuple[GlobalStock, ...]:
    if (
        type(snapshot.batch_id) is not int
        or snapshot.batch_id <= 0
        or type(snapshot.item_count) is not int
        or snapshot.item_count != len(snapshot.items)
        or snapshot.as_of.tzinfo is None
        or snapshot.as_of.utcoffset() is None
    ):
        raise StockNormalizationError("Stock batch is not an authoritative complete published batch")
    rows: list[GlobalStock] = []
    source_keys: set[tuple[str, str]] = set()
    product_keys: dict[tuple[str, int], str] = {}
    for item in snapshot.items:
        if not item.warehouse_code.strip() or not item.sku.strip():
            raise StockNormalizationError("Stock source key is missing")
        key = (item.warehouse_code, item.sku)
        if key in source_keys:
            raise StockNormalizationError("Stock source key is duplicated")
        source_keys.add(key)
        mapping = mappings.get(item.sku)
        if mapping is None or mapping.confirmed is not True:
            raise StockNormalizationError("Stock SKU has no confirmed mapping")
        unit = declared.get(item.sku)
        if unit is None:
            raise StockNormalizationError("Stock SKU has no declared source unit")
        if (
            type(mapping.global_product_id) is not int
            or mapping.global_product_id <= 0
            or not mapping.sale_unit.strip()
            or mapping.sale_unit != unit.sale_unit
            or _factor(mapping.units_to_base) != _factor(unit.units_to_base)
        ):
            raise StockNormalizationError("Stock SKU unit or conversion differs from the confirmed mapping")
        product_key = (item.warehouse_code, mapping.global_product_id)
        if product_key in product_keys:
            raise StockNormalizationError("Several SKUs of one warehouse map to the same global product")
        product_keys[product_key] = item.sku
        factor = mapping.units_to_base
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
        rows.append(
            GlobalStock(
                item.warehouse_code,
                mapping.global_product_id,
                item.sku,
                on_hand,
                reserved,
                snapshot.as_of,
                snapshot.batch_id,
            )
        )
    return tuple(sorted(rows, key=lambda r: (r.warehouse_code, r.global_product_id)))
