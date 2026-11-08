# REST customer/product feeds — 2026-11-08

DEC-SRC-D1-001 D1-A, US-INT-01 / US-SRC-02 subset. `RestMarketAdapter` now implements
`fetch_customers(updated_since)` and `fetch_products(updated_since)` as read-only async iterators.

- Aware inclusive checkpoint, source API key, page envelope/header validation and bounded page count.
- Preserve decimals and nullable source product category; never silently replace null with invented data.
- Check item natural keys/timestamp ordering, reject duplicates, incomplete pages, changing totals,
  wrong page metadata and redirect/error responses. Errors contain no response body, credentials or PII.
- No source writes, database writes, durable checkpoints, mapping/routing decisions or automatic plans.

Caller may have consumed earlier pages before a later page raises. Persisted ingestion must use
idempotent upsert and advance a durable per-feed checkpoint only after successful exhaustion of all
pages; rollback/retry on any read failure. This transport cannot guarantee an immutable multi-request
snapshot under concurrent source writes, even when row count remains unchanged. Keep overlap/version
handling and review ingestion consistency separately. Default safety budget 10000 pages is configurable
per adapter instance; hitting it is an explicit failed feed, not successful truncation.

Other source feeds/order cancellation transport, stock batch/pool normalization and ingestion API
remain separate tasks. `ProductDTO.category` now faithfully permits null, matching source 05/06.
Assumptions: reviewed; DEC-SRC-D1-001; none new.
