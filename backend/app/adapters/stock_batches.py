"""Normalize a published source stock batch to CFO global products.

Policies: DEC-SRC-Q10-SKU-001 (fixed unit per SKU), DEC-SRC-Q9-ERROR-001, DEC-CFO-STOCK-SCOPE-001
(SKU scope, option B) and DEC-CFO-STOCK-INDEPENDENCE-001 (aggregate only when independence is verified, A).

Pure function: no persistence, clock or I/O. Contract:
- Source stock has exactly one row per (warehouse, SKU), always in that SKU's declared stock unit; there is
  no pool or alias concept and equal converted quantities never imply shared stock.
- Only SKUs of the **caller-supplied CFO scope** are normalized. The scope is fixed before the sync (never
  derived from which SKUs of this batch happen to map); rows outside it are ignored and can never block.
- Any in-scope SKU that is unmapped, unconfirmed, inconsistent or unconvertible rejects the **whole**
  batch: no partial result is ever returned, so an incomplete snapshot cannot be published as complete.
- Each SKU is converted once with `units_to_base` after the source-declared unit and factor are checked
  against CFO's confirmed mapping.
- Several in-scope SKUs of one warehouse that map to one global product are summed (after conversion)
  **only** if all of them are inside one `verified_independent` group, i.e. verified independent physical
  inventory. Otherwise the batch is rejected. How independence is verified, and by whom, is not decided
  yet, so the evidence is an explicit input and the default (nothing verified) is fail closed.
  Warehouses are never merged.
"""

from collections.abc import Collection, Mapping
from collections.abc import Set as AbstractSet
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
    source_skus: tuple[str, ...]
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
    *,
    scope: AbstractSet[str],
    verified_independent: Collection[AbstractSet[str]] = (),
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
    if any(not sku.strip() for sku in scope):
        raise StockNormalizationError("Stock SKU scope contains an empty SKU")
    source_keys: set[tuple[str, str]] = set()
    groups: dict[tuple[str, int], list[tuple[str, Decimal, Decimal]]] = {}
    for item in snapshot.items:
        if not item.warehouse_code.strip() or not item.sku.strip():
            raise StockNormalizationError("Stock source key is missing")
        key = (item.warehouse_code, item.sku)
        if key in source_keys:
            raise StockNormalizationError("Stock source key is duplicated")
        source_keys.add(key)
        if item.sku not in scope:
            continue  # outside the pre-defined CFO scope: never converted, never blocking
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
        groups.setdefault((item.warehouse_code, mapping.global_product_id), []).append(
            (item.sku, on_hand, reserved)
        )
    rows: list[GlobalStock] = []
    for (warehouse, product), members in groups.items():
        skus = frozenset(sku for sku, _, _ in members)
        if len(members) > 1 and not any(skus <= group for group in verified_independent):
            raise StockNormalizationError("Several SKUs share a global product without verified independence")
        total_hand = sum((hand for _, hand, _ in members), Decimal(0))
        total_reserved = sum((reserved for _, _, reserved in members), Decimal(0))
        rows.append(
            GlobalStock(
                warehouse,
                product,
                tuple(sorted(skus)),
                stored_quantity(total_hand),
                stored_quantity(total_reserved),
                snapshot.as_of,
                snapshot.batch_id,
            )
        )
    return tuple(sorted(rows, key=lambda r: (r.warehouse_code, r.global_product_id)))
