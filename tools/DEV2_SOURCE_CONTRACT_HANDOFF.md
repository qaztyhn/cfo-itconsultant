# D1 source contract candidate — 2026-11-08

Review order: #97 receiving calendar → #98 sales/store references → #100 DRAFT creation → #102
validation/submit → #104 PUT/cancel (including Linux fixture fix) → #105 complete stock batches →
this full-contract candidate. Use merge commits and retarget/recheck each stacked PR after its base.

`source_system/openapi.yaml` is now generated from implemented routes, not hidden stubs. It includes
the six paginated feeds, complete stock batch markers (`batch_id`, `item_count`), typed
POST/PUT/validate/submit/cancel bodies,
shared error envelope, source API-key security and public health 200/503. Error shapes and date formats
reflect actual responses; pagination documents X-Total-Count. Handled errors and normal responses
carry one consistent correlation ID. No customer input values are added to technical logs.

The same request/lifecycle/stock tests run on isolated SE and shadow schemas (different configured
calendar timezones); schema factory output must be identical and match the candidate artifact.
`tools/check_openapi.py` comparison is a drift check, **not review approval**. Dev 1/3 must review this
candidate before treating it as the agreed release baseline. CFO OpenAPI remains a separate artifact.

## Integration still required

- Dev 1/2: consume both SUBMITTED and CANCELLED source feeds with durable checkpoints, idempotent
  versions and overlap. Source writes never directly change CFO, release holds, approve or replan.
- Dev 1: review allowed CFO cancellation transitions, pre-dispatch suggestion-only source edits,
  committed-resource protection and post-dispatch escalation. No automatic routing/approval.
- Dev 1/2: review one-fixed-unit-per-SKU stock normalization and full snapshot replacement. No
  `physical_stock_pool_id`: each published stock batch contains at most one row per
  `(batch_id, warehouse_code, sku)`. Unknown/unpublished stock is HTTP 503
  `STOCK_UNAVAILABLE`, never a 200 empty snapshot. A published complete zero-row batch is valid 200.
  Multiple local SKUs mapping to one global product must not be combined without verified
  independent inventory. CFO ingestion/persistence and freshness gates remain separate work.
  Source publication preserves existing historical rows on staged upgrades.
- Dev 3: use typed payloads/expected_version/idempotency key, errors and official source calendars in POS;
  do not send server-owned coordinates/status or arbitrary notification content.
- Full seeded scenario/golden/E2E acceptance still depends on the engine/execution integration.
- Earlier read-only baseline proposal #99 must be reconciled with this implemented write/batch surface;
  do not reintroduce hidden implemented routes or replace the candidate with a partial stub baseline.

Assumptions: reviewed; DEC-SRC-D1-001; none new. No cloud deployment (D6 deferred) or new scheduler (D8 pending).
