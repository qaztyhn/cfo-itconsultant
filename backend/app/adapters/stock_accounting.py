"""Available-to-promise with no double subtraction of WMS reservations (DEC-WMS-RESERVE-SYNC-20261109).

WMS `reserved` already lowers WMS availability and is owned by WMS across ALL channels; physical `on_hand`
is
untouched by a reservation. CFO may subtract only its own commitments that WMS has NOT yet reflected:
- tentative local planning hold (never sent to WMS)            -> subtract;
- WMS-acknowledged reservation, batch proves inclusion          -> do NOT subtract (WMS reserved has it);
- WMS-acknowledged reservation, no proof the batch includes it  -> subtract (conservative pending
  protection).
Inclusion needs a version proof (`batch_id >= reflected_in_batch_id` supplied by WMS); a later `as_of`
alone is
never proof. Missing rows are unknown, never zero. Pure; no I/O or clock.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CfoCommitment:
    warehouse_code: str
    wms_sku: str
    quantity: Decimal
    kind: str  # "tentative" | "wms_acked"
    reflected_in_batch_id: int | None = None


@dataclass(frozen=True)
class Availability:
    warehouse_code: str
    wms_sku: str
    on_hand: Decimal
    wms_reserved: Decimal
    wms_available: Decimal
    pending_subtracted: Decimal
    available: Decimal  # never below zero
    shortfall: bool  # True when commitments exceed what WMS reports available
    pending_inclusion: bool  # some acknowledged reservation is not yet proven to be in this batch


def included_in_batch(batch_id: int | None, commitment: CfoCommitment) -> bool:
    return (
        commitment.kind == "wms_acked"
        and batch_id is not None
        and commitment.reflected_in_batch_id is not None
        and batch_id >= commitment.reflected_in_batch_id
    )


def compute_availability(
    batch_id: int | None,
    rows: Mapping[tuple[str, str], tuple[Decimal, Decimal]],
    commitments: Collection[CfoCommitment],
    wanted: Collection[tuple[str, str]],
) -> dict[tuple[str, str], Availability]:
    """`rows` = {(warehouse_code, sku): (on_hand, reserved)} from ONE complete published batch."""
    result: dict[tuple[str, str], Availability] = {}
    for key in wanted:
        if key not in rows:
            raise ValueError("STOCK_ROW_UNKNOWN")  # absent is unknown, never zero
        on_hand, reserved = rows[key]
        wms_available = on_hand - reserved
        pending = Decimal(0)
        pending_flag = False
        for c in commitments:
            if (c.warehouse_code, c.wms_sku) != key:
                continue
            if c.kind == "tentative":
                pending += c.quantity
            elif c.kind == "wms_acked" and not included_in_batch(batch_id, c):
                pending += c.quantity
                pending_flag = True
        available = wms_available - pending
        result[key] = Availability(
            key[0],
            key[1],
            on_hand,
            reserved,
            wms_available,
            pending,
            max(available, Decimal(0)),
            available < 0,
            pending_flag,
        )
    return result
