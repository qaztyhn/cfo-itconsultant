"""Reverse SKU resolver for CFO -> WMS reservation requests (DEC-WMS-REVERSE-SKU-20261109).

Pure and fail-closed. A CFO `global_product_id` is NEVER sent to WMS and the POS `local_sku` is NEVER
assumed to be the WMS SKU: the WMS-native SKU comes only from an explicit, confirmed POS<->WMS relation
for the exact (market, warehouse, local_sku). One global product may have several local SKUs, so the
inverse is resolved from the original order line, never "the first match". Quantities are converted
exactly into the WMS SKU's fixed stock unit (DEC-SRC-Q10-SKU-001); anything ambiguous, missing, changed or
fractional-when-forbidden rejects the whole request. No I/O, no clock."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from decimal import Decimal, DecimalException, Inexact, localcontext


class ReverseSkuError(ValueError):
    """Safe reason code only; never carries source payloads."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class OrderLineRef:
    order_line_id: int
    local_sku: str  # original POS SKU of the order line (provenance)
    global_product_id: int
    qty_base: Decimal  # derived from qty_sale x units_to_base at order time
    mapping_version: str  # version/etag of the confirmed mapping the line was planned with


@dataclass(frozen=True)
class ConfirmedMapping:
    local_sku: str
    global_product_id: int
    sale_unit: str
    units_to_base: Decimal
    confirmed: bool
    version: str


@dataclass(frozen=True)
class WmsSkuRelation:
    """Explicitly confirmed POS<->WMS relation for a market/warehouse (never inferred from equal strings)."""

    market: str
    warehouse_code: str
    local_sku: str
    wms_sku: str
    stock_unit: str  # the unit the WMS stock row of `wms_sku` is published in
    units_to_base: Decimal  # base units per WMS stock unit
    allow_fraction: bool  # whether the WMS accepts fractional quantities for this SKU
    confirmed: bool


@dataclass(frozen=True)
class ReservationLine:
    order_line_id: int
    pos_sku: str
    wms_sku: str
    warehouse_code: str
    quantity: Decimal  # in the WMS stock unit
    wms_unit: str
    mapping_version: str


def _exact_quantity(qty_base: Decimal, units_to_base: Decimal, *, allow_fraction: bool) -> Decimal:
    if not qty_base.is_finite() or qty_base <= 0 or not units_to_base.is_finite() or units_to_base <= 0:
        raise ReverseSkuError("QUANTITY_INVALID")
    try:
        with localcontext() as ctx:
            ctx.prec = 40
            ctx.traps[Inexact] = True
            quotient = qty_base / units_to_base
    except DecimalException:
        raise ReverseSkuError("QUANTITY_NOT_EXACT") from None
    if quotient != quotient.quantize(Decimal("0.001")):
        raise ReverseSkuError("QUANTITY_NOT_EXACT")  # NUMERIC(12,3) stock precision: never round silently
    if not allow_fraction and quotient != quotient.to_integral_value():
        raise ReverseSkuError("FRACTIONAL_QUANTITY_NOT_ALLOWED")
    return quotient.quantize(Decimal("0.001")).normalize()


def resolve_reservation_lines(
    market: str,
    warehouse_code: str,
    lines: Collection[OrderLineRef],
    mappings: Mapping[str, ConfirmedMapping],
    relations: Collection[WmsSkuRelation],
    warehouse_skus: Collection[tuple[str, str]],
) -> tuple[ReservationLine, ...]:
    """Resolve every order line or raise: no partial result is ever returned."""
    if not market.strip() or not warehouse_code.strip() or not lines:
        raise ReverseSkuError("REQUEST_INCOMPLETE")
    by_key: dict[str, list[WmsSkuRelation]] = {}
    for rel in relations:
        if rel.market == market and rel.warehouse_code == warehouse_code:
            by_key.setdefault(rel.local_sku, []).append(rel)
    resolved: list[ReservationLine] = []
    for line in sorted(lines, key=lambda x: x.order_line_id):
        mapping = mappings.get(line.local_sku)
        if mapping is None or mapping.confirmed is not True:
            raise ReverseSkuError("MAPPING_NOT_CONFIRMED")
        if mapping.global_product_id != line.global_product_id or mapping.version != line.mapping_version:
            raise ReverseSkuError("MAPPING_CHANGED")  # wrong product or a version other than the planned one
        candidates = [r for r in by_key.get(line.local_sku, []) if r.confirmed is True]
        if not candidates:
            raise ReverseSkuError("WMS_SKU_NOT_VERIFIED")  # POS SKU == WMS SKU is never assumed
        if len(candidates) > 1:
            raise ReverseSkuError("WMS_SKU_AMBIGUOUS")
        rel = candidates[0]
        if (warehouse_code, rel.wms_sku) not in set(warehouse_skus):
            raise ReverseSkuError("WMS_SKU_NOT_IN_WAREHOUSE")
        if rel.stock_unit != mapping.sale_unit or rel.units_to_base != mapping.units_to_base:
            raise ReverseSkuError("UNIT_MISMATCH")
        resolved.append(
            ReservationLine(
                order_line_id=line.order_line_id,
                pos_sku=line.local_sku,
                wms_sku=rel.wms_sku,
                warehouse_code=warehouse_code,
                quantity=_exact_quantity(line.qty_base, rel.units_to_base, allow_fraction=rel.allow_fraction),
                wms_unit=rel.stock_unit,
                mapping_version=mapping.version,
            )
        )
    return tuple(resolved)
