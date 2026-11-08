# Stock batch transport and fixed-SKU normalization — handoff

Redesign of the rejected #107 (physical stock pool) under **DEC-SRC-Q10-SKU-001** and **DEC-SRC-Q9-ERROR-001**.
This is a review checklist, **not** approval. Nothing here writes to the database or to the source.

## Agreed DTO (Source → CFO adapter)

`GET /stock` → `200 {"as_of", "batch_id", "item_count", "items": [{"warehouse_code","sku","on_hand","reserved"}]}`
or `503 STOCK_UNAVAILABLE`. No pool or alias field. Unknown fields are refused by the adapter (`extra = forbid`).

## What the adapter and normalizer do

- `RestMarketAdapter.fetch_stock`: requires `batch_id` (> 0, strict int), `item_count` (≥ 0), aware `as_of`, no duplicate
  `(warehouse_code, sku)`, `item_count == len(items)`. `503 STOCK_UNAVAILABLE` → `StockUnavailable` (a `SourceReadError`).
- `normalize_stock(snapshot, mappings, declared)` (pure): the source-declared `sale_unit` / `units_to_base` must equal the
  confirmed CFO mapping; each SKU is converted once; quantities must be exact in NUMERIC(12,3); different warehouses stay
  separate; **any** problem rejects the whole batch (no partial result).

## Decisions for Dev 1 / owner (not invented here)

1. **Unmapped or unconfirmed SKU in the batch rejects the whole snapshot.** This is the literal reading of "never publish an
   apparently complete partial replacement". While pending SKUs exist in the source, stock sync would therefore fail; if the
   owner prefers to skip and report unmapped SKUs, that needs an explicit rule.
2. **Several SKUs of one warehouse mapping to one global product are not summed.** There is no verified-independence contract
   yet; define how independence is confirmed before enabling aggregation.
3. Persistence (full replacement of `ops.stock_snapshot` in one transaction per source/warehouse/batch), keeping the previous
   snapshot on `StockUnavailable`, durable checkpoints and the freshness gate are **not** in this slice.
4. Update 2026-11-08: #105 and #111 are now both merged and agree on this fixed-SKU/503 DTO. The earlier
   producer mismatch is resolved. Old `{as_of, items}` bodies are still refused on purpose.

No whole-market freshness or full US-INT-03 acceptance is claimed.

T07's subsequent persistence/availability work is documented in [T07_INGESTION_HANDOFF.md](T07_INGESTION_HANDOFF.md).
The transport-only scope described above is historical; the new writer uses complete batch replacement and a
latest-run availability helper, while production planning/approval consumption remains an explicit handoff.
