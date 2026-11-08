# SRC-Q9 / SRC-Q10 — coherent stock batch and fixed-unit SKU model

**Status: revised at the project owner's explicit request, 2026-11-08. Docs-only proposal for Dev 1 + Dev 2 joint schema/API review; no code or migration.**

**IMPORTANT — revision history:** this document replaces the earlier PR #101 draft named `SRC_Q9_Q10_STOCK_BATCH_POOL.md`. The older pool model was rejected after owner clarification. **The current design DOES NOT use or require `physical_stock_pool_id` or physical-stock-pool grouping.** It supersedes the earlier pool/alias proposal and the Q10 pool-specific portion of `DEC-SRC-D1-001`. Current owner decision: `DEC-SRC-Q10-SKU-001` ([ledger](../ASSUMPTIONS.md#dec-src-q10-sku-001--mỗi-sku-một-đơn-vị-tồn-kho-chuẩn-không-physical-stock-pool)). Q9's already approved batch/completeness principle remains unchanged.

**Scope:** Q9 = authoritative whole-source stock snapshot; Q10 = consistent unit and unique quantity **per (warehouse, SKU)**. CFO always reads from Source; never writes back to POS/WMS. Q8 receiving work proceeds separately. No D6 cloud work or D8 scheduler enabled.

## Why the old Q10 design was wrong for this project

The previous version proposed two SKU rows pointing at the same physical pool, such as 100 bags and five pallets of 20 bags. **Numerical equivalence does NOT establish that they are the same physical stock.** The owner confirmed that each product SKU has **one stable unit of inventory** and rejected introducing speculative shared-pool inventory records. Do not deduce identity or shared inventory from quantity or packaging conversion.

- A SKU has a stable `sale_unit` / stock unit recorded in the source product catalogue and a valid `units_to_base` conversion to a canonical CFO/global base unit.
- Source stock uses the same declared unit for that SKU in every batch, warehouse and row. Changing a SKU's unit requires an explicit new SKU or controlled data migration and review; do **not** silently reinterpret existing snapshots and orders.
- If a customer orders a different packaging quantity, the POS/Source converts that **order quantity** to the product's declared SKU unit; do not create a second stock row merely to represent a different packaging option.
- Different SKUs are not inferred to share or duplicate stock. If multiple SKUs happen to map to the same CFO `global_product_id`, CFO may aggregate only when each is **confirmed to represent an independent source inventory** under an explicit, reviewed mapping contract. If the relationship is unknown, **fail closed** for that product/warehouse, do not blindly sum or arbitrarily deduplicate. No pool table/ID is introduced for this.
- At a given source warehouse and published batch, **there can be only one row per SKU**. A duplicate is a malformed batch, not additional inventory.

Example: `CEM-25` declared stock unit = **bag**, source has 100 bags. An order of five pallets × 20 bags uses 100 bags of `CEM-25`; the source still stores **one** stock row with 100 bags. There is no duplicate `CEM-PALLET` stock row created for the same physical stock.

## Q9 — published stock batch (unchanged owner-approved principle)

**Required behavior:** one authoritative `as_of` for the whole snapshot, atomically published, and an explicit marker that the entire expected snapshot was received. A complete published **zero-row** batch means inventory is zero **for that source-instance snapshot's scope**; no published batch means **unknown/unavailable**, never zero.

Proposed additive source model (names/DDL to be reviewed with Dev 1):

```sql
src_stock_batch (
  batch_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  as_of         timestamptz NOT NULL,     -- one authoritative snapshot instant
  status        text NOT NULL CHECK (status IN ('loading','published','failed')),
  expected_rows integer NOT NULL CHECK (expected_rows >= 0),
  published_at  timestamptz,
  created_at, updated_at,
  CHECK ((status = 'published') = (published_at IS NOT NULL))
)

src_stock ( -- logical target; migrate existing PK safely, do not reset data
  batch_id      bigint REFERENCES src_stock_batch(batch_id),
  warehouse_code,
  sku,          -- references stable SKU catalogue unit
  on_hand, reserved,
  UNIQUE (batch_id, warehouse_code, sku)
)
```

There is **NO `physical_stock_pool_id`** anywhere in Q9/Q10 target DDL or `/stock` DTO.

