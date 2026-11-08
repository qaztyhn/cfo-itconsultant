# Stock batch transport and normalization — handoff

Covers the merged #111 (adapter + normalizer) and this update for the owner decisions of 2026-11-08:
**DEC-SRC-Q10-SKU-001**, **DEC-SRC-Q9-ERROR-001**, **DEC-CFO-STOCK-SCOPE-001** (SKU scope, option B) and
**DEC-CFO-STOCK-INDEPENDENCE-001** (aggregate only verified independent stock, option A). This is a review checklist,
**not** approval. Nothing here writes to the database or to the source.

## Agreed DTO (Source → CFO adapter)

`GET /stock` → `200 {"as_of", "batch_id", "item_count", "items": [{"warehouse_code","sku","on_hand","reserved"}]}`
or `503 STOCK_UNAVAILABLE`. No pool or alias field; unknown fields are refused (`extra = forbid`).

## `normalize_stock(snapshot, mappings, declared, *, scope, verified_independent=())` (pure)

- **Scope (B).** Only SKUs in `scope` are normalized; rows outside it are ignored and never block. The scope must be fixed
  before the sync and is never derived from which SKUs of the batch map. An in-scope SKU that is unmapped, unconfirmed,
  unit/factor-inconsistent or not exactly representable in NUMERIC(12,3) rejects the **whole** batch (no partial result).
- **Independence (A).** Several in-scope SKUs of one warehouse for one global product are summed after conversion **only**
  if all of them lie inside one `verified_independent` group; the default is empty, i.e. fail closed. Independence is not
  inferred from different codes, the same product or equal quantities, and is not transitive across groups.
- Each SKU is converted once with `units_to_base`; warehouses are never merged; batch markers, duplicate keys and aware
  `as_of` are checked for every row, in or out of scope.

## Still open (the owner has **not** decided these; nothing is invented)

1. **Where the SKU scope is declared** (market/pilot), its version and validity, and how it is checked against
   `batch_id` / `item_count` / `as_of` and extended.
2. **Evidence and authority for "verified independent"**, how it is audited and versioned, and when it lapses if the
   mapping or source stock changes.
3. **An in-scope SKU with no row in the batch** is not rejected by the normalizer (the expected warehouses are unknown);
   a persistence layer replacing a snapshot must treat a missing `(warehouse, product)` as *unknown*, not zero.
4. Persistence (atomic full replacement of `ops.stock_snapshot` per market/warehouse/batch), keeping the previous
   snapshot on `StockUnavailable`, the freshness gate and the T07 stock writer (`ingest_stock` still refuses to run).

No whole-market freshness, full US-INT-03 or E2E acceptance is claimed.
