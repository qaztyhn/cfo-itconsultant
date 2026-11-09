# Disposable WMS native mapping + reserve/status/release contract (DEV 2 P0)

**Status: DRAFT, SYNTHETIC ONLY. No real WMS endpoint has been approved.** This standalone loopback test service is **not** registered with CFO routes or production WMS and does not approve an order. It exists to validate the missing transport and evidence contract for Dev 1 PR #213, not to bypass #207/#210/#213. Production remains `DisabledWmsPort`.

The service is disabled unless `APP_ENV=test`, `DEMO_DISPOSABLE=1`, `APP_NOW=2026-11-04T10:05:00+01:00`, `WMS_PRODUCTION_ENABLED!=1` and a private API key are all set. Standalone main listens **only on 127.0.0.1:8188**, with a required *on-disk* SQLite database. The reserve request must match a pinned synthetic `source_orders[]` record for `source_ref`, `order_id`, `plan_id`, `source_version`, line ID, original POS SKU, warehouse and exact quantity; this prevents a caller-declared version from serving as provenance. Such pinned offline evidence does not establish an authoritative live POS version. The caller must configure absolute `SYNTHETIC_WMS_DB`, `SYNTHETIC_WMS_FIXTURE` and `SYNTHETIC_WMS_API_KEY`; the fixture is not mutable after the first boot. A separate persistent volume is required if run in a container; this PR does not integrate or expose a new Docker Compose production service.

## Reviewed synthetic-only wire API

- `POST /v1/reserve`: `X-Demo-WMS-Key` authentication; `market`, `order_id`, `plan_id`, `source_version`, stable `idempotency_key` and `source_ref`; `lines[]` carry original `order_line_id`, `pos_sku`, *explicitly mapped* `wms_sku`, `warehouse_code`, `wms_unit`, `mapping_version`, and exact decimal `quantity`. Server checks each against a confirmed, market/warehouse-specific mapping and immutable pinned synthetic Source order/line/source-version evidence. No arbitrary inverse global-product lookup, no inferred POS/WMS equality and no partial allocation.
- `GET /v1/status/{market}/{request_key}`: persistent same-key lookup after timeout or restart, never blind duplicate reserve.
- `POST /v1/release`: `reservation_id`, market and `<original-key>:release`; idempotent compensation. Physical `on_hand` stays unchanged.
- `GET /v1/stock`: returns **all** native `(warehouse, wms_sku, wms_unit)` records, `complete`, `item_count`, immutable `batch_id`, `as_of`, reserved and on_hand, plus `included_reservation_ids`. Payload SHA-256 and HMAC-SHA256 over canonical response bind inclusion to the authenticated test service. `verify_batch` must reject a missing ID, modified quantity, invalid signature or incomplete batch. This is synthetic integrity only, **not** cryptographic proof from an unknown real WMS.

SQLite `BEGIN IMMEDIATE` serializes competing reserve requests and makes available-to-promise checks/updates atomic. Identical keys replay; a changed payload conflicts. Reservation status survives process restart, including compensation, with no auto-approval. A new batch version is published only after atomic reserve/release; `on_hand` never decreases for a reservation.

### Required integration gates *not* supplied by this slice

1. Dev 2 / Owner must verify **actual source POS order-line/version provenance** and confirm the true native WMS API, units, SKU crosswalk and effective mapping from the source of record. Current fixture mappings are deliberately invented *synthetic* examples, not authority to send a real reservation.
2. Dev 1 must connect persisted `ops.wms_reservation_intent` to this port **only** after the authorized five-gate confirmation. In no case can the client provide SKU evidence directly.
3. The governed CFO `ops.stock_snapshot` writer cannot yet ingest native batch inclusion proofs and safely account for already included reservations; it must be extended under approved stock-scope grants and independently verified effective SKU coverage. This test-only service must **not** write to CFO stock balances.
4. The approved source `GET /stock` batch exists, but the disposable setup intentionally skips CFO stock ingestion because the market scope approval is not bootstrapped. Therefore Planning 409 `RESOURCE_CONFLICT` (missing/stale stock) remains unresolved until genuine governed ingestion is verified.
5. Approval/recovery, replan, loss of WMS ACK, release and DB commit failure require audited exactly-once E2E against the real PlanningService and PostgreSQL. **Final APPROVED/WMS ACK remain BLOCKED.**

Review target: Dev 1 on #213 plus Owner. Do not merge until CI green and contract approved. Existing Sales Sync #204 is already merged and untouched.
