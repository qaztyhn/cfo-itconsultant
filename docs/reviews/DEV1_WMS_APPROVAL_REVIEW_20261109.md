# Dev 1 review: WMS reservation, stock governance, transfer authority and GPS

**Date:** 2026-11-09. **Status:** technical proposal / fail-closed review, **NOT** an approved API or migration. Base: `main` after merged #155. Open PRs reviewed: #127, #148, #129, #121, #137, #151. Existing contracts in docs/04, 05, 06, 09 remain unchanged.

## 1. Priority: approval must not claim WMS stock guarantee without WMS ACK

**Existing code:** `backend/app/services/approval_service.py` already locks/rechecks stock, labour, vehicles and driver, calls the trusted `five_gate_recheck`, commits local stock reservations and the order, and queues CONFIRMED. In `_stock_available()` its current equation is `on_hand − wms_reserved − other CFO committed − other held (Sales)`. That is only safe when there is no WMS-confirmed CFO reservation included in `wms_reserved`. Once WMS holds the same CFO line and the new snapshot includes it, subtracting CFO committed again counts it twice. **No external WMS reserve/status/release interface or inclusion watermark has been verified.**

Do not treat the existing local `committed` state as proof of external stock reservation; do not enable a new success response until the approval transaction is reconciled with a real, reviewed external receipt. The approved five gates, 15-minute tentative hold, exact source-version, warehouse shift, 56-day driving/rest/legal-scope checks, Sales rank-1 restriction, multi-vehicle and `DEC-HOLD-001` continue to apply.

### Proposed durable state transitions (new schema/API require approval)

```text
User clicks Confirm + trusted 5-gate and source/roster recheck
    -> LOCAL_HOLD_VERIFIED (not an APPROVED order)
    -> RESERVE_REQUEST_RECORDED (durable unique order/line/version/key, outbox)
    -> WMS_STATUS_UNKNOWN (timeout/no ACK; same-key STATUS lookup only)
        OR WMS_REJECTED (including partial/mismatched ACK)
        OR WMS_ACK_VERIFIED (all SKU/warehouse/unit/qty/keys match)
    -> WMS_REFRESH_PENDING (immediate read requested; old batch may still omit reserve)
        -> RECONCILED (specific reservation-inclusion version proof)
        -> FINALIZE_PENDING (fresh gates/locks rechecked; DB transaction retries)
    -> CFO_APPROVED + COMMITTED + audit + notification outbox in ONE local transaction
```

This is a proposed **saga**, not a cross-database transaction and not the current `ops.order_status` enum. No new externally visible order status, error code, migration or response field is authorized by this review. A pending reservation must **not** be surfaced as `APPROVED` via the existing endpoint. If the pending status cannot be safely expressed with an approved contract, the API must fail closed and the WMS feature stays disabled.

**Concurrency & recovery:**
1. Persist a deterministic, stable, order-version-scoped external intent **before** an external side effect; uniquely bind market, order, warehouse, original order lines, native SKU, unit, quantity, mapping version, WMS stock version and idempotency key. Use DB row/advisory locks and `UNIQUE` constraints with an owner-approved migration. One intent per order stock need, **not per vehicle**, per UI retry or per plan alternative. Replan requires explicit supersession/release semantics.
2. The worker sends once or queries `STATUS` with the **same** key after lost response. Never issue an unrelated second reservation on timeout; reject partial/mismatched ACK. If the WMS API cannot promise atomic whole-order reserve and idempotent status lookup, do **not** enable automatic confirmation.
3. Save matched WMS reservation identity/status in an independent durable CFO transaction. If WMS ACKed but the CFO DB commit fails, recovery must query WMS using the stable pre-existing intent, not infer failure and issue a second reserve. Unmatched external stock is conservatively blocked until linked; once safe, compensate by WMS idempotent release only if the reviewed API permits and the order is not already physically issued.
4. On ACK, **immediate** WMS stock refresh must be requested. If WMS publishes an older batch, retain the known-unincluded reservation exposure as a conservative protection (or block additional approvals). Do not infer inclusion from `as_of`, available delta or a later periodic sync. Only explicit version/identity evidence clears that protection. When WMS reserve is included in `wms_reserved`, do **not** subtract that reservation again from ATP.
5. If CFO DB finalize fails, keep the external reservation tracked and `FINALIZE_PENDING`; no customer confirmation or `APPROVED`. Compensation/retry must be idempotent and alert IT. Avoid holding SQL locks across arbitrary WMS HTTP timeouts; revalidate locks/gates again before finalization.
6. Hold expires: the **local unapproved plan** must expire; external reservation already ACKed requires a separate verified release/compensation decision. Never turn an expired hold into an approved plan, even with WMS stock reserved. Cancellation/replan likewise must distinguish local tentative hold, confirmed external WMS reserve and physically consumed stock. Never reserve a second time for the second delivery vehicle or a repeat `DELIVERED` stop.

### Reserve request validation and WMS response requirements

The separate `wms_reservation_readiness.py` prototype checks only prospective trusted source/WMS identifiers and exact decimal conversions plus exact response ACK and inclusion matching. It performs **zero** external/network/database I/O, cannot authorize an approval and is **not integrated** into `ApprovalService`. Dev 2 must verify POS SKU ↔ WMS SKU relation, original `order_line.local_sku`, market/warehouse native IDs, global mapping version/effective date, fixed sale/stock units, order quantities, duplicate local SKU mappings, scope/evidence version, source batch id/version and authoritative accepted reservation lines. Never invert global→SKU by selecting first match; never infer physical independence or build a stock pool. Never auto-round fractional WMS units.