- Publish in **one database transaction**: stage exact items → verify expected row count, unique `(warehouse_code, sku)`, SKU exists, stable unit and valid conversion → mark batch published. If validation fails, roll back / mark failed; **never** serve a partial batch.
- `GET /stock` serves only the **latest completely published** batch (highest `as_of`, then `batch_id`). It must not mix batches or compute the response's `as_of` using `min/max(row.as_of)`.
- An empty published batch is a valid explicit statement. If **no completed/published batch exists** (including when all batches are still loading or failed), Source responds with **HTTP 503 `STOCK_UNAVAILABLE` — explicitly approved by the owner on 2026-11-08 as `DEC-SRC-Q9-ERROR-001`**. This is a **source-only** error, distinct from a published complete empty batch (valid `200` with `items=[]`). If a prior published batch exists while a newer batch fails, `GET /stock` may still expose only the latest **published** batch with its real `as_of`; CFO must check freshness, not pretend the older snapshot is fresh.
- The CFO adapter treats unavailable as a failed stock sync; do not overwrite the last successful snapshot with `[]`. Historical snapshot may be retained only as historical/auditable data, **not** silently promoted into a fresh/current commitment; stock-freshness gate must fail closed if stale/unknown.
- Legacy `src_stock` rows have no trustworthy completeness marker. Keep them isolated/unpublished while migrating. The initial `batch_id` cannot be made globally NOT NULL over existing rows without a staged migration; do not create fake published snapshots. Preserve manual source changes.
- A published batch cannot be changed silently; new stock must be a **new batch**, with appropriate audit/provenance. Source batch publication is internal, not a public POS stock write route.

Proposed additive `GET /stock` DTO:

```json
{
  "as_of": "2026-11-08T09:00:00+01:00",
  "batch_id": 17,
  "item_count": 1,
  "items": [
    {"warehouse_code": "GBG", "sku": "CEM-25", "on_hand": 100, "reserved": 10}
  ]
}
```

The existing `{as_of,items}` contract remains supported. `batch_id`/`item_count` additions are for provenance and explicit completeness; **no stock pool identity field**.

### Approved Source API behavior for unavailable stock — DEC-SRC-Q9-ERROR-001

Owner explicitly approved option A on **2026-11-08**. When **no complete published batch** is available for the source instance, `GET /api/v1/stock` returns HTTP **503** (after the usual Source authentication) using the existing standardized Source error envelope:

```json
{
  "error": {
    "code": "STOCK_UNAVAILABLE",
    "message": "Stock snapshot is unavailable.",
    "details": {},
    "correlation_id": "<opaque-correlation-id>"
  }
}
```

The response includes `X-Correlation-ID`. Neither error message nor log may echo stock customer/order PII, raw exceptions, or internal diagnostics. `200 {"as_of": "...", "items": []}` remains valid **only for a complete, explicitly published empty batch**. Do not confuse this source-specific 503 with `GET /health` (health response keeps its own body), or a normal failed upstream connection in the CFO adapter. On HTTP 503, CFO keeps the previous snapshot for historical/audit reference, reports a source sync failure, and gates new planning on freshness/availability; it does **not** replace stock with zero or re-stamp the old `as_of`.

**Contract tests required (both source instances):** 503 with `STOCK_UNAVAILABLE` for no batch, only loading batches, only failed batches; 200 with `items=[]` for a published zero-row batch; 200 with latest published batch when a newer *unpublished* load fails, preserving the original `as_of`; 503 `X-Correlation-ID` and error envelope; CFO stock safety when stale/unavailable. Production implementation and OpenAPI baseline update belong to later code PR(s), not this documentation PR.

## Q10 — fixed-unit SKU, one row per warehouse and SKU

**Source (Dev 2):**

