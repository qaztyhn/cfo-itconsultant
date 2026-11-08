# T07 — ingestion and ingest-only scheduler

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

## Delivery B: reference feed persistence

Customers upsert by market/external ref, preserve notification preferences/receiving settings and
refuse to rehydrate anonymised records. Products use each market's existing product table, retain
IT mapping ownership/status, ignore stale `source_updated_at`, create pending mapping tasks without
marking the run partial, and reject changes to the fixed SKU unit/conversion. Nullable source
category cannot satisfy 05's NOT NULL column and is rejected without inventing a category.

Inbound uses confirmed mapping/base units, market-scoped warehouses and exact NUMERIC quantities;
received deltas update ERP rows. CFO transfers and cross-warehouse/global-key collisions are protected.
05's inbound identity omits source SKU and warehouse: several local SKUs mapping to one global product
cannot safely overwrite that identity, so these records are rejected until target provenance is reviewed.
Fleet upserts source intervals only, scoped through vehicle home warehouse; manual rows and EXCLUDE
constraints stay active. Conflicting overlapping source/manual intervals are partial, never overwritten.

Incremental absence is not an upstream tombstone. Source contract currently has no deletion/version
provenance for customer/inbound/fleet rows and no transactionally frozen full list. This implementation
does not infer a receipt or delete busy time merely because a row is absent from a delta. Reliable removal
reconciliation needs a reviewed source tombstone/full-snapshot handoff; it is not claimed complete.
Per-row stale skipping is supported by orders' version and products' source_updated_at; other target
tables lack source timestamps, and their stale-record provenance requires a schema handoff.

Changes to inbound/fleet with approved/in-flight orders require a trusted transactional risk callback.
Without it, affected row writes roll back, the run is explicitly partial and the checkpoint is pinned for retry;
no fake risk recalculation, plan replacement or approval is performed. Reference tests cover mapping
preservation, pending products, stale versions, unit drift, invalid/foreign rows, transfers and calendar
idempotency/collisions. Results are tracked in the reference PR.

## Delivery C: existing CFO order versions and protected source changes

Polling does not implement authorized Sync & check or initial CFO order creation. It updates only
an existing order with an explicit immutable `cfo` routing decision. Unresolved routing or a `cfo`
decision without its initial order is partial/pinned for handoff; no guessed source staging table,
creation timestamp, automatic mapping/route, hold or approval is introduced. Legacy stays legacy.
An accepted newer version replaces SUBMITTED data/lines atomically, validates scoped customer/store,
existing Sales attribution, known confirmed SKU conversion and exact quantities/money. Replays/stale
versions do not replace lines, bump CFO version or duplicate orders/routing.

APPROVED/PREPARING/GOODS_READY/LOADED source edits keep all approved order fields, lines and committed
resources and raise a deduplicated Dispatcher warning. A trusted T14 `ReplanSource(session,order,fresh)`
handoff must calculate all five gates with old commitments added back, create only suggestion candidates,
audit and alert in the same transaction, and identify `params.source_version`. The runner checks suggestion
kind/version, no holds/reservations/approved candidates and unchanged order/lines. No production handler is
injected while T14 is unavailable: the run remains partial and retries. Fake test callbacks verify only this
handoff/guard; they do not prove real planning acceptance. Existing valid source-version suggestions dedupe.

After DISPATCHED/terminal, changes/cancellation are alert-only. Before dispatch a source cancellation never
creates a replacement delivery. Before approval, the present transition table does not authorize system
cancellation, so cancellation remains partial/pinned until Dev 1 reviews that transition/workflow. The worker
never impersonates Dispatcher or directly writes status.

Risk callbacks for inbound/fleet now execute once per affected order after every row/page, in the same
transaction. Replays without a material reference change do not recalculate. Missing callback rolls back
the affected reference row; callback failure rolls back the entire run. This keeps retry meaningful rather
than acknowledging new data before downstream work exists. Initial risk/replan callback adapters are still
Dev 1 handoffs, not automatically inferred from existing stub function names.

## Delivery D: polling job and explicit scheduler worker

`app.jobs.ingest.run_market` polls customers → products → orders (both statuses) → inbound → fleet,
records every feed result and continues independent feeds after one failure. Incomplete runs or
overlapping feed errors make the job fail visibly; no catch-and-return-zero success. Technical logs
use the approved integration/scheduler services with market/counts only.

