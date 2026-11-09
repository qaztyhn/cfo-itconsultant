# DEC-WMS-READONLY-20261109 — WMS is the authoritative stock and transfer ledger

**Status: OWNER CLARIFICATION / APPROVED — 2026-11-09.** The owner corrected the previous proposed CFO transfer-reconciliation approach: “CFO chỉ lấy dữ liệu từ WMS nhé. Sao phải quản lý mấy cái này”. This is a product-boundary clarification and **supersedes the proposed CFO-owned WMS movement reconciliation workflow** in DEC-T18-WMS-RECON-20261109, without undoing the already approved stock safety invariants.

## Approved responsibility boundary

- **Legacy WMS owns** physical stock ledger, stock receipt/issue, physical warehouse-to-warehouse movements, inventory reconciliation, warehouse transfer movement records and correction of on-hand balances.
- **CFO only reads WMS/Source**. CFO must not issue, receive or reconcile physical movement in WMS and must never write or correct legacy WMS stock. CFO must not require a duplicate in-CFO per-transfer WMS movement case, WMS receipt approval, separate documentary evidence workflow, `PENDING_RECONCILIATION` queue or a 24h unresolved-reconciliation escalation merely to consume WMS inventory.
- **CFO planning owns** its own immutable order/plan commitments, held/committed reservations and feasibility checks. It reads the current **published, complete, sufficiently fresh and market/SKU-scoped** WMS stock snapshot. A WMS stock change is reflected only by the next valid source sync or verified Sync Now read. Unknown/stale/partial WMS stock must fail closed for new guarantees; zero must be explicit.
- To prevent double counting, **do not add CFO transfer inbound to WMS on-hand or subtract physical transfer outbound a second time**. Pending transfer hints/ETA may only come from authoritative WMS/Source data and remain non-available until verified in the WMS stock feed; no CFO-synthesized physical movement adjustment. CFO reservations against confirmed available stock remain separately enforced to prevent multiple orders consuming the same stock.
- Existing CFO `stock_transfer` / `inbound_shipment(source=transfer)` concepts and endpoints in PR #127 / docs §7 were drafted before this clarification. **They need a product/technical review for scope:** a *suggestion or request* may remain as non-authoritative planning information, but physical confirm-source/receive and the workflow that treats CFO movement as stock truth cannot be activated as presently designed. Do not silently delete APIs/migrations or auto-merge #127; propose a targeted contract change before implementing.
- **Stock Admin bootstrap** remains applicable only to CFO-specific approved market/SKU scope, independent-evidence policy and protected configuration (S1/S2), **not to control the WMS physical stock ledger**. If scope governance is later simplified, request an explicit owner change.
- **Previous owner assumption preserved:** WMS records outbound and inbound transfers operationally. However, CFO need not ingest per-movement IDs simply to calculate on-hand availability from a correct WMS published stock snapshot. If WMS itself has faulty/missing stock, refer investigation to WMS owners; CFO does not invent numbers.

## Clarifications to pending decisions

- Previous **Q3 “24h unresolved reconciliation” is not required for the CFO MVP** under the read-only design. Report source freshness, failed sync and unusable WMS batches as integration issues instead; their own alerts are separate from physical movement reconciliation.
- The previous `DEC-T18-WMS-RECON-20261109` requiring WMS movement proof and independent reviewer within CFO is **superseded** by this clarification. T18-1's **no double counting**, T18-2 lead provenance and T18-3 reversal guard remain safety constraints until the transfer feature is reviewed.
- No code, schema or actual WMS integration has been changed by this docs clarification.

## Handoff

**Dev 1:** Review #127 transfer/receipt endpoints and any synthesized stock adjustments against WMS-source-only policy; preserve WMS-source ATP and CFO reservations. Review #148 to keep Stock Admin authority limited to CFO configuration/scope. **Dev 2:** Read complete/fresh WMS stock batches, preserve idempotency and stock unavailable/fail-closed behavior; do not invent movement reconciliation services. **Dev 3:** Show source freshness/unknown stock, do not add an unapproved reconciliation dashboard.

## Subsequent approved narrow exception — reservation on CFO-approved plan

[DEC-WMS-RESERVE-SYNC-20261109](DEC_WMS_RESERVE_SYNC_20261109.md) **supersedes the blanket no-CFO-write-to-WMS wording above only for an owner-selected reserve-on-approval workflow**: CFO reads WMS stock, an authorized user confirms a plan, CFO sends a narrowly scoped WMS reserve request using the verified original WMS SKU, WMS atomically confirms and reduces available (not physical on_hand), and CFO immediately refreshes its WMS-derived stock/availability and order state. Actual WMS API and production write deployment are still gated by reviewed contract/security/testing; the decision does not permit WMS physical stock adjustment or reintroduce CFO-owned transfer reconciliation. All other read-only boundaries remain.