**Dev 2 interface/contract blockers before implementation:** authenticated WMS `RESERVE`, `STATUS` by external key, `RELEASE/ADJUST` and authoritative status/conflict/revision semantics; atomic all-or-none behavior; accepted-line detail; WMS-native market/warehouse/SKU/stock-unit conversion; idempotency storage duration; immediately readable full stock batch and reservation-specific inclusion proof; 503/error handling and rate limiting. No WMS write credentials, production activation or fake test adapter until explicit deployment/security approval.

## 2. Stock Admin #148 and migration ordering

Retain S1–S5: market-scoped, revocable `StockAdminGrant`; author ≠ approver; 30-day independent evidence; immutable scope versions selected by trusted `batch.as_of`; coverage of **every** expected (warehouse, SKU), explicit zeros allowed, incomplete batch fails wholesale; mapping/unit/scope change invalidates evidence. Stock Admin **does not** acquire physical WMS edit rights.

#148's `grant_admin` requires an existing active grant and thus does not implement first-grant bootstrap. Its test's direct SQL bootstrap is not a production authenticated path and does not record the required audit. **Proposed prerequisite (needs reviewed identity/DTO/contract):** Owner-delegated System Admin authentication, explicit one-time market/beneficiary/capability/reason grant, no self-grant, append-only audit in the same transaction, advisory lock and unique initial grant guard; bootstrap may not silently fall back to generic `admin` or seed. No first-grant API is authorized by this review.

#129 provides migration **0012** for unique POD by trip_stop; #148 proposes **0013** with `down_revision = 0012`. Integration order is therefore #129 before #148, with real fresh/seed PostgreSQL upgrade and downgrade tests; stop on competing Alembic heads or data that violates new POD uniqueness. Do not drop existing tables or edit PR owners' migrations without coordination.

## 3. Transfers #127: WMS owns physical movement

The existing `confirm-source` and `receive` endpoints create/close CFO `inbound_shipment(source=transfer)` as if a warehouse-manager click were physical WMS issue/receipt. That semantics is superseded by DEC-WMS-READONLY-20261109. **Block merge/production activation pending an approved contract revision.** GET transfer suggestions may remain read-only. If any CFO action is retained, label it a non-authoritative request/intent; do not write physical stock or require a duplicate WMS documentary reconciliation queue. Maintain `planning_context.confirmed_inbound` exclusion of transfer-sourced pending inbound: no synthetic stock additions or timestamp-based WMS inclusion. `cancel` must never reverse WMS goods without a separate WMS contract; continue reason+audit/idempotency for CFO-only intent.

## 4. GPS #129 + #137: live immediately revoked, history seven days

Current #129 terminal branch calls `gps_service.purge_trip_on_terminal`; #137 implementation deletes valid history immediately and `purge_expired` deletes at shift end. DEC-GPS-RET-20261109 supersedes both destructive operations. On actual terminal trip/shift end, reject new/late offline device points and revoke live GPS authorization immediately, while preserving legally valid historical GPS for **up to seven days** in a separately protected, case-authorized audit service. Proposed source for expiry anchor: verifiably persisted first terminal trip/valid duty-end time (whichever earlier); no guess from ingestion time. Historical read requires an approved reviewer, case, reason, market/trip scope and immutable access log; no use of the existing broad live Dispatcher endpoint. Dev 2 must implement idempotent scheduled cleanup against the authorized expiry anchor and handle backups/retention; preserve POD, duty log, tachograph and append-only business audit. D8's **07:00/13:00 Europe/Stockholm** reviews are approved, but the scheduler tick/worker itself is not.

## 5. Required real PostgreSQL & integration tests — NOT YET EXECUTED

These are **release blockers**, not claimed passing tests:

- Simultaneous approvals competing for (warehouse, WMS SKU), vehicle, driver or daily staff; unique persisted reservation intent, at most one final approval; row/advisory lock and deadlock ordering validated.
- Same UUID + same payload replay; same UUID + different payload conflict; multi-vehicle order reserves stock once, not per trip.
- WMS timeout/lost ACK -> STATUS lookup with same key; partial ACK/wrong warehouse/WMS SKU/units/qty -> never `APPROVED`; delayed stock publish doesn't remove protection.
- WMS ACK success + simulated local PostgreSQL commit failure -> recover reserved external ID without double reserve; compensation/release failure remains visible, no false success.
- Source line one-to-many global SKU reverse mapping; fixed stock-unit precision; unsupported fractional quantity and unconfirmed/incompatible mapping fail before outbound request.
- Batch 503/stale/incomplete; only trusted inclusion identity clears duplicate-accounting protection; reservation consume after actual physical issue.
- Cancellation/replan/expired local hold and rerun; FIFO fairness and 5-gate/56-day safety.
- #148 bootstrap delegated System Admin and concurrent dual bootstrap; grant lifecycle, audit, market isolation, migration 0012→0013 against seed/fresh PostgreSQL.
- GPS multi-vehicle/trip-stop terminal, immediate live revoke, historical survivor, 7-day cleanup, denied cross-market/unauthorized case, invalid offline replay, audit/POD/duty preservation.

**Status:** Unit tests for the pure WMS readiness checks are included with this draft. Full PostgreSQL/Source/WMS integration cannot pass until DB/API state and Dev 2 verified WMS transport are reviewed. This file deliberately changes no approved DDL/endpoint/enum/action code. Existing PR #127/#148/#129 are left unmodified; review comments were placed directly on those PRs and #121/#137/#151.

**Assumptions:** reviewed. No new owner-approved decision IDs or changes; #155 owner decisions remain authoritative. No WMS production writes enabled, no auto-merge.