1. Product catalogue provides an immutable-in-practice SKU identifier, declared stable stock/`sale_unit`, `units_to_base` conversion and `updated_at`. Stock quantities `on_hand`/`reserved` are expressed **in that SKU's declared stock unit**, never a mix of bag/pallet/ton under the same SKU.
2. Enforce `UNIQUE(batch_id, warehouse_code, sku)` at DB level and reject duplicate rows **before publishing**; no sum, no last-row-wins.
3. Verify SKU exists and factor is positive and unambiguous; do not create a stock row for a second packaging representation of the same SKU.
4. Different warehouses have independent stock. E.g. SKU `CEM-25`, GBG=100 bags and STO=200 bags — these remain **separate warehouse inventory** for planning, even if reporting may show 300 bags.
5. A conflicting SKU unit/conversion configuration or duplicate makes the batch invalid/unavailable, not an automatically corrected zero.

**CFO (Dev 1):**

1. Read published batch + declared product unit; convert each verified `(warehouse,SKU)` once to canonical base units using `units_to_base`. Never infer shared-stock aliases by comparing equal converted quantities; **no pool IDs**.
2. Mapping `local_sku → global_product_id` must be explicitly confirmed under existing SKU governance. Multiple source SKUs mapping to one global product are **not automatically additive** unless independent physical inventory semantics are positively verified; if ambiguous, reject/quarantine the affected source snapshot/product and mark stock unavailable for planning. Avoid publishing an apparently complete **partial** replacement missing unresolved inventory.
3. Only after all required rows pass validation, replace CFO stock snapshot consistently per source/warehouse/batch in one transaction; keep `as_of` tied to published batch. Cross-warehouse aggregation is **for reports only**, not proof that a specific delivery warehouse holds all units.
4. If stock sync fails, retain previous successful snapshot for audit, alert IT/Warehouse and enforce stock freshness/availability as a **planning safety gate**. Never disguise a failed batch as a valid zero or fresh snapshot.

## Engineering decisions still required from Dev 1 + Dev 2

These are technical implementation choices **not** new permission to add stock pools:

1. Exact table/column names, safe legacy migration from the current one-row-per-warehouse/SKU table to per-batch rows, and when/how older rows are archived as unpublished.
2. OpenAPI additive fields `batch_id`, `item_count` and the **approved** `503 STOCK_UNAVAILABLE` source-only error contract. The error code/status are owner-approved; the exact migration/DTO details are Dev 1/2 technical-review items.
3. Which source catalogue field is authoritative for the fixed SKU stock unit; how unit changes are versioned; Decimal conversion precision/rounding policy (no float).
4. Dev 1's staging/quarantine and full-replacement boundary for **ambiguous multiple local SKUs mapping to one global product** without inventing any shared-stock pool.
5. Full-batch completeness and freshness gates, with auditable `batch_id`, `as_of` and source instance. Seed one explicit, independently managed stock row per warehouse+SKU; do not manufacture duplicate presentation rows.

## Test plan / acceptance criteria for implementation PRs

- **Q9 source PostgreSQL:** atomic publication, when **no published batch** (including only loading/failed) then `503 STOCK_UNAVAILABLE` with standard error envelope and correlation ID, complete empty batch = **200, items=[]**, newest published selection with tied `as_of` and a later failed load, rollback on malformed rows, repeatable additive migration, legacy rows unpublished, two source instances isolated, nonpaginated GET, authoritative batch timestamp, OpenAPI baseline.
- **Q10 source:** exactly one row per `(batch,warehouse,SKU)`; duplicate rejected; SKU stock unit never changes within a snapshot; stock stays in declared SKU unit; invalid factor/unknown SKU rejected; order quantity expressed in alternate packaging is correctly converted **without introducing an alias stock row**.
- **CFO adapter Dev 1:** per-SKU Decimal conversion, independent warehouses, no blind alias/pool grouping, no last-row-wins; multiple local SKUs to one global requires explicit independence or **fail closed**; invalid/partial source batch does not publish partial CFO replacement; no batch retains prior snapshot as stale only and blocks planning; complete empty batch clears applicable stock scope.
- **Integration:** Source-to-CFO cross-instance contract, DB uniqueness, stable sync provenance, freshness and test showing 5 pallets × 20 bags consume 100 units of a bag-SKU without double counting.

**Not implemented by this PR:** Q9/Q10 schema, source `/stock` publication, CFO adapter changes, contract migration, and E2E. The current endpoint still uses `min(row.as_of)`; this is not Q9-compliant. Dev 1 and Dev 2 should review and coordinate implementation PRs. No auto-merge.
