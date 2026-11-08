# Stock batch transport and fixed-SKU normalization — handoff

## Current T07 contract status — 2026-11-08, main 361bd73

This section supersedes earlier stock-persistence and pending-PR statements below.
PRs #105, #106, #111 and T14 #117 are merged. T07 runner/reference/order PRs #115,
#116 and #118 were merged by the owner. Scheduler #119 and stock-readiness #121
remain review work; no automatic merge is enabled.

DEC-CFO-STOCK-SCOPE-001 requires an explicitly fixed CFO SKU scope before ingestion;
confirmed mappings and the Source batch cannot define that scope implicitly.
DEC-CFO-STOCK-INDEPENDENCE-001 requires verified physical independence before summing
SKUs. Scope/evidence storage, versions, effectivity and authority are not yet contracted.
PR #120 is a pure-normalizer proposal, not an approved persistence repository.

Accordingly the earlier whole-market stock replacement is withdrawn. Production
scheduler runs customers, products, orders, inbound and fleet only. Explicit stock
CLI diagnostics record a failed run/reject (STOCK_SCOPE_NOT_CONFIGURED), preserve all
cached stock and commitments, and never advance the checkpoint. A complete empty
Source batch also cannot clear CFO stock without the scoped contract. Stock usability
returns false; this is a dependency gate, not implemented availability proof.

T14 now has a real suggest_replan core. Its default loader reads the existing CFO
order/version; wiring it directly to a newer Source DTO would plan the old approved
order. A reviewed fresh-source input adapter and risk integration remain necessary.
The trusted callback tests prove transaction guards, not a real T14/T16 E2E flow.
No edits to planning_service.py, approval_service.py or api/v1/planning.py are made.

Verification below with older commits/counts is historical. Final exact-head checks
are recorded in PR #121. No new business decision, schema, public API or config key
is introduced. Assumptions: reviewed; existing approved stock-scope/independence rules.

## Historical implementation notes (superseded where stated above)

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
