# Demo MVP — Swedish pilot: reproducible setup

**Status: partial / fail-closed.** The steps below reproduce the synthetic Source,
CFO reference data, official *demo-only* shift schedule and live HTTP checks on
one isolated Compose installation. They do **not** presently reproduce a
fully approved, driver-executable happy path. See
[DEMO_TEST_RESULTS.md](DEMO_TEST_RESULTS.md) for exact blockers and evidence.

## 1. Scope and contracts

- **One walkthrough slice:** Swedish market `SE`, originating store `ST-001`,
  Göteborg warehouse `GBG`, vehicle `GBG-03-02` (B class) or another
  verified eligible vehicle chosen by the *actual planner*, demo driver
  `driver1@cfo.demo`. Do **not** assign a driver or claim a vehicle match
  merely because the reference record exists.
- **Fixture cases:** `SE-2026-000149` (light, physically plausible standard workflow candidate),
  `SE-2026-000137` (requested-date/resource negative scenario; actual engine
  result must be measured), `SE-2026-000156` (pending SKU `88412`,
  definitive legacy routing negative case). These are existing synthetic
  fixtures, not guaranteed outcomes. Do not change the golden expectations.
- **Other locations are present:** The approved deterministic seed already
  contains 25 stores, 3 warehouses, 9 vehicles, 18 current orders and 48
  historical source orders. This runbook **uses only one store and warehouse**
  for the walkthrough. It does not silently delete or reshape the approved
  broader seed to pretend the database physically contains one location.
- **Clock:** `APP_NOW=2026-11-04T10:05:00+01:00` for **both** Source and CFO.
  This is a fixed Stockholm instant (09:05 UTC), not today's wall clock.
- **Owner decisions:** `DEC-SRC-D1-001`, `DEC-ROUTING-002`,
  `DEC-INT-SEED-GOLDEN-20261109`, official schedules `ASM-007/009`,
  `DEC-DEV2-D7-001`, `DEC-WMS-RESERVE-SYNC`. Never manufacture 56-day D7
  evidence, GPS consent, approval, stock ACK, attendance or a driving-duty
  declaration. The generated 560 history entries are **explicitly unverified**.
  Market GPS remains disabled, no customer email or WMS production write.
- **Architecture:** The simulated Source API is a real separate PostgreSQL
  database and publishes WMS stock batches; CFO consumes only its read API.
  T07 polling cannot decide routing or initialize a new undecided CFO order.
  **Sales Sync & Check** is the required first acceptance action.

## 2. Requirements and isolated configuration

Use Docker Engine/Compose v2, Python 3.12 for CLI/unit tests, Git Bash/WSL
or a POSIX shell, and repository checkout at the intended branch or latest
`main`. Do **not** run against a company production database. No credentials
are committed or printed.

Create an untracked root `.env` based on `.env.example`, and securely set
`POSTGRES_PASSWORD`, `DATABASE_URL`,
`SOURCE_SE_DATABASE_URL`, `SOURCE_SE_API_KEY`, `JWT_SECRET`,
`SEED_DEMO_PASSWORD`, `INTERNAL_TICK_KEY` and `CORS_ORIGINS`.
Use separate `cfo` and `source_se` database URLs on the Compose
`postgres` hostname, with identical private DB credentials. Do not place
real customers, accounts or services here. In particular, never set a real
SMTP endpoint or production WMS credentials.

The **non-secret** demo values must be:

```dotenv
APP_ENV=test
DEMO_DISPOSABLE=1
COMPOSE_PROJECT_NAME=cfo-demo-sweden
APP_NOW=2026-11-04T10:05:00+01:00
SOURCE_DB_NAME=source_se
SOURCE_SCHEMA=src_se
VITE_API_URL=http://localhost:8000/api/v1
CORS_ORIGINS=["http://localhost:5173"]
```

Export your private `.env` values into the shell before running the
guarded setup (e.g. `set -a; . ./.env; set +a` on POSIX shells). The
Compose configuration alone does not make every variable visible to local
Python processes. Use a **unique `cfo-demo-*` project name**; never reuse
an existing non-disposable Compose project or data volume.

## 3. Start, migrate and seed (never silently reset)

From repository root:

```sh
bash tools/demo_setup.sh
```

This performs in order:

1. Refuses non-test APP_ENV, unknown clock, missing private environment keys
   or a non-`cfo-demo-*` project; validates Compose.
2. Starts dedicated PostgreSQL and creates its separate Source database;
   starts Source, CFO, Mailpit and frontend on localhost.
3. Initializes Source `src_se` schema and applies CFO Alembic to `head`.
4. Runs existing `app.seed.generate_data` and exports the *unchanged*
   deterministic manifest `demo-fixtures.json`. Its exit code **2 is
   expected**, meaning reference/roster preparation succeeded but E2E and
   regulatory assertions are not complete. The script requires exactly this
   partial-demo status; it does not reinterpret it as a PASS.
5. Copies that manifest to Source and calls `app.seed_demo` using the
   already implemented idempotent order/stock publisher. The source
   publisher is the only writer of its physical-stock batch.
6. Binds the existing Swedish market row to the local
   `http://source-se:8100/api/v1` adapter using `app.demo_configure`.
   The reference migration leaves `source_base_url` unset: this guarded
   step is idempotent, accepts only the existing `SOURCE_SE_API_KEY`
   reference, and rejects any conflicting URL without overwriting it.
7. Executes existing `ingest_service.sync_entity` for customers, products,
   inbound and fleet using `backend/app/demo_ingest.py`. Any partial/error
   exits **2**, never advances a synthetic SUCCESS claim.

No source order is placed into CFO merely by seeding. No direct SQL is used
to invent a route, planning run, approved plan, committed reservation or
driver duty.

