# M0 Dev 2 implementation and handoff — 2026-11-06

Branch: `feat/m0-infra-source`. Changes are local and uncommitted; no merge or push
was performed. No backend migrations, authentication, planning engine, frontend UI,
POS UI, or design documents were changed.

**M0 is not complete.** Infrastructure and source foundation have working evidence,
but CFO health and migrations require Dev 1, and scenario seed belongs to M1.
The final full Harness invocation returned FAIL; the details below preserve that result.

## Task 1 — Compose and source database

Files: `docker-compose.yml`, `tools/postgres/init-source-db.sh`, `tools/.gitattributes`.

- Preserved exactly five services: postgres, mailpit, source-se, cfo-api, cfo-web.
- Added PostgreSQL/source/CFO health checks and readiness dependencies.
- Supplied container DNS URLs, Mailpit connection, frontend API URL and configurable
  local host ports through environment configuration. Required secrets have no defaults.
- Added a separate source database on the same PostgreSQL service, preserving the
  five-service architecture; instance data lives in configurable `src_<market>` schemas.
- The source DB initializer creates a missing database and never drops one. Fresh
  volumes run it automatically; existing volumes use the explicit `source-db` target.
- Bound local service ports to loopback. No Docker volume was deleted.

Executed using `tools/m0_smoke.py` in isolated project `cfo-m0-check-864342d3`:

| Command / check | Result |
| --- | --- |
| `docker compose ... config --quiet` | PASS |
| `docker compose ... up -d --build --wait postgres mailpit source-se` | PASS |
| `docker compose ... exec -T source-se python -m app.init_db` | PASS |
| `docker compose ... up -d --build cfo-api cfo-web` | PASS: all five services started |
| Source `GET /api/v1/health` | PASS: HTTP 200, `status=ok`, `db=ok` |
| Web HTTP | PASS: HTTP 200 |
| CFO `GET /api/v1/health` | FAIL/BLOCKED: handler remains `NotImplementedError`; container unhealthy |
| `docker compose ... stop` | PASS: stopped only the new test project |

The test project used randomly generated credentials in memory and tmpfs PostgreSQL.
Its stopped containers and built images remain for inspection; no existing container
or volume was deleted. Source application startup itself does not create tables.

## Task 2 — Source foundation

Files: `source_system/app/{config,db,models,init_db,main,api}.py`,
`source_system/pyproject.toml`, `source_system/Dockerfile`,
`source_system/.dockerignore`, `source_system/README.md`,
`source_system/tests/unit/test_foundation.py`,
`source_system/tests/integration/test_database.py`.

- Added configuration validation, async engine lifecycle, bounded DB connectivity
  probe and HTTP 503 on failed probes without exposing connection details.
- Added all eight minimum `src_*` tables from `05` section 10, with NUMERIC amounts,
  timezone-aware timestamps, foreign keys and source order status constraint.
- Added explicit schema bootstrap and database update triggers. Re-running bootstrap
  preserves existing rows; future table evolution requires reviewed source migrations.
- Recorded physical storage choices in `source_system/README.md`; these need review
  before accepting the complete M1 source contract. Full POS payload mapping remains M1.
- Corrected source image packaging so application files exist when the package is built.

Final source commands executed by the Harness, with real PostgreSQL 16:

| Command | Result |
| --- | --- |
| `python -m ruff check .` | PASS |
| `python -m black --check .` | PASS, 9 files unchanged |
| `python -m mypy app` | PASS, 7 source files |
| `python -m pytest tests/unit tests/integration` | PASS, **17 tests: 12 unit + 5 integration** |

Integration evidence: all eight tables/timestamps exist; bootstrap retains data;
updates advance timestamps; PostgreSQL rejects invalid foreign keys and order states;
NUMERIC values retain Decimal precision; health executes a real DB query.
Tests drop only their own uniquely generated `src_test_*` schemas. Missing
`SOURCE_TEST_DATABASE_URL` fails rather than skipping integration tests.

Traceability: M0 source foundation in `08` section 3 and `10` M0; `05` section 10;
health/source contract in `06` section 16; BR-GEN-01/02. This does **not** claim
US-SRC-02 AC1 completion: the full shared SE/second-instance contract test is M1.
US-SRC-01 seeds and US-SRC-03 Sales Validation remain M1, as do source business
endpoint API-key enforcement and POS behavior. Existing M1 stubs were preserved.

## Task 3 — Makefile and development tools

Files: `Makefile`, `tools/check_m0_dependencies.py`, `tools/m0_smoke.py`,
`tools/tests/test_m0_tools.py`.

- Kept the existing local commands; `up` now builds images before starting them.
- Added config, source database/bootstrap/tests and container migration/seed targets.
- Added explicit detection of known stub dependencies. The current Alembic env is
  empty and could otherwise exit successfully without running migrations.
- Added an isolated Compose verification runner with generated credentials and
  Windows Docker credential-helper PATH support.

