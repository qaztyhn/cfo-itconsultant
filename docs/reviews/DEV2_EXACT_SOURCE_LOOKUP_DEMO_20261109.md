# Dev 2 handoff — exact Source order read for demo-first Sales Sync & Check

**Scope:** read-only internal adapter helper; no new Source endpoint, no CFO routing
decision, no POS/WMS mutation, no deployment switch. Based on owner-approved
DEC-SRC-D1-001, DEC-ROUTING-002 and docs/06 §6.3.

**Available helper:** `RestMarketAdapter.fetch_order_for_sync(external_ref)`
returns a validated `SourceOrder` (including trusted Source version, contact
snapshot, lines, market-local store code) or `None` when absent/cancelled.
It reads **both** complete, existing D1 `GET /orders?status=` feeds and
denies a contradictory submitted/cancelled observation. A malformed or partial
source response raises `SourceReadError`: never route that order to legacy or
CFO from an incomplete Source read. Read credentials are the configured source
adapter credentials, never forwarded browser-supplied values.

**Integration with Dev 1 PR #202:**

1. Dev 2 must create the approved `POST /api/v1/integration/orders/sync-now`
   route (requires JWT, role, store/market scope and Idempotency-Key).
2. The endpoint must build the market-scoped adapter from trusted market config
   and secret reference, then call `fetch_order_for_sync(external_ref)`.
3. Pass the validated `SourceOrder` to Dev 1's
   `source_handoff.accept_source_order` in a single transaction.
4. Check its immutable route outcome, reuse the idempotency key and report
   unresolved/503 without saving `ops.order_routing` as legacy. Do not treat a
   `None` return, a failed read or unauthorised store as a successful sync.
5. Prove PostgreSQL concurrent same-ref retries, cross-store and cross-market
   rejection, immutable legacy routing, source version, successful order creation
   exactly once, and visibility in scoped `GET /orders`.
6. Integrate smoke tests and update the approved OpenAPI artifact/CHANGELOG if
   the actual route contract changes. Do not claim end-to-end planning/approval
   success while WMS ACK and D7 verified 56-day evidence fail closed.

**Limits:** The Source D1 API supports paginated status lists, not point lookup
or a transactionally consistent multi-feed snapshot. A Source order may change
between those two HTTP reads or after verification. A contradictory double
observation is blocked, but absent a Source-side version/ETag/transactional
snapshot, this is only a **demo read bridge**, not proof of atomic live POS
routing. Never market it as production source consistency. A reviewed future
Source contract or post-read source version fence may be necessary.

**Test evidence:** `backend/tests/unit/test_rest_source_exact_lookup.py` uses
the real RestMarketAdapter HTTPX code and MockTransport, including Source 503,
malformed related rows, cancellation, contradictory statuses, and exact-ref
matching. This is **NOT** real Source+CFO HTTP or PostgreSQL E2E evidence.
See [demo setup PR #200](https://github.com/qaztyhn/cfo-itconsultant/pull/200)
for disposable Compose runbook and the truthful results ledger, and
[Dev 1 handoff PR #202](https://github.com/qaztyhn/cfo-itconsultant/pull/202).

**Assumptions:** reviewed; no new or changed business decision. Full demo
remains BLOCKED pending verified `sync-now`, qualified D7 proof and WMS ACK.
