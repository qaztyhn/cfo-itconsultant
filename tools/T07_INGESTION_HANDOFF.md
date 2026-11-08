# T07 — ingestion and ingest-only scheduler

Scope: US-INT-01 AC2–AC5, US-INT-02 AC1–AC3, US-INT-03 transport/persistence subset,
US-ADM-01 AC2; FR-INT-02/04/05/06 and BR-ORD-01, DEC-ROUTING-002, DEC-SRC-D1-001.
Approved decisions override older architecture examples that auto-create/route orders.

## Delivery A: transactional runner

`ingest_service.synchronize` takes a trusted row writer and read-only adapter. It records a
running API run before network I/O; an advisory transaction lease rejects overlapping workers
for the same market/entity. A later lease recovers interrupted running rows as failed. Invalid
typed records become safe `sync_reject` metadata; individual DB constraints use savepoints.
Transport/pagination failure rolls back all data/reject/checkpoint changes and records failure
plus one deduplicated admin-only `SYNC_FAILED` alert. Successful recovery resolves that alert.

First sync omits the source timestamp bound. Later sync uses the durable checkpoint minus
the approved two-minute overlap. Submitted and cancelled orders have separate checkpoint
keys (`orders`, `orders:cancelled`) but share an orders run/lease. Only completed pagination
can advance checkpoints. A completed partial run may advance its known timestamps per 04 §5.2;
unknown/future timestamps and missing downstream dependencies pin that feed. Explicit API
`retry_run_id` replays the previous failed/partial lower bound into a new run without erasing
history or moving an existing checkpoint backward. CSV retry persistence is a separate task.

Rejects contain external identity, static code and no raw payload/PII. Source errors/URLs/keys
are never copied into run errors or alert messages. Customer technical logs are not produced.

Initial PostgreSQL runner tests: 5 PASS (duplicates, partial, whole-run rollback/failure/retry,
overlap and concurrent lease/visible running status). Adapter regression cases: 39 PASS.
Ruff/Black and strict adapter/runner mypy PASS. Full CI is tracked in the runner PR.

## Contracts and pending integration

At audit, #105 is merged with fixed-unit SKU batches and `503 STOCK_UNAVAILABLE`; #111 is
still open, and #106 has a stale conflicting pool-era OpenAPI candidate. Do not integrate the
old pool normalizer or claim stock ingestion complete. Stock remains unavailable to this runner.

Entity row writers, polling job and ingest scheduler follow in separate reviewable changes.
Polling must never create routing decisions/customer orders before an authorized `cfo` decision,
revive legacy orders, change approved commitments, create holds or approve a delivery.
The production `planning_service.suggest_replan` is still a stub: fresh-source suggestion/risk
handoffs must use a trusted transactional adapter; absence must remain visible and retryable.
No edits to planning_service.py, approval_service.py or api/v1/planning.py are authorized here.

D8 remains unapproved. Only ingestion cadence already specified by `MarketConfig.sync.interval_min`
is in T07; no new internal-tick HTTP contract, GPS/outbox/nightly schedules or cloud deployment.

Assumptions: reviewed; DEC-SRC-D1-001, DEC-SRC-Q10-SKU-001, DEC-SRC-Q9-ERROR-001,
DEC-ROUTING-002; none new. No migrations, auth, source writes or automatic merge.