| Command | Result |
| --- | --- |
| `make -n up` | PASS: resolves to `docker compose up -d --build`; underlying Compose startup tested above |
| `make test` (Python 3.12 backend venv activated) | PASS, 15 backend tests |
| `make migrate` | BLOCKED, exit 2: Alembic env and all eight revision files remain stubs |
| `make seed` | BLOCKED, exit 2: M1 seed generator remains a stub |
| `python -m unittest discover -s tools/tests` | PASS, 4 tests |
| Ruff for the new Python tools | PASS |

Tool tests reject no-op migration scaffolds, reject empty OpenAPI artifacts, accept
matching/reject changed contracts, and reject HTTP 200 error payloads in smoke checks.
New Make wrappers were reviewed/dry-run through their equivalent underlying commands;
the table identifies the Make targets actually executed. GNU Make with a POSIX shell
is supported; Windows setup is documented in `source_system/README.md`.

## Task 4 — CI and contract checks

Files: `.github/workflows/ci.yml`, `.github/actions/postgres/action.yml`,
`tools/check_openapi.py`.

- Backend: Python 3.12, Ruff, Black, mypy, import-linter, pytest and tools tests.
- Source: Python 3.12, Ruff, Black, strict mypy, unit and real PostgreSQL tests.
- Frontend: Node 20, `npm ci`, lint, test, build.
- Replaced the committed CI database password with a random job-local password,
  masked in GitHub Actions and supplied to PostgreSQL through the environment.
- Added exact OpenAPI comparison against versioned, approved artifacts when present.
  An empty/missing artifact is recorded as BLOCKED/NOT VERIFIED in the job summary;
  it is never described as a passing contract test. Direct comparison exits 2 for
  missing/empty artifacts and 1 on differences.

Workflow and composite action YAML parsed successfully. Contract-tool behavior is
covered by the tools tests. A remote GitHub Actions run was **not performed**.
Current artifacts: CFO `contracts/cfo.openapi.json` absent; source `openapi.yaml`
has `paths: {}`. Both contract comparisons remain **BLOCKED/NOT VERIFIED**.

## Task 5 — Harness results and final review

Files: `tools/harness.py`, this report.

Added source checks to `verify`, including PostgreSQL integration tests. Tightened
health verification to require HTTP 200 with both `status=ok` and `db=ok`.

`python tools/harness.py verify`, invoked by the isolated runner with Python 3.12:

| Gate | Result |
| --- | --- |
| Repository/tooling doctor | PASS |
| Backend Ruff / Black / mypy / import-linter | PASS |
| Backend pytest | PASS, 15 tests |
| Frontend lint / Vitest | PASS, 1 test |
| Frontend build in elevated runner | FAIL: EPERM while removing `frontend/dist/assets` |
| Source Ruff / Black / mypy | PASS |
| Source unit + PostgreSQL tests | PASS, 17 tests |
| Overall `verify` | **FAIL**, preserved faithfully |
| Overall `smoke` | **FAIL**: source passes, CFO health fails |

Follow-up: `npm.cmd run build` from the normal workspace execution context **PASS**,
including the PWA output. The elevated-run failure is therefore specific to access
to existing build artifacts; no frontend code or lint rules were changed to avoid it.
Do not report a full Harness PASS by combining these separate runs.

`git diff --check` passed. Tracked changes are confined to Dev 2 scope. No secret
values were added to source/config files; the existing literal CI DB password was
removed. No tests were skipped and no `continue-on-error` was introduced.

## Handoff dependencies

| Owner | Required handoff | Acceptance / next verification |
| --- | --- | --- |
| Dev 1 | Implement CFO `/api/v1/health` with real DB/dependency checks | Harness smoke must pass both APIs; process startup alone is insufficient |
| Dev 1 | Implement Alembic env and revisions `0001…0008` | `make migrate` proceeds past preflight; migrations verified on a clean PostgreSQL DB |
| Dev 1 | Authentication and minimum account data | Seed-account login/RBAC acceptance remains unverified; no auth code was changed |
| Dev 1 / Dev 3 | Review backend/frontend Docker build contexts and Dockerfiles | Add scoped `.dockerignore` rules for local venv/node_modules/build outputs; make frontend container installs use the lockfile |
| Dev 3 / local environment owner | Resolve `dist/assets` access across execution contexts | Re-run complete Harness from one consistent context and obtain a single successful build |
| Dev 1 | Approved CFO OpenAPI artifact | Supply reviewed artifact at `contracts/cfo.openapi.json`; CI comparison becomes required automatically |
| Dev 2, M1 | Complete source API contract and scenario seed | Replace the empty source contract through normal review; US-SRC-02 AC1 and `make seed` can then be accepted |

Build evidence for the Docker context handoff: backend sent about 183 MB and frontend
about 222 MB, including local dependency directories, because their existing build
contexts have no `.dockerignore`. Both images did start in this test. Those files
were left to their owners as requested.