**Re-run behavior:** Existing demo identities, versions and scheduled shifts
are not overwritten; conflicting fixture manifests and source orders abort.
For repeatability after a deliberate test mutation, choose a *new disposable
project*, rather than resetting an existing shared database.

## 4. Live API smoke and negative path

With the stack up, run the read-only verifier (uses the exported
`SOURCE_SE_API_KEY` and `SEED_DEMO_PASSWORD`; never displays them):

```sh
python3 tools/demo_smoke.py --report demo-read-results.json
```

It checks live Source/CFO database health and frontend HTTP, Source API key
denial, source submitted order versions, repeated GET, role-specific CFO
JWTs (Sales/Dispatcher/Warehouse Manager/Driver), scoped order reads, and
CFO unauthenticated denial. **HTTP 200 for the frontend is not proof of
browser rendering**. An exit code **2 means BLOCKED/NOT VERIFIED**, not
PASS.

To explicitly test *mutating* Sales Sync & Check **only in this disposable
test Compose environment**, use:

```sh
python3 tools/demo_smoke.py --exercise-sync --report demo-sync-results.json
```

The script checks the documented `POST /integration/orders/sync-now` with
a stable UUID `Idempotency-Key` for `SE-2026-000149`, repeats it with
the same body/key, verifies the same CFO order is readable by Sales and
Dispatcher, then checks the unmapped `SE-2026-000156` remains `legacy`
with no CFO order. No POS write. If the endpoint is absent (current
`main`), it reports **BLOCKED** and does not pretend the order was
created by polling.

**Authentication rate-limit:** each probe logs in four demo roles. CFO's
real five-attempts-per-minute/IP limiter remains active. When running
the read-only and mutating probes manually back-to-back, allow more than
60 seconds between them; otherwise the second probe correctly fails
with HTTP 429. The isolated CI preflight respects that window without
disabling or resetting the limiter.

If a valid plan is produced, an *optional, explicit* guarded attempt
`--exercise-sync --exercise-approval` submits only a server-identified
eligible rank-1 Sales plan through the approved API. Approval might
legitimately return 409 until D7/stock reservation gates are proven; such a
response is **BLOCKED**, not a synthetic successful delivery. Do not
enable real WMS writes to make this pass.

**PostgreSQL uniqueness check (read-only, after successful sync):**

```sh
docker compose exec -T postgres psql -U cfo -d cfo -Atc \
  "SELECT count(*), min(source_version), max(source_version)
   FROM ops.customer_order WHERE external_ref='SE-2026-000149';"
```

Expect **exactly one** row, source version equal to the Source GET version.
This query must actually run before marking database uniqueness PASS.
Likewise check the routing record/audit is immutable on repeated requests.
The HTTP probe **does not** claim that a matching ID alone proves DB
uniqueness.

**Automated, read-only PostgreSQL evidence** is now part of
`tools/demo_ci.py` and may also be executed after the mutating HTTP probe:

```sh
python3 tools/demo_db_verify.py \
  --sync-report demo-sync-results.json \
  --report demo-db-results.json
```

This tool only runs with `APP_ENV=test`, `DEMO_DISPOSABLE=1`, the exact
approved `APP_NOW`, and a `cfo-demo-*` project. It independently re-reads
the authenticated Source order versions, then uses PostgreSQL `psql` in
the **named disposable** Compose project to prove that order
`SE-2026-000149` has exactly one CFO row and one CFO routing decision
at the matching source version, and that pending-mapped
`SE-2026-000156` has zero CFO rows and one immutable legacy route.
No order, routing, stock or planning state is written by the verifier.
It never prints raw Source payloads, database errors or credentials.
Exit 0 = both real checks PASS; 2 = Sync & Check BLOCKED (no proof
fabricated); 1 = evidence FAIL or unsafe environment. A green *preflight*
with Sync BLOCKED is not an end-to-end success.

The real-Compose CI artifact `demo-preflight-status` now includes
`demo-ci-db-results.json`, separate from the HTTP smoke report.
The prior manual SQL remains a second inspection option. The verifier
does not on its own prove route audit immutability under concurrent
writes or any WMS/D7 approval; those need distinct PostgreSQL/E2E tests.

## 5. Safe reset — explicit destructive operation only

Only after confirming the named project is truly disposable and has
no business data:

```sh
bash tools/demo_reset.sh --confirm-disposable-data-loss
```

This targets only `COMPOSE_PROJECT_NAME=cfo-demo-*` and deletes *that*
Compose project's containers **and volumes**. It never runs as part of
setup or smoke and does not delete locally exported fixtures/results.
Do **not** run `docker volume prune`, unscoped `down -v`, or a
destructive SQL truncation against other environments.

## 6. Verification and ownership

- **Dev 2:** seed, Source read adapter, batch/reference ingestion, demo
  environment scripts and source privacy. Existing fixtures/rosters are not
  reimplemented. The live smoke documents raw PASS/FAIL/BLOCKED.
- **Dev 1:** missing approved Sales Sync & Check routing transaction/API;
  real PostgreSQL idempotency and market/store-scope tests; D7 legal evidence
  gate and WMS reservation/approval readiness. Consult Dev 3 on the exact
  payload; do not let T07 polling invent `order_routing`.
- **Dev 3:** Sales Sync & Check UI, selected Driver/Dispatcher presentation,
  mobile/browser E2E screenshots and display of blocked/unknown states.
- **Unresolved production/legal:** the isolated seed provides *official
  demo-only shift assignments*, **not** real regulatory compliance. Until
  attested 56-day driver history exists, no real plan approval/delivery
  claim; vehicle licence/class match is evaluated by the real planner.

See [DEMO_TEST_RESULTS.md](DEMO_TEST_RESULTS.md) for an evidence ledger that
distinguishes the CI fixtures from full E2E.
