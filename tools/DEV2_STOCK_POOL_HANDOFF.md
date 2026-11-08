# D1 physical stock pool normalization — 2026-11-08

Depends on source producer #105 for `{as_of,batch_id,complete,row_count,items}` and explicit warehouse/SKU
`physical_stock_pool_id`. REST transport now rejects absent/unpublished/non-boolean markers, bad counts,
unknown pool IDs and invalid snapshots; published complete empty batches remain distinct from unknown.

`adapters.stock_pools.normalize(snapshot,mappings)` is exact and has no DB writes or country branches:

- Multiply source sale-unit quantities by confirmed SKU `units_to_base` using Decimal arithmetic.
- Group aliases by **warehouse + physical pool**; every alias must map to the same global product and
  identical converted on_hand/reserved. Count that physical pool once.
- Sum only independent pools into warehouse/global-product totals; return pool provenance and batch/time.
- Quarantine the batch on missing/unconfirmed mapping, ambiguous/disagreeing pool, duplicate source key,
  nonfinite/negative values, or a value not exactly representable in existing NUMERIC(12,3). No rounding
  that might invent stock; no blind summation or last-row-wins. Caller must decide reviewed partial-run
  handling rather than silently discarding rejected physical pools or marking the full feed fresh.

Before production persistence, Dev 1/2 must review warehouse/market scope, mapping freshness and base-unit
identity, rejection/partial-batch behavior, zero-row safe replacement, durable checkpoints/overlap,
row-level provenance and the existing stock schema's numeric scale. No stock snapshot is written by this
component. It does not claim full US-INT-03, whole-market freshness or golden-scenario acceptance.

Compatibility: old raw snapshots lacking explicit complete/batch/pool markers are intentionally refused
under the newly approved D1-D; don't use a legacy min(row.as_of) snapshot as complete inventory.
Assumptions: reviewed; DEC-SRC-D1-001; none new. No source writes or automatic mapping/approval.
