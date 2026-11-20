# E0-04 — stock ingest to a feasible planning run

This is a disposable, synthetic Swedish demo on a separate PostgreSQL Compose
project. It stops at a **proposed** plan. It never calls `/approve`, sends email,
or claims legal driver verification. See `docs/DEMO_SETUP.md` for the base setup.
To continue from the proposed plan with WMS and an approval in the browser,
follow [the T27 manual retest](T27_INTEGRATED_E004.md#retest-manually-on-a-running-cfo-demo-e004).

## Fixed scenario

| Field | Value |
|---|---|
| Source `external_ref` | `SE-2026-000249` (`SUBMITTED_FOR_PLANNING`) |
| Customer/store | synthetic `DEMO-C002`, `ST-001` |
| SKU/quantity | `SE-BRD-GYP-13`, 10 declared stock units |
| Delivery | 2026-12-02, 07:00–16:00 Stockholm |
| `APP_NOW` for Source and CFO planning | `2026-12-01T10:05:00+01:00` |
| Warehouse/driver/vehicle | STO, `DEMO-DRIVER-2`, `STO-12-04` selected by the real planner |
| Stock scope | SKU above × active SE warehouses GBG/STO/MLM |

The fixed future clock is intentional: grants and scope are approved at the
actual PostgreSQL wall time, so the old 2026-11-04 Source batch cannot be
accepted under a scope approved later. **Run the fresh-DB preparation before
2026-12-01 10:05 Stockholm.** After that, a newly reviewed future demo clock
and corresponding Source/driver/shift fixtures are required. Never backdate
scope or edit an old batch timestamp.

## Reproduce after reset

1. Create private untracked `.env` as in `docs/DEMO_SETUP.md`; install Python
   3.12 backend/tool dependencies, including `python-dotenv` and timezone data.
   Use Docker Desktop and Git Bash on Windows. The command below uses only
   localhost and the hard-coded isolated project `cfo-demo-e004`.
2. If this same **disposable** project was previously run and its data is no
   longer needed, reset only it: `docker compose --env-file .env -p cfo-demo-e004 down -v`.
   Do not use `down -v` on another project.
3. Run `py -3.12 tools/e0_04_prepare.py` on Windows (or
   `python3.12 tools/e0_04_prepare.py` on POSIX). On Windows, set the Python
   interpreter to the installed backend venv if its packages are not global.

The command checks the disposable context, runs the unchanged base seed,
provisions two dedicated Admin identities, issues separate audited `scope`
grants to the author and independent approver through the PR #216 service,
creates and approves scope version 1, then switches both services to the fixed
E0 clock. It builds a hash-attested **synthetic-only** D7 fixture for driver 2,
creates named manager-attributed Dec 1–2 shifts, records STO attendance via
`set_attendance`, and loads the STO vehicle's separately declared synthetic
mass/Regulation 561 context with an audit row. It publishes Source batch 2
through `app.stock_batches.publish` using a new observation of the simulated
WMS state after scope approval. CFO ingests it through `sync_entity` and the
stock writer. Sales Sync now creates the CFO order; the configured fallback
routing provider prepares route pairs before Sales Check feasibility.

The source and CFO batch remain separate. No script writes
`ops.stock_snapshot` directly. Synthetic driver evidence has
`legal_verified=false`, is accepted only under `APP_ENV=test`,
`DEMO_DISPOSABLE=1`, exact clock and hash-matched fixture, and is not an HR or
tachograph attestation. The base 2026-11-04 fixture remains unchanged.

This is a compatibility demo for the currently merged planner. The approved
Round 3 contract replaces individual attendance/56-day D7 planning inputs
with day capacity and driver availability. Once that migration and planner
land, revalidate E0-04 against the new contract; these synthetic inputs are
not production policy.

## Observed clean replay (2026-11-19)

Before the fix, the base order `SE-2026-000149` gave `POST /plan` HTTP 409
`RESOURCE_CONFLICT`. `app.demo_stock_preflight` reported
`STOCK_SCOPE_NOT_EFFECTIVE`, `NO_ACCEPTED_STOCK_BATCH`,
`STOCK_SNAPSHOT_MISSING` and missing `(warehouse_id, product_id)` pairs
`(6,26)`, `(7,26)`, `(8,26)`. The old batch's stock sync failed with
`STOCK_SCOPE_NOT_CONFIGURED`: 300 rows in, zero accepted.

After a full reset and the E0-04 preparation, the new Source batch `2` was
complete (300 Source rows); CFO `ops.stock_write_run` accepted 3/3 in-scope
rows under scope version `1`. Preflight for `SE-2026-000249` returned `PASS`,
`blockers=[]`, `missing=[]`, `stale=[]`, accepted batch `2` as of
`2026-12-01T09:00:00Z`. Sales Sync now returned HTTP 200,
`routing_status=cfo`, CFO order `1`. Sales Check feasibility returned HTTP
200, `runId=1`, `result=feasible`, one plan. `GET /plans/1` returned HTTP 200
for Sales, rank 1, `status=proposed`, one vehicle. PostgreSQL showed plan `1`
at warehouse `7` (STO), route provenance `fallback`, with `stock`,
`preparation`, `truck`, `site_date`, and `safety` all `passed=true`.
The order status remained `PLANNED`; approval was not attempted.

The command writes a safe, credential-free `.e0-04-after.json` containing the
Sales-visible plan log. Browser rendering is **NOT VERIFIED** because the
computer-use browser failed to initialize; the HTTP detail response and
PostgreSQL record above verify the proposal can be opened via the API.

Verification: `tools/e0_04_prepare.py` PASS from an empty project; 44 targeted
backend PostgreSQL tests, 12 Source stock tests, the E0-04 D7 fixture test,
and 17 Sales Sync/Check UI tests PASS. `tools/harness.py doctor` and `smoke`,
frontend lint and build PASS. The broad backend pytest gate was stopped after
its first 4% because it contains 1,467 tests on this host: **NOT VERIFIED**
as a full suite. The full frontend test gate failed in three unchanged suites
(`SignIn`, `PlanReview`, `PlanReviewActions`): 55 failed, 983 passed. The
affected Sales Sync/Check suite passed independently.

During diagnosis, the first Dec 1 run reached HTTP 200 but was infeasible
because prep-day attendance was missing. Once that was corrected, routing
data was absent; `app.demo_e0_04_routes` prepared it through the approved
fallback path. Vehicle scope then remained unknown; the final synthetic
classification used the checked transport context from the existing D7
fixture. None of these steps removed a planner safety check.
