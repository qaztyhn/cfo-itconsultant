# Demo MVP — reproducibility evidence ledger

**Checked against:** `main` and approved decisions on 2026-11-09.
**Environment:** Swedish isolated, synthetic `APP_NOW=2026-11-04T10:05:00+01:00`.
**Target:** Source → authorized CFO Sync & Check → planning → approved standard order,
with one real infeasible/legacy negative path. **Not yet E2E PASS.**

Every status below refers to a specific surface and evidence type:

- **PASS:** the actual named check was executed and passed, not an inferred business outcome.
- **FAIL:** executed check contradicted the contract.
- **BLOCKED:** required endpoint, approved input or external contract prevents safe execution.
- **NOT VERIFIED:** no matching real-service run/result yet.
- **Unit-test PASS is not the same as real Source/CFO/PostgreSQL E2E PASS.**

## Current evidence

| Check | Status | Source of evidence / precise limitation | Owner |
|---|---|---|---|
| Approved Swedish demo clock + deterministic 18 current, 48 historic source orders | PASS (unit fixture contract) | Existing `backend/app/seed/scenarios.py` and `source_system/app/seed_demo.py` have deterministic generator, manifest validation and conflict refusal; existing integration tests cover source PostgreSQL seed rerun. Fresh Compose replay requires preflight evidence. | Dev 2 |
| ST-001 source order `SE-2026-000149` (light candidate) | PASS (fixture presence only) | Generated submitted source input; actual feasible rank-1 result **NOT VERIFIED** until routed, stock/evidence and planning are read from real APIs. | Dev 2 / Dev 1 |
| GBG warehouse, vehicle GBG-03-02 and driver1 account | PASS (reference fixture only) | `workforce.py`, `fleet.py`; real joint eligibility and assignment **NOT VERIFIED**. | Dev 2 / Dev 1 |
| Official manager-attributed warehouse + driver shift | PASS (seed-contract tests) | `test_demo_roster.py`, `test_demo_driver_shifts.py`; only official **synthetic** schedule, not proof of attendance, GPS permission or D7 driving/rest compliance. | Dev 2 |
| Verified 56-day D7 regulatory evidence | BLOCKED | Existing 560 history rows explicitly `verified=false`, `reg_561_scope=unknown`; candidate never becomes legally qualified by changing test data. | Dev 1 / privacy |
| Source product mappings + WMS published 300-row snapshot | PASS (source fixture/seed tests) | Existing `test_demo_seed.py`; `88412` pending mapping. CFO stock persistence needs reviewed scope/independence evidence and must never fake `on_hand`. | Dev 2 / Dev 1 |
| Source submitted-orders GET, API-key negative, repeated versions | **PASS (disposable Compose preflight)** | Real Source HTTP at [run #42605883212](https://github.com/qaztyhn/cfo-itconsultant/actions/runs/42605883212) reported `source_auth_negative`, `source_fixture`, `source_read_repeat` PASS. This is real Source HTTP, not CFO acceptance. | Dev 2 |
| CFO authenticated Sales/Dispatcher/Warehouse/Driver APIs | **PASS (disposable Compose preflight)** | The real-HTTP preflight required all four role login/read probes, unauthorized denial, Source/CFO DB health and frontend HTTP to PASS before a green result. JWT kept in memory. This is not browser interaction or delivery approval evidence. | Dev 2 |
| Sales `POST /integration/orders/sync-now`, scoped idempotent routing and CFO order creation | BLOCKED | Documented in `docs/06` §5.0.2, but no implementing route on `main`. T07 polling deliberately cannot accept a new undecided source order; do not insert a fake `order_routing`. | Dev 1 (contract) + Dev 2 (integration) + Dev 3 (UI) |
| Repeated sync without duplicate CFO records | NOT VERIFIED | Real HTTP retry checks matching ID + key. Additional read-only PostgreSQL uniqueness query in `DEMO_SETUP.md` must be executed before PASS. | Dev 1 / Dev 2 |
| Negative case: pending SKU `88412` stays legacy | NOT VERIFIED E2E | Fixture mapping pending confirmed by source/canonical catalogue; routing endpoint missing, so no valid routing decision yet. | Dev 1 / Dev 2 |
| Negative case: `SE-2026-000137` requested-date/resource constraint | NOT VERIFIED E2E | Golden expected outcome is a specification baseline, **not** an observed planner result. No hardcoded fake `NO_FEASIBLE_DATE`. | Dev 1 |
| Real server-generated planning run | BLOCKED | No accepted CFO route from Sync & Check yet; stock freshness/scope and D7 gates also remain mandatory. | Dev 1 |
| Explicit rank-1 standard plan approval | BLOCKED | D7 attested evidence and real/simulated approved WMS reservation-ACK proof must pass server gates; never use a fabricated driver history/ACK. | Dev 1 |
| Driver dispatch/POD, GPS, customer notification | NOT VERIFIED / DISABLED | Beyond this smoke's safe scope; no real GPS, live customer messaging or WMS production write. | Dev 1 / Dev 3 / privacy |
| Disposable environment reset | **PASS (isolated CI Compose project only)** | [Run #42605883212](https://github.com/qaztyhn/cfo-itconsultant/actions/runs/42605883212) logs show all `cfo-demo-ci-*` containers removed, named `pgdata` volume removed, and no unrelated project targeted. Reproduction on a different developer workstation remains NOT VERIFIED. | Dev 2 |

## Incremental evidence contract — database proof slice (2026-11-09)

**Code added, new exact-head Compose run not yet verified at the time of this
change.** `tools/demo_db_verify.py` reads the real Source versions and CFO
PostgreSQL rows *after* an actually accepted Sales Sync & Check event, with
no extra database writes. Its two independently reported results are:

- `postgres_once`: exactly one CFO order and one `cfo` routing decision
  matching Source version for Swedish store candidate `SE-2026-000149`.
- `postgres_legacy_negative`: zero CFO orders and exactly one `legacy`
  routing decision matching source version for unmapped `SE-2026-000156`.

If the mutating Source/CFO HTTP smoke reports `sales_sync_write=BLOCKED`,
the tool does **not** query an imagined CFO order: it emits `BLOCKED` and
`NOT VERIFIED`. A source-version mismatch, duplicate row, missing routing,
malformed prior smoke report or inaccessible PostgreSQL is **FAIL**. The
preflight CI enforces the proof whenever the HTTP route actually succeeds,
and uploads a separate non-PII JSON report.

**Current ownership and prerequisites:** Dev 1 Source-order acceptance is
in [PR #202](https://github.com/qaztyhn/cfo-itconsultant/pull/202);
Dev 2 HTTP adapter is in stacked
[PR #204](https://github.com/qaztyhn/cfo-itconsultant/pull/204).
Neither was merged into `main` when this slice was authored.
Do not upgrade Source→CFO sync, database uniqueness, actual five-gate plan,
standard-plan approval or full E2E to PASS based on this code or the older
preflight. Regulatory D7 data remain unverified and WMS reservation ACK
remains a separate Dev 1/2 prerequisite. No production scheduling,
real GPS, notification sending or physical WMS write is enabled.

## Executed disposable CI evidence — 2026-11-09

- Commit: `c2171fa6a1daafe4212ba243ae652294fd48a934`
- [Real Compose demo-preflight run #42605883212](https://github.com/qaztyhn/cfo-itconsultant/actions/runs/42605883212): **SUCCESS**. The runner launched actual PostgreSQL 16, Source API, CFO API, Mailpit and frontend. Source manifest generator emitted SHA256
  `02a3c0094b9a22935ac71b3bb52fe4569da3bf44c9c61c6433bf3966bdb6f508`.
- Source seed: 66 orders inserted. The four existing reference feeds reported:
  customers 40 rows, products 100, inbound 1, fleet 1; each finished without
  automatic routing/approval. Demo roster generator reported 312 warehouse and
  80 driver shifts (synthetic official assignments, **not** D7 legal proof).
- Both read-only and mutating-mode preflight probes reported
  `source_auth_negative=PASS`, `source_fixture=PASS` and
  `source_read_repeat=PASS`. The harness required CFO/source DB health,
  frontend HTTP, authenticated four-role checks and scoped Sales/Dispatcher
  reads to PASS; the overall preflight passed those assertions.
- The mutating probe identified **missing Sales sync-now** as BLOCKED; the
  successful preflight job explicitly printed
  `BLOCKED != E2E PASS`. No new accepted CFO order or approved plan was proven.
- CI cleanup removed the one generated `cfo-demo-ci-*` project, its containers
  and named PostgreSQL volume. A second independent clean workstation run has
  not been observed.
- [Regular repository CI run #42605883173](https://github.com/qaztyhn/cfo-itconsultant/actions/runs/42605883173): **SUCCESS**.
- The published `demo-preflight-status` artifact contains the limited
  machine-readable results. No real-customer or production-system data used.

These outcomes supersede earlier `NOT VERIFIED` status **only for the named
read-only Source/CFO HTTP checks and disposable CI reset**. Full Sales Sync,
database uniqueness after acceptance, five-gate planning, D7 and WMS ACK remain
BLOCKED/NOT VERIFIED exactly as recorded in the table.

## Commands and evidence to record

Run in a uniquely named disposable project, following
[DEMO_SETUP.md](DEMO_SETUP.md). The isolated preflight CI is defined
in `.github/workflows/demo-preflight.yml`. It creates unique temporary
credentials, starts the **real** Source, CFO, PostgreSQL and frontend
services, runs the read-only checks, exercises the missing Sync & Check
endpoint only on synthetic data, then resets **only its own** project.
A green *preflight* is not a green full delivery E2E.

```sh
python3 tools/demo_smoke.py --report demo-read-results.json
python3 tools/demo_smoke.py --exercise-sync --report demo-sync-results.json
# Optional only when all verified server prerequisites are available:
python3 tools/demo_smoke.py --exercise-sync --exercise-approval --report demo-approval-results.json
```

Expected process exit codes: **0 all required checks PASS**, **1 a
real failure**, **2 BLOCKED / NOT VERIFIED**. Output contains status
codes and non-sensitive checkpoints only; do not upload credentials,
customer notes or raw Source responses.

**Verification details must be filled from actual executed CI or shell
run:** commit SHA, run URL, exact test counts, PostgreSQL migration
revision, named status results, idempotent row-count query and browser
viewport. Do not replace `NOT VERIFIED` based on code review.

## Blocking dependency handoff

1. **P0: Dev 1 + Dev 2** — implement/review approved Sales Sync & Check
   service+route transaction (market/store RBAC, confirmed mapping at
   decision instant, immutable routing+audit, idempotency/version,
   `unresolved` if source cannot be verified). No POS write or polling
   decision; add real PostgreSQL tests and OpenAPI/docs/CHANGELOG.
2. **P0: Dev 1** — regulatory D7 56-day verified evidence and official
   work-shift/rest check remain fail-closed. Do not mark synthetic
   `verified=false` data as qualified just to approve a plan.
3. **P0: Dev 1 + Dev 2** — WMS physical-stock authority, stock-scope
   evidence and authorized reservation ACK, all with real transaction
   and rollback evidence. A fake staging WMS ACK must be labelled
   `simulated`, never a production reservation.
4. **P1: Dev 3** — integrate visible Sales Sync & Check results from
   real endpoint; record responsive/mobile browser evidence, warehouse
   and Driver display. Browser rendering is not proven by HTTP alone.
5. **P1: Dev 2** — after the independent contracts above land, rerun
   disposable real-stack preflight and approval smoke; record DB
   uniqueness, negative/positive planning, full E2E or explicit blockers.

No production scheduler, live GPS, customer email, third-party WMS
write or auto-merge was enabled as part of this work.
