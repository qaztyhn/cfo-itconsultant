# Dev 2 — independent work and remaining dependencies

## Current T07 update — 2026-11-08

The sections dated 07/11 below are historical evidence, not the current decision backlog.
Owner-approved D1–D5/D7 and the superseding fixed-SKU Q10 are applied. D6 is deferred; expanded
D8 scheduling remains unapproved. This task changes no planning/approval/API-planning files,
database migrations, authentication, design contract or frontend UI.

T07 is delivered as a review stack: [#115](https://github.com/qaztyhn/cfo-itconsultant/pull/115)
runner → [#116](https://github.com/qaztyhn/cfo-itconsultant/pull/116) reference persistence →
[#118](https://github.com/qaztyhn/cfo-itconsultant/pull/118) existing CFO order versions/guards →
[#119](https://github.com/qaztyhn/cfo-itconsultant/pull/119) ingest worker/scheduler → stock follow-up
on `feat/t07-stock-ingestion`. Each part has tests and its own PR; no auto-merge is enabled.
Use merge commits, then retarget/recheck the next PR on main. Parent branches were reconciled with
merged #111 using normal merge commits, without rewriting their published history.

Implemented: durable runs/rejects, two-minute inclusive overlap, transactional upserts, independent
submitted/cancelled checkpoints, new-run retry, interruption recovery, source failure alerts, feed/market
leases, scoped reference sync, immutable routing/legacy protection, approved-order/commitment protection,
and an explicit APScheduler ingest worker. After #105/#111 merged at `06ab96d`, the stock extension
adds all-or-nothing fixed-SKU replacement, complete empty batches, unavailable/capture/mapping guards,
retained old data on failure and a latest-run availability/freshness helper. It introduces no pool IDs
or policy to silently skip unmapped stock. Timer cadence stays independent of frozen APP_NOW data.

Verification so far: initial five-feed Harness **PASS** (856 backend tests, 138 source tests,
frontend lint / 1 test / build), before the final stock/timer additions. Focused final PostgreSQL
cases and strict adapter/service/job typing are run separately; final exact-head CI and final local
Harness results are recorded in the stock PR. No unexecuted check or OpenAPI readiness is a PASS.

Remaining handoffs: authorized Sync & check/initial order creation, source staging for unresolved
orders, real T14 fresh-source replan and risk adapters/audit, reviewed cancellation transitions,
availability checks in the forbidden planning/approval modules, source deletion/provenance for
inbound/fleet/customer reconciliation, and review of #106's current Source OpenAPI. Tests with fake
planner/risk callbacks establish the handoff guards only, not real five-gate or E2E acceptance.
Detailed behavior, commands, file responsibilities and dependencies:
[T07_INGESTION_HANDOFF.md](T07_INGESTION_HANDOFF.md).

## Historical independent-delivery record

Date: 2026-11-07. Branch: `feat/dev2-independent-services`.
Integrated `origin/main` at `e1eb333` (PRs #44, #49, #50), merge commit `b6be5d6`.
Subsequently integrated main `798aa22` (including #37, #53, #54 and the decisions register),
then the finished M0 PR branch. Earlier verification counts below remain historical snapshots.
This report distinguishes implemented components from complete milestone acceptance.
No main merge, deployment, real external email, or paid routing request was performed.

## Current delivery session — separate PRs and remaining decisions

Initial verification used main `67e2212`, including approved migrations 0009/0010. The independent components were
split into incremental PRs **#60–#70**; each exact-head CI passed backend/source/frontend and each PR
was marked Ready for review. Those components have since been integrated by the owner, including #74.
The roster branch was updated to main `61ae96a` before publication (migration 0011, routing/ORS/email
decisions, pure planner and DEC-SRC-001 from #79). No automatic merge is enabled. Per-task PR
links, owner decisions D1–D8 and developer handoffs are in
[DEV2_DECISIONS_REQUIRED.md](DEV2_DECISIONS_REQUIRED.md).

New independent task after the schema handoff: `app.seed.roster`, a synthetic warehouse-only roster
for explicit dates, with named assignments (7 early / 6 late per warehouse), demo manager authority,
working-day/holiday checks and SHIFT_CHANGED audit in the same transaction. It does not assign from
expected_staff, replace/resurrect existing schedules, create attendance, or invent driver duty history.
The CLI requires seed-reference first and accepts `--from YYYY-MM-DD --to YYYY-MM-DD` (1–31 days).
Three PostgreSQL tests passed, including full rollback after a late warehouse authorization failure.
Verification on 2026-11-08: full Harness PASS (649 backend / 49 source tests; frontend lint,
1 test and build). On a separate empty PostgreSQL 16 tmpfs database, migration to head 0010,
reference seed and two roster CLI runs passed: 78 new shifts, then 0; final schedule/audit/attendance
counts were 78/78/0. Only that temporary database container was stopped. The roster is a fixture
subset, not full US-WH-06 or M3 acceptance. See the roster PR metadata for hosted CI.

The schema dependency for warehouse rosters is resolved. The actual schedule API and attendance
generation remain Dev 1 work; source/gps/notification/retention/tick contracts and staging decisions
are not silently invented. No whole M1–M9 milestone is declared complete.

## Latest slice — M1 source catalogue reference seed

Integrated `origin/main` at `ce5d7bc`, which contains the owner's merge of PR #41 and the ASM-alignment
fix #57. No source-contract proposal was implicitly approved by those merges. The schedule/routing
migration is present on a separate Dev 1 branch, not main, and is not incorporated here.

Implemented the `08` §5.2 data subset of US-SRC-01 under the existing ASM-009 fixture choices:

- `source_system/seed/se/catalog.py`: deterministic 100-SKU reference catalogue with the six groups,
  documented example SKUs, synthetic unique GTINs, Decimal quantities/prices/weights and base-unit factors.
- `source_system/app/seed_reference.py`: seed catalogue alongside customers/addresses. Insert missing
  SKUs only; retain existing prices, names, timestamps and unrelated rows. Do not seed stock/orders,
  choose routing, or change CFO mapping status.
- `source_system/pyproject.toml` and `Dockerfile`: include the seed package in the installed wheel and
  image. The source application does not import CFO or read CFO data to write it back upstream.
- Source tests cover repeatability, documented quantities/units, GTIN validation and preservation.
  A backend PostgreSQL test compares every shared field of all 100 source fixtures to actual CFO seed
  rows. Cross-application loading is test-only; no runtime dependency between applications is added.
- Targeted cross-catalogue test: **1 passed**. Source tests: **49 passed**. Ruff/Black and source
  strict mypy (`app` + `seed`): PASS. Docker source image build: PASS.
- Updated-branch Harness: **PASS**, **621 backend / 49 source tests**, frontend lint /
  **1 test** / build. No database tests skipped.
- Installed-wheel import check using `python -I`: **PASS**, independent of the image working directory.
  Packaged `app.init_db` and two `app.seed_reference` invocations against isolated PostgreSQL: **PASS**,
  with exactly **100 products / 40 customers / 80 addresses** afterwards. No live source API or CFO
  data was used for this seed. Only the temporary PostgreSQL container was stopped.

Run the existing `source-seed-reference` / `source-seed-reference-docker` targets after `source-init`;
these now add products as well as the 40 customers / 80 addresses. Full M1 remains incomplete:
source API contracts, stock batch semantics, inbound/fleet/scenario orders and calendars remain pending.

## PR #41 completed for review; next routing slice

[PR #41](https://github.com/qaztyhn/cfo-itconsultant/pull/41) was completed **Ready for review** by Dev 2;
the owner subsequently merged it into main at `ce5d7bc`.
Head `cb4ae7a`; [CI run 42382553067](https://github.com/qaztyhn/cfo-itconsultant/actions/runs/42382553067)
completed successfully for backend, source and frontend. Its Windows Docker smoke exited 0:
554 backend tests, 17 source tests, frontend lint/test/build and both health probes passed;
authentication remained valid after Harness. M1/later source/auth/seed/routing work is excluded
from this nine-file M0 PR. OpenAPI comparisons remain NOT VERIFIED, not silently certified by CI.

Continued US-INT-05 AC1/2 / FR-DEL-02 in the separate Dev 2 branch:

- `backend/app/services/routing_service.py` prepares route_matrix entries for an existing order's
  delivery snapshot and all active warehouses in that same market, in the caller's transaction.
- `tools/precompute_routes.py --order-id <id>` exposes the use case for explicit operational use.
  `--offline` prevents ORS calls while respecting the market's allow_fallback setting. Output contains
  counts only, not coordinates, addresses, credentials or provider responses.
- Three real PostgreSQL integration tests cover market/active-warehouse isolation, cache reuse,
  atomic rollback on routing failure, offline fallback and refusal when fallback is disabled.
- No source writes, order state changes, plan/hold creation, API/DDL or engine changes. This helper
  does not establish CFO-versus-legacy eligibility or approve anything. Dev 1 still needs to invoke
  route preparation from the appropriate planning use case after routing/eligibility is ready.
- Targeted tests: **3 passed**. Targeted Ruff, Black, mypy and CLI --help: PASS.
- Full updated-branch Harness: **PASS**, **617 backend / 47 source tests**, frontend lint /
  **1 test** / build. Tool unittest suite: **7 passed**.
- Offline CLI executed twice against a synthetic existing order on fresh temporary PostgreSQL:
  **PASS**, one fallback pair on each run, no ORS request. The test container was stopped;
  existing projects/volumes/data were untouched. New routing work is not added to PR #41.

## Follow-up — M0 live-stack acceptance

Continued under the existing contracts and `docs/M0_BACKEND_HANDOFF.md` §5.
At the time of that run, remote main was `e1eb333`; the newer schedule/routing and assumptions-register branches were
read for coordination. Their business approvals do not provide the pending source API DTOs or
the final reviewed migration/API implementation for schedules/routing.

Changes in this follow-up:

- `frontend/Dockerfile`: install the committed lockfile with `npm ci`.
- `frontend/.dockerignore`: exclude host node_modules, dist, environment files, logs and coverage.
  No frontend UI or dependency versions changed.
- `tools/m0_smoke.py`: use IPv4 for the IPv4-only published PostgreSQL port; create dedicated
  cfo_test/source_test databases so migration tests cannot reset the running applications' databases;
  repeat authentication after Harness to prove application seed accounts survived.
- Rename Dev 2's technical seed assumption to ASM-009, with its former branch-local ASM-008 identity
  recorded, to avoid the Dev 3 ASM-008 referenced by the new decisions register. No business decision changed.

Command: `python tools/m0_smoke.py --docker <Docker executable>`.
The final run uses isolated project `cfo-m0-check-b4bd32eb`, generated credentials and tmpfs PostgreSQL.

| Handoff step | Result |
|---|---|
| 1. Five Compose services | PASS; postgres, mailpit, source-se, cfo-api healthy; cfo-web running and HTTP 200 |
| 2. Empty-DB migration | PASS; direct container `alembic current` returned `0008 (head)` |
| 3. Minimal accounts | PASS; generated password, no credentials written to files |
| 4. CFO/source health and web | PASS; both health responses valid, web HTTP 200 |
| 5–8. Login, /auth/me, invalid/missing token, disabled account | PASS; authentication smoke true |
| 9. Harness verify + smoke | PASS; 488 backend tests, 47 source tests, frontend lint / 1 test / build; both live health probes HTTP 200 |
| Application auth preserved after database tests | PASS; login, identity, invalid-token and account-lock checks passed again after Harness |

Additional check: the built Linux web container returned HTTP 200 for `/src/main.tsx` with a
successfully transformed Vite entry module. The Docker build used `npm ci` and excluded host modules.
The complete runner exited **0**; it stopped only the isolated test project's containers, with no
volume deletion. Tool tests: **7 passed**; script Ruff and `git diff --check`: PASS.

The initial smoke run's slow localhost pytest child was deliberately stopped for the IPv4 correction;
that run returned FAIL and is **not** counted as a passing verification. Its isolated containers were
stopped by the runner. The passing results above come from the complete rerun, with no tests disabled.

## Implemented components

| Task | Source files | Evidence / acceptance covered |
|---|---|---|
| Market onboarding and adapter registry | `backend/app/adapters/{registry,market_setup}.py`, `tools/add_market.py` | US-INT-04 / BR-GEN-02: explicit per-market credentials, missing configuration fails safely without SE fallback; additive DK table, FKs, timestamp trigger, currency, union view, shadow mode; rerun preserves configuration. Registry is stock-capable, not a claim that all adapter feeds work. |
| ORS routing, fallback and cache | `backend/app/providers/routing_{ors,fallback}.py`, `route_cache.py` | US-INT-05 / FR-DEL-02: authenticated HGV matrix, lon/lat order, km/seconds conversion, sanitized provider errors, fallback when allowed, refusal when disabled, cache persistence and replacement of disallowed fallback. Existing ORS cache entries are preserved under conflict. Planning-service invocation remains to be connected. |
| Infrastructure/workforce/fleet/catalog reference seed | `backend/app/seed/{infrastructure,workforce,fleet,catalog,reference_demo}.py`, `Makefile` | `08` §5.1–5.4, M1/M3 subset: 3 warehouses, 25 stores, 30 weekday shift templates, Swedish holidays, 163 employees, one active assignment each, 28 primary managers, 10 drivers including one expired licence, 9 vehicles including 8 t crane, 100 local SKUs (97 confirmed / 3 pending). Workers have no app account. Passwords come from environment; repeat does not reset password hashes, disabled accounts or operator edits. |
| Source catalogue/customer/address reference seed | `source_system/seed/se/catalog.py`, `source_system/app/seed_reference.py`, source integration and cross-catalogue tests | `08` §5.2/5.5 / US-SRC-01 data subset: 100 SKUs matching CFO, deterministic 40 customers (30 business / 10 consumer), 80 synthetic geocoded addresses; rerun preserves edits. Does not seed stock, orders or receiving calendars. |
| GPS loss / position retention | `backend/app/jobs/gps_lost.py`, `gps_retention.py` | US-GPS-03 AC1/2 / BR-GPS-01: enabled markets and on-road trips only for loss; configurable strict loss threshold; deduplicated dispatcher-only alert. Retention uses trip end time and market configuration, preserves active trips and exact boundary, and remains effective when GPS is disabled. No coordinates or driver details in logs/alerts. |
| Stale stock check | `backend/app/jobs/stale_data.py` | US-INT-03 AC2 backend component: oldest stock timestamp per warehouse, configurable strict threshold, one open dispatcher warning, resolves on recovery, can recur after resolution; stock quantities/reservations are untouched. UI flag is Dev 3 / planning integration. |
| SMTP and SMS transports | `backend/app/providers/{email_smtp,sms_sim}.py` | US-NOT-01 AC3 transport component: local Mailpit SMTP by default, verified STARTTLS for authenticated SMTP, sanitized errors, header injection rejected; SMS has no network side effect. |
| Queued notification delivery | `backend/app/services/notification_delivery.py`, `notify_service.py`, `backend/app/jobs/outbox.py` | US-NOT-01 AC3/4 and US-NOT-03 AC1–3: market-local quiet hours (DST boundary tested), explicit DELAY exemption, no sending unapproved DELAY/draft, shadow suppression, configurable attempt cap, sanitized last_error, sent/suppressed audit in the caller transaction, `FOR UPDATE SKIP LOCKED` prevents competing workers sending the same queued row concurrently. No new content templates or customer messages are generated. |
| Explicit operational CLI | `tools/gps_simulator.py`, `tools/run_job.py`, `docker-compose.yml` | US-GPS-01 AC4 simulator payload with 60–120 second spacing, driver token from env, stops on denial without replay; route/token never printed. Run only implemented maintenance jobs explicitly. Compose forwards optional ORS key and source APP_NOW. Does not silently activate scheduler stubs. |

Routing request format was checked against the official
[ORS Matrix API reference](https://giscience.github.io/openrouteservice/api-reference/endpoints/matrix/).
Tests use HTTP mock transports; live ORS connectivity/quota is not verified.

Assumption ASM-009 (previously ASM-008 on this branch) in `docs/ASSUMPTIONS.md` records synthetic fixture choices.
These reference fixtures do not assert the quantitative outcomes of scenario orders in `08` §5.6.
GPS enablement/DPIA state and existing market configuration are preserved.

## Commands and verification

Final verification results are recorded below after execution; no unexecuted check is a PASS.

- Focused routing/registry/transport/seed/GPS tests: 24 passed before the final additions.
- Harness after integrating main, before outbox additions: **PASS**, backend 482 tests,
  source 47 tests, frontend lint / 1 test / production build.
- Outbox integration tests: **6 passed**, including real PostgreSQL concurrent workers.
- Final `python tools/harness.py verify`: **PASS**, backend **488 passed**, source **47 passed**,
  frontend lint / **1 passed** / production build; no database tests skipped.
- `docker compose config --quiet`: **PASS** with runtime-only generated credentials.
- CLI smoke on separate fresh databases: `alembic upgrade head`, CFO `app.seed.reference_demo`
  twice, source `app.init_db` then `app.seed_reference` twice: **PASS**.
- `python tools/run_job.py` for gps-lost, gps-retention, stale-stock, outbox: **PASS** against the
  freshly migrated/seeded database (no eligible rows; nonempty behavior covered by integration tests).
- `python -m unittest discover -s tools/tests`: **7 passed** in the final CLI smoke.
- CLI `--help`, script Ruff under the project's backend config, and `git diff --check`: **PASS**.
- Additional mypy over the Dev 2 adapters/providers/jobs/seed/delivery service: PASS.
- OpenAPI readiness commands for CFO and source: **BLOCKED / NOT VERIFIED**; the approved
  `contracts/cfo.openapi.json` and `source_system/openapi.yaml` artifacts are absent/empty.
  Their readiness command exits zero to communicate availability, not successful contract comparison.

PostgreSQL tests use fresh `postgres:16` containers with tmpfs and randomly generated credentials.
Only those temporary containers are stopped. Existing containers, Docker volumes and application data
are not reset or removed. The standard FastAPI/Starlette deprecation warning remains non-failing.

GNU Make is not installed in this Windows shell. Actual module commands behind the new targets are
verified directly; the Make invocations themselves are NOT VERIFIED here. CI on a supported Linux
runner has not been observed for this unpublished branch.

## Running the completed subsets

Use the backend venv / supported shell, with DATABASE_URL and credentials supplied privately:

```text
make seed-reference
make seed-reference-docker
make source-seed-reference
make source-seed-reference-docker
python tools/add_market.py DK --name Denmark --timezone Europe/Copenhagen --currency DKK
python tools/run_job.py gps-lost
python tools/run_job.py gps-retention
python tools/run_job.py stale-stock
python tools/run_job.py outbox
python tools/gps_simulator.py --trip-id <id> --route <synthetic-route.json>
```

For source commands, run `source-init` first and use the source DATABASE_URL/SOURCE_SCHEMA.
Set APP_NOW to the documented demo timestamp for consistent demonstrations. Set CFO_DRIVER_TOKEN
privately for the simulator. It requires the GPS API, an on-road trip and a properly scoped driver.
The simulator has transport tests, not a verified live GPS API round-trip.

`make seed` still targets the full scenario generator; it remains explicitly blocked while that
generator is a stub. The subset commands never turn that check green.

## Skipped decisions and dependencies

| Milestone / remaining task | Why it is not completed / next owner or decision |
|---|---|
| M0 live five-service acceptance / remote CI | Follow-up live Compose acceptance is recorded above. Remote CI and reviewed OpenAPI baselines remain separate and are not inferred from local smoke. |
| M1 source write APIs, source OpenAPI, complete seed | SRC-Q1–Q10 in `docs/proposals/M1_SOURCE_CONTRACT.md` remain unapproved: order snapshots, response DTOs, validation, paging, calendars, atomic/empty stock snapshots and SKU stock normalization. The main ASM approvals do not approve this proposal. |
| M2 REST feeds other than stock / CSV adapter | List DTOs/paging and CSV column/schema contract are unresolved. No guessed file layout or upstream write-back. |
| M2 ingestion and Sales sync-now | Needs approved source DTOs and the ASM-005/Q14 routing producer/API handoff. Main #57 removed automatic order unblocking; 0009/0010 now provide immutable routing storage, but source completeness/freshness and scoped sync behavior remain pending. Dev 1 must review store scope for sync-now. |
| M2 stock persistence | Need a decision for multiple local SKUs mapped to the same global product: the source is keyed by warehouse/SKU, but CFO snapshot is keyed by warehouse/global product. Blind overwrite or sum may double-count physical stock. Batch freshness / empty batches are also SRC-Q9. |
| M2 scheduler and `/internal/tick` | Supported job names/response DTO and complete jobs are not handed off. The explicit CLI runs implemented jobs only; there is no claim of an automatic 5-minute pipeline. |
| M3 attendance generation | Schema is migrated (0009/0010), and explicit warehouse demo roster seed is implemented. Dev 1's schedule API/attendance generation integration is still pending; generate_attendance currently returns 0. No automatic allocation from expected_staff or invented actual attendance. |
| M4 golden scenarios / route matrix for all scenario sites | Requires complete source order seed, approved mapping policy and working planner/capacity context. Order-route preparation service/CLI and cache are implemented; golden outcomes (000123/137/144/160) are NOT VERIFIED. |
| M5 approval/load tests and Sales concurrency | ApprovalService, ReservationService and guarded Sales approval remain dependencies owned by Dev 1. Existing close_active_plan is available, but is not full approval. No fake concurrency acceptance against a stub. |
| M6 GPS ingest/live/history/settings | GPS response DTOs and exact contracts need review; risk/ETA recalculation remains a Dev 1 dependency. Endpoint authorization/consent and live simulator round-trip are not claimed complete. |
| M7 enqueue/delay draft/send/discard, templates, retry scheduling beyond next tick | These remain separate from queued delivery. Sensitive template content must reconcile `09` (status/ETA only) with `03` examples containing warehouse/recipient details. Approval/execution/risk hooks are not ready. No invented retry backoff or dispatcher authorization payload. |
| M7 morning/milestone risk jobs | Depend on Dev 1 RiskService/execution/planning context. Stale-stock/GPS-loss checks are independently implemented. |
| M8 anonymisation and 48 closed-order seed | Need retention eligibility rules for shared customer/employee history and immutable audit, plus execution/KPI services and scenario state. GPS expiry is implemented separately; full retention is still pending. |
| M9 E2E and staging | E2E requires Dev 1 endpoints and Dev 3 UI. Deployment needs selected accounts/projects, region and private credentials; no hosting configuration is guessed or externally published. |

### Delivery reliability boundary

Database row locking and dedupe prevent competing workers from sending the same persisted queued row
at the same time. SMTP has no transactional acknowledgement with PostgreSQL: a process crash after
SMTP acceptance and before DB commit can cause delivery again. Exactly-once external delivery is
not claimed. SMS content is retained in the notification row; the transport's message list is local
to its process. Customer content generation and notification-list API remain separate work.

Overall M1–M9 are **not complete**. Independent components above are implemented; skipped contracts,
unavailable dependencies and unverified end-to-end behavior remain explicit.
