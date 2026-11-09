# ASM-WMS-RESERVATION-20261109 — Legacy WMS supports reserving stock (owner assumption)

**Status:** The owner explicitly approved assuming that the existing WMS **has a stock reservation / stock allocation capability** for customer orders on 2026-11-09 (“assume là có đi”). **This is an assumed capability, not a verified interface/API, nor an approval to deploy write access.**

## Business interpretation

- WMS remains the **authoritative physical stock ledger and reservation authority**. A stock reservation decreases **available-to-promise**, not physically on-hand quantity. Physical on-hand decreases only when WMS records actual pick/issue/dispatch; the reservation must be consumed/closed, not deducted again.
- Example: on-hand 100, WMS confirms a reservation of 60 => physical on-hand 100, WMS available 40. After real issue of 60 => physical on-hand 40, active reservation 0, available 40 (ignoring any other commitments).
- Avoid double deduction: when WMS's published available quantity already accounts for a CFO-originated reservation, CFO must not subtract the same 60 again. Internal CFO held/committed reservations must have an explicit inclusion/ownership boundary with WMS availability. Concurrency, consistency and source snapshot semantics require design review.
- CFO order ingestion/feasibility estimation does **not** itself imply physical stock issue. Planning may require an internal temporary hold; at the **authorized approval/commit** boundary, a proposed integration would ask WMS to atomically reserve stock, obtain a synchronous affirmative acknowledgement, and only then claim guaranteed stock. WMS rejection/timeout/unknown acknowledgement must **fail closed** (no falsely confirmed order). Periodic 5-minute stock polling is verification/freshness, **not** a substitute for the reservation acknowledgement.
- Order cancellation, approval failure, hold expiration, replan, physical issue and partial fulfillment require **idempotent reservation lifecycle** (reserve, confirm/status lookup, release/consume) with stable external reference, concurrency protection and recovery for cross-system partial failure. No WMS API capability, transaction protocol or compensation mechanism should be invented before inspection.

## Implementation authorization boundary (NOT YET OWNER APPROVED)

The latest owner clarification [DEC-WMS-READONLY-20261109](DEC_WMS_READ_ONLY_STOCK_AUTHORITY_20261109.md) says CFO **only reads WMS**. The owner's question “như vậy nếu có đơn hàng thì cfo gửi thông tin về cho wms và wms trừ sau đó cfo đồng bộ lại à” requests clarification of a **proposed exception**, not unequivocal approval to change read-only into write-enabled WMS integration.

**Therefore do not enable WMS mutation from CFO yet.** Dev 1/Dev 2 must submit a tightly scoped contract/approval proposal for **reserve/status/release only**, WMS source authority, authentication, request/response and idempotency, reservation expiry/partial fulfillment, conflict/timeout compensation and stock calculation ownership. Legacy POS modifications and WMS physical stock adjustments remain out of scope. Seek explicit owner approval of the narrow outbound write exception and verified WMS interface before implementation.

**Not part of this docs PR:** any WMS endpoint implementation, live credentials, actual reservation, code changes, migration or merge.