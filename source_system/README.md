# Source system foundation (M0, Dev 2)

Requirements: Python 3.12, PostgreSQL 16. Install `pip install -e ".[dev]"`
in a dedicated source virtual environment. Backend and source both use an `app`
package: run their commands from their respective directories, in separate processes.

## Local containers

Use the root Compose file. Supply secrets privately through environment variables
or an untracked root `.env` using the existing `.env.example` as a template.
`DATABASE_URL` must select CFO's `cfo` database at host `postgres`;
`SOURCE_SE_DATABASE_URL` must select the separate `source_se` database at that host.
Both URLs use `postgresql+asyncpg`. URL-encode credentials in connection URLs.
`POSTGRES_PASSWORD` must match these URLs. `SOURCE_DB_NAME` defaults to `source_se`;
if overridden, update the source URL accordingly. No database URL is printed by tools.

Compose passes `SOURCE_SCHEMA=src_se` to the source. Other instances use their own
`src_<market>` schema with identical code. Outside Compose, explicitly set
`DATABASE_URL` and `SOURCE_SCHEMA`; settings do not silently fall back to a live DB.

From the repository root:

Make targets support GNU Make with a POSIX shell (Linux, WSL, or Git Bash/MSYS2
on Windows). Put Docker on PATH and activate the backend Python 3.12 venv before
the existing local `make migrate`, `make seed`, `make test`, and `make lint` targets.
For source tests, activate the source venv or set `SOURCE_PYTHON` to its interpreter.
`migrate-docker` and `seed-docker` avoid requiring the backend packages on the host,
but still run the stdlib-only dependency check with `PYTHON` first.

```sh
make config
make up
make source-db
make source-init
```

The database initialization script runs automatically only for a new PostgreSQL
volume. `make source-db` explicitly creates a missing source database on an existing
volume, without dropping or replacing any database. `make source-init` explicitly
creates missing source tables and timestamp triggers. App startup performs no DDL.
The bootstrap preserves rows, but does not upgrade existing table definitions;
future schema evolution needs a reviewed source migration plan.

`GET /api/v1/health` remains public. It returns HTTP 200 with `status=ok, db=ok`
only after a real `SELECT 1`; unavailable DB returns HTTP 503 without exception
details or credentials. This proves connectivity, not POS readiness or seed coverage.
The query has a bounded timeout and the engine is disposed on shutdown.

## Schema implementation decisions

`docs/05` section 10 lists minimum columns rather than exact source DDL. The M0
models preserve those names and all eight tables. Text source IDs follow the examples
in `docs/06` section 16; money/quantities use PostgreSQL NUMERIC, timestamps use
TIMESTAMPTZ. Every table has created_at/updated_at, with a DB update trigger.
Stock uses (warehouse_code, sku), inbound uses (inbound_ref, warehouse_code, sku),
and calendar uses (vehicle_code, from_ts, to_ts) as natural keys. Source order lines
have an internal bigint identity and unique (order_id, line_no); line_no, sku, qty,
unit_price follow the API example. Order status is limited to the four source states.
These storage choices require review before the full M1 source contract is accepted.
Additional POS/contact payload mapping and validation are M1 work.

## Verification

```sh
python -m ruff check .
python -m black --check .
python -m mypy app
python -m pytest tests/unit
# Set SOURCE_TEST_DATABASE_URL to a disposable PostgreSQL test database first.
python -m pytest tests/unit tests/integration
```

Integration tests create unique `src_test_*` schemas in the supplied test database,
then drop only those schemas. No existing schema, Docker volume or business data is
deleted. Missing test DB configuration fails rather than skipping tests.
The root harness `source` and `verify` commands also require this variable.

For an isolated infrastructure run from the repository root:

```sh
python tools/m0_smoke.py
# If Docker Desktop is not on PATH:
python tools/m0_smoke.py --docker "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
```

Use a Python 3.12 environment with the development dependencies installed. This
runner generates credentials only in process memory, chooses unused host ports,
starts a new Compose project with tmpfs PostgreSQL, runs source tests and the
harness, then stops its own containers. Stopped containers/images remain available
for inspection. It returns nonzero if any required check fails, including CFO health.

Full POS endpoints, API-key enforcement for those endpoints, seed scenarios and the
shared SE/second-instance contract test are M1 work (US-SRC-01/02/03). The existing
M1 stubs remain unimplemented. The `paths: {}` OpenAPI file is not an approved
contract baseline; CI reports this dependency as BLOCKED/NOT VERIFIED.