`app.jobs.scheduler.create_scheduler` builds one job per market, its configured IANA timezone and
`sync.interval_min`, coalescing missed invocations with max_instances=1. PostgreSQL leases still guard
replicas/manual runs. Building/importing does not start jobs. No API startup, new `/internal/tick`
contract or D8 GPS/outbox/nightly schedule is enabled. Rebuild the worker after market-config changes.

Explicit commands from backend, with private `DATABASE_URL` and source-key-reference environment set:

```powershell
.venv/Scripts/python.exe -m app.jobs.ingest --market SE
.venv/Scripts/python.exe -m app.jobs.scheduler
```

The first command is a one-off run and exits nonzero for partial/failed work. The second starts the
ingest-only worker and runs until stopped. It must be operated separately from API replicas; do not
also start an overlapping external cron. T14 risk/replan remains fail-closed until the server handoff
is injected. No production API exposes callback injection. Stock remains excluded from this delivery.

Recheck during implementation: #111 merged into main at `06ab96d` after the initial T07 audit; #105
and #111 now agree on fixed-SKU/503 DTO. #106 is still open, reconciled on a new head awaiting review.
Do not read the earlier initial audit as the current merge status or reuse superseded pool code.
Full stock persistence/freshness still needs an all-or-nothing batch review and its own tests.

## Delivery E: stock after merged Q9/Q10

This delivery supersedes the earlier five-feed exclusion. It incorporates main `06ab96d`, where
#105 and #111 are merged. The worker now polls stock last as a sixth feed. It reads a complete
batch, the complete source product unit catalogue, and the batch again to detect publication
changes. Confirmed CFO mapping/unit/factor must match; conversion occurs once. Any unknown SKU,
unconfirmed mapping, ambiguous multi-SKU/global identity, unknown warehouse, invalid quantity,
capture regression/conflict or incomplete source response rejects the whole batch. No owner rule
was added to skip pending SKU rows or aggregate unverified inventories.

Replacement is one transaction for the configured market/source namespace, including an explicitly
published complete zero-row batch. Other markets and all CFO reservations are preserved; no snapshot
`FOR UPDATE` is used. HTTP 503/failed validation/downstream callback rolls back replacement and keeps
the old snapshot/capture. Replay retains the original row provenance/time. A failed batch cannot
advance its checkpoint or be published as partial complete inventory. Batch counters count inventory
rows, including zero for a genuinely published empty batch. Safe batch rejection metadata is recorded.

`ingest_stock.usable(session,market_id,now=...)` distinguishes current successful/fresh capture from
unavailable/failed/running/stale state, including a fresh complete empty batch. A failed latest run
invalidates even recently cached rows. T14/T16 must consume this **in addition to** their real source
and per-item/locked approval checks; forbidden planning/approval files are untouched. Providing this
helper is not proof that the production five-gate availability integration already exists.

The existing stale-stock threshold/key/Dispatcher warning are retained; an old source capture is never
renewed to job time. Changes affecting approved/in-flight orders still require the trusted risk handoff;
without it the stock run fails and rolls back. No automatic replan approval or reservation release occurs.

Worker batches have an additional market lease so replicas cannot interleave dependent feeds, plus
per-feed leases shared with manual runs. Standalone workers configure safe JSON logging and one
correlation ID per batch. APP_NOW freezes business time, while the periodic timer uses APScheduler's
wall clock unless a timer anchor is explicitly injected for tests. CLI supports a scoped manual retry:

```powershell
.venv/Scripts/python.exe -m app.jobs.ingest --market SE --entity orders --retry-run-id 123
```

Tests use only temporary PostgreSQL databases and mocked read-only HTTP. Full final CI/verification
is recorded in the PR; focused PostgreSQL cases cover duplicates, partial/failure/retry, stale versions,
concurrency, protected approved data, scheduler execution/clock, stock empty/unavailable/scope, mapping
failures, capture integrity and preservation of CFO commitments. Source OpenAPI #106 remains a separate
review gate. No live deployment, extended D8 tick contract or whole-M2/E2E acceptance is claimed.
