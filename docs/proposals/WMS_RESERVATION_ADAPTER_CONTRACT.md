# WMS Reservation Adapter — survey, proposed interface and implementation status (Dev 2, 2026-11-09)

Authority: DEC-WMS-RESERVE-SYNC, DEC-WMS-REVERSE-SKU, ASM-WMS-RESERVATION, DEC-WMS-READONLY (all 2026-11-09).
**The WMS reserve capability is an ASSUMPTION. No WMS API, credential or write path is verified or enabled.**

## 1. Contract that really exists today (read-only)

`GET /stock` of the Source/WMS system (source_system, DEC-SRC-Q9/Q10): `{as_of (aware), batch_id (int>0), item_count,
items:[{warehouse_code, sku, on_hand, reserved}]}`, one row per (warehouse, SKU) in that SKU's fixed stock unit,
503 `STOCK_UNAVAILABLE` when no complete batch exists. Mapping data: `ref.product_se` (`sale_unit`, `units_to_base`,
`global_product_id`, `mapping_status`). **Nothing else is known**: no reserve/status/release endpoint, no reservation id,
no inclusion marker, no auth scheme. Physical on_hand is never changed by CFO.

## 2. Proposed (UNVERIFIED) port — `app/adapters/wms_reservation.py`

| Operation | Purpose | Notes |
|---|---|---|
| `reserve(request)` | reserve exact WMS SKU/warehouse/qty for one approved plan | stable `idempotency_key`; WMS checks availability atomically across all channels |
| `status(market, key)` | recover after timeout/lost ACK | never a blind duplicate reserve |
| `release(market, reservation_id, key)` | compensate partial/failed commit, cancel/replan | consume/adjust semantics need the real WMS |

ACK needed from WMS: `reservation_id`, `status`, accepted lines (SKU, warehouse, qty), `revision`, and ideally
`reflected_in_batch_id` (the stock batch known to include the reservation) — **assumed field**, needed to lift the
conservative pending protection. Without it protection is kept (no double subtraction, but also no release).

## 3. Implemented in this PR (tests against an in-memory FAKE WMS only)

- `wms_sku.resolve_reservation_lines`: reverse SKU from the **original order line**, explicit confirmed POS↔WMS relation
  per market/warehouse (POS==WMS never assumed), confirmed mapping *and version* match, warehouse carries the SKU, exact
  stock-unit conversion (no rounding), one-to-many never guessed/pooled, any doubt → whole request rejected.
- `wms_reservation`: deterministic idempotency key per (market, order, plan, exact lines) — a 2nd vehicle/retry reuses it;
  ACK must equal the request exactly; reject / partial / mismatch (compensating release) / timeout → status lookup /
  unknown → fail closed; `DisabledWmsPort` is the default (no write reachable).
- `stock_accounting.compute_availability`: tentative holds subtract; WMS-acked reservations subtract only until a batch
  *version proof* shows inclusion; later `as_of` alone is never proof; missing row = unknown.
- `stock_refresh.refresh_after_ack`: immediate controlled re-read (bounded attempts), rejects 503/partial/older batches,
  never moves checkpoints; does not replace the 5-min poll or Sales Sync Now.
- D8: `app/jobs/ops_review_slots.py` 07:00/13:00 market-local slot keys (DST-safe, idempotent). **No cron activated.**

## 4. Not implemented / blocked

| Item | Blocker |
|---|---|
| HTTP adapter for reserve/status/release | real WMS API, auth and credentials unknown; owner has not approved deployment |
| POS↔WMS SKU relation data source | no verified table/feed; `WmsSkuRelation` must come from a reviewed source |
| `reflected_in_batch_id` | field not confirmed by WMS |
| Reservation ledger, outbox/saga for "WMS ACK ok but CFO commit failed", hold lifecycle | Dev 1 (#148/#129/#127): persistence, approval sequencing, audit |
| Real-PostgreSQL tests of the ledger | nothing persisted by this PR; belongs with Dev 1's ledger |

Dev 1 handoff: approval flow calls `build_request` → `reserve_with_recovery`, persists ACK (id, revision, lines,
`reflected_in_batch_id`) and the key in the approval transaction/outbox, then calls `refresh_after_ack` and feeds
`compute_availability`. Never enable a real port before the owner approves the narrow reserve/status/release exception.
