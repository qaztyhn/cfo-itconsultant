# SRC-Q9 / SRC-Q10 — stock batch and physical stock pool: design proposal

**Status: proposal for Dev 1 + Dev 2 agreement. No code and no migration is written from this document.**
Owner decision already taken: DEC-SRC-001 (Q9/Q10 direction) and DEC-SRC-D1-001 D1-D (`docs/decisions/DEC_SRC_D1_APPROVED_20261108.md`).
Order of work set by the project owner (2026-11-08): Q8 → **Q9 + Q10** → order writes → CFO checkpoint / cancellation / replan.
`05` and `06` must be updated in the implementation PR together with the migration, tests and OpenAPI baseline.

## Why this needs a joint decision

The source key of a stock row is `(warehouse_code, local sku)`; the CFO key is `(warehouse_id, global_product_id)`
(`ops.stock_snapshot`, `05` §6). Today `GET /stock` returns every row with `as_of = min(row.as_of)`, which is neither a batch
marker (Q9) nor safe when several local SKUs describe the same physical inventory (Q10). The source migration, the `/stock` DTO
and the CFO adapter/normalisation must be consistent, and the last two belong to Dev 1.

## Q9 — published batch with a completeness marker

Proposed source tables (additive; names to be confirmed in review):

```sql
src_stock_batch (
  batch_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  as_of         timestamptz NOT NULL,          -- one authoritative instant for the whole batch
  status        text NOT NULL CHECK (status IN ('loading','published','failed')),
  expected_rows integer NOT NULL CHECK (expected_rows >= 0),   -- completeness marker; 0 is a valid complete batch
  published_at  timestamptz,
  created_at, updated_at,
  CHECK ((status = 'published') = (published_at IS NOT NULL))
)
src_stock (  -- existing table, extended
  batch_id bigint NOT NULL REFERENCES src_stock_batch,
  warehouse_code, sku, physical_stock_pool_id text NOT NULL, on_hand, reserved,
  PRIMARY KEY (batch_id, warehouse_code, sku)
)
```

- **Publish is one transaction** (`publish_stock_batch(as_of, items)`; a source-internal function/CLI, there is no public write
  endpoint for stock): insert rows → verify `count(rows) = expected_rows` and the Q10 checks → set `status = 'published'`.
  Any failure rolls back or leaves `failed`; a half-loaded batch is never readable.
- `GET /stock` serves the **latest published batch** (highest `as_of`, then `batch_id`). It never mixes rows of two batches and
  never uses `min/max(row.as_of)`.
- **Empty published batch** (`expected_rows = 0`, published) is authoritative zero stock for that source instance.
- **No published batch, or only `failed`/`loading`** → stock is **unavailable**, never zero. Proposed response:
  `503` with the standard error body and a new source-only code `STOCK_UNAVAILABLE` (needs approval, like `NOT_IMPLEMENTED` in #99).
  The CFO adapter must treat it as a failed stock sync (`SourceReadError`), keep the previous `ops.stock_snapshot`, and let the
  existing freshness job raise its alert.
- Rows already in `src_stock` before the migration have no batch: they are **not served** (quarantined) until a batch is
  published, so the upgrade can never silently publish an incoherent snapshot.

Proposed `GET /stock` DTO (additive; `{as_of, items}` stays valid for the current adapter, which ignores extra keys):

```json
{ "as_of": "…", "batch_id": 17, "item_count": 2,
  "items": [{ "warehouse_code": "GBG", "sku": "SE-CEM-25", "physical_stock_pool_id": "GBG-P-0042", "on_hand": 800, "reserved": 20 }] }
```

## Q10 — physical stock pool and anti double counting

- `physical_stock_pool_id` identifies **one physical inventory at one warehouse**. Several local SKUs (aliases / presentations)
  of the same inventory share the pool id; independent inventories have different ids. The id is source-owned, opaque, unique
  per `(warehouse_code, pool)` in a batch.
- **Source-side check at publish (rejects the whole batch):** inside one `(batch, warehouse, pool)` every row, converted to base
  units with the product's `units_to_base` (`qty × units_to_base`), must give the same `on_hand` and the same `reserved`.
  A pool whose aliases disagree is ambiguous: it is **quarantined by failing the batch**, never resolved by last-row-wins.
- **CFO-side normalisation (Dev 1, adapter):** per batch and warehouse, for each pool take the converted quantity **once**
  (not per alias); map the pool's SKUs to `global_product_id`; if the SKUs of one pool map to different global products, or
  any SKU is unmapped, quarantine the pool (alert, no stock row for it); distinct pools of the same global product **sum**.
  Result is written as a full replacement of `ops.stock_snapshot` for that source/warehouse in one transaction, with the
  batch `as_of`.
- The units conversion factor travels in the product feed (`GET /products`, `units_to_base`), so the stock DTO stays quantities
  in local sale units and the pool id.

## Decisions needed from Dev 1 and Dev 2 before any code

1. Table/column names above and the `STOCK_UNAVAILABLE` code (or another agreed unavailable signal).
2. Whether the pool consistency check is **exact equality** after conversion or has a tolerance (proposal: exact).
3. Where CFO records the batch id / quarantined pools (new `stg` rows vs `stg.sync_reject`).
4. Where freshness is judged (batch `as_of` against `MarketConfig`, existing stock-freshness job).
5. How a legacy source without pool ids is seeded (proposal: explicit pool id per SKU in the demo seed; no guessing).

## Test plan for the implementation PRs

Source (PostgreSQL): publish atomicity and rollback; zero-row published batch; no batch / failed / loading batch → unavailable;
latest-batch selection with equal `as_of`; pool aliases consistent vs inconsistent (batch rejected); two independent pools;
unit conversion; legacy rows not served; additive upgrade repeatable; OpenAPI baseline updated; two-instance contract test.
CFO adapter (Dev 1): alias counted once, independent pools summed, unmapped / conflicting pool quarantined, unavailable keeps the
previous snapshot, empty published batch replaces stock with zero rows.

**Not claimed:** nothing here is implemented; the current `GET /stock` (minimum row `as_of`) is still **not** Q9-compliant, and the
Source contract and E2E are not complete.
