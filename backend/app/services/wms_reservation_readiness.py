"""Fail-closed value validation for a *prospective* WMS reservation integration.

DEC-WMS-RESERVE-SYNC / REVERSE-SKU (2026-11-09): the owner approved the
business sequence, not a live transport, DTO, durable state machine, or write
credentials. This module makes NO WMS calls, NO database writes, and MUST NOT
be interpreted as approval to reserve inventory. Its input must originate
from trusted server-side provenance, never a browser payload.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.errors import DomainError


def _reject(message: str) -> None:
    raise DomainError("PLAN_NOT_APPROVABLE", message)


@dataclass(frozen=True)
class VerifiedSourceLine:
    """Source/POS line with separately verified WMS identity and stock unit."""

    order_id: int
    line_no: int
    market_id: int
    warehouse_id: int
    global_product_id: int
    pos_sku: str
    wms_sku: str
    wms_unit: str
    mapping_version: str
    source_version: int
    sale_quantity: Decimal
    units_to_base: Decimal
    base_units_per_wms_unit: Decimal
    wms_quantity_scale: int
    mapping_confirmed: bool
    pos_wms_relation_verified: bool
    warehouse_allocation_verified: bool
    snapshot_complete_and_fresh: bool


@dataclass(frozen=True)
class WmsLine:
    """A stock-unit-specific reservation line; NOT a CFO global-product key."""

    line_no: int
    warehouse_id: int
    wms_sku: str
    wms_unit: str
    quantity: Decimal


@dataclass(frozen=True)
class ReserveIntent:
    """Proposed canonical data for an external idempotent request (no transport)."""

    order_id: int
    market_id: int
    warehouse_id: int
    source_version: int
    idempotency_key: str
    lines: tuple[WmsLine, ...]


@dataclass(frozen=True)
class ReserveAck:
    """Authoritative WMS proof, after independent authentication by an adapter."""

    idempotency_key: str
    reservation_id: str
    status: str
    lines: tuple[WmsLine, ...]


def _positive(value: Decimal) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value > 0


def prepare_intent(
    originals: tuple[VerifiedSourceLine, ...],
    *,
    idempotency_key: str,
) -> ReserveIntent:
    """Require original SKU provenance, exact units and one reservation per order line.

    Never reverse-lookup a global product by choosing an arbitrary local SKU.
    The caller must first have approved all five gates, the Sales/Dispatcher
    authorization, stock scope and the market's batch/watermark evidence.
    This function does not verify those unrelated authorization or gate proofs.
    """
    if not originals or not idempotency_key.strip() or len(idempotency_key) > 200:
        _reject("Verified order lines and a stable idempotency key are required.")
    first = originals[0]
    ids = (
        first.order_id,
        first.market_id,
        first.warehouse_id,
        first.source_version,
    )
    if any(value <= 0 for value in ids) or any(
        line.order_id != first.order_id
        or line.market_id != first.market_id
        or line.warehouse_id != first.warehouse_id
        or line.source_version != first.source_version
        for line in originals
    ):
        _reject("All WMS reservation lines must belong to one order, warehouse and source version.")

    seen: set[int] = set()
    built: list[WmsLine] = []
    for line in originals:
        if line.line_no < 1 or line.line_no in seen or line.global_product_id <= 0:
            _reject("Duplicate or invalid source order line.")
        seen.add(line.line_no)
        if not all(
            (
                line.pos_sku.strip(),
                line.wms_sku.strip(),
                line.wms_unit.strip(),
                line.mapping_version.strip(),
            )
        ):
            _reject("WMS SKU, fixed unit and mapping provenance are required.")
        if not all(
            (
                line.mapping_confirmed,
                line.pos_wms_relation_verified,
                line.warehouse_allocation_verified,
                line.snapshot_complete_and_fresh,
            )
        ):
            _reject("Source-to-WMS identity, mapping or stock evidence is unverified.")
        if not (
            _positive(line.sale_quantity)
            and _positive(line.units_to_base)
            and _positive(line.base_units_per_wms_unit)
        ):
            _reject("A positive exact fixed-unit conversion is required.")
        if not 0 <= line.wms_quantity_scale <= 3:
            _reject("WMS quantity precision is not verified.")
        quantity = line.sale_quantity * line.units_to_base / line.base_units_per_wms_unit
        scale = Decimal(1).scaleb(-line.wms_quantity_scale)
        if not _positive(quantity) or quantity != quantity.quantize(scale):
            _reject("The WMS stock unit cannot represent the order quantity exactly.")
        built.append(
            WmsLine(
                line_no=line.line_no,
                warehouse_id=line.warehouse_id,
                wms_sku=line.wms_sku,
                wms_unit=line.wms_unit,
                quantity=quantity,
            )
        )
    return ReserveIntent(
        order_id=first.order_id,
        market_id=first.market_id,
        warehouse_id=first.warehouse_id,
        source_version=first.source_version,
        idempotency_key=idempotency_key,
        lines=tuple(sorted(built, key=lambda line: line.line_no)),
    )


def require_full_ack(intent: ReserveIntent, ack: ReserveAck | None) -> str:
    """Fail closed on partial/duplicate/mismatched/unknown WMS acknowledgement.

    Timeout, connection loss and unconfirmed WMS status MUST result in lookup
    using the SAME idempotency key, not a new reserve call. A matching ACK is
    necessary, but NOT sufficient, to commit CFO APPROVED: the caller also
    needs durable cross-system recovery and a post-ACK stock refresh.
    """
    if (
        ack is None
        or ack.idempotency_key != intent.idempotency_key
        or not ack.reservation_id.strip()
        or ack.status != "accepted"
        or len(ack.lines) != len(intent.lines)
        or tuple(sorted(ack.lines, key=lambda line: line.line_no)) != intent.lines
        or len({line.line_no for line in ack.lines}) != len(ack.lines)
    ):
        _reject("WMS reservation is not authoritatively and completely acknowledged.")
    return ack.reservation_id


def require_snapshot_inclusion(
    reservation_id: str,
    *,
    authoritative_included_reservation_ids: frozenset[str] | None,
) -> None:
    """Never infer inclusion from batch.as_of or a changed available quantity.

    The prospective Dev 2 adapter must supply WMS-authenticated inclusion
    evidence by reservation ID. A lagging or unknown batch cannot release
    the conservative pending-inclusion protection for new approvals.
    """
    if (
        not reservation_id.strip()
        or authoritative_included_reservation_ids is None
        or reservation_id not in authoritative_included_reservation_ids
    ):
        _reject("WMS snapshot inclusion is unverified; keep stock unavailable for new commitments.")
