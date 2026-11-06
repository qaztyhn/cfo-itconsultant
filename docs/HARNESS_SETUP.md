# CFO — Context + Harness setup (v1.2)

## What these files do

- `/AGENTS.md`: routing document for Codex / other coding agents; **not** an alternative PRD.
- `/tools/harness.py`: run existing quality gates in one command on Windows, macOS, or Linux; no automatic installation or DB modifications.
- `harness_templates/ci.yml`: **reviewed replacement proposal**, not automatically installed in `.github/workflows/`.
- `harness_templates/Makefile.append.txt`: optional targets to append to the existing `Makefile`.

The real repository already has `Makefile`, `docker-compose.yml`, and `.github/workflows/ci.yml`. Do **not** blindly overwrite them. The suggested additions extend the current setup.

## Start from the Git repository root

1. Copy `AGENTS.md` into repo root; `tools/harness.py` into `tools/`; and this file into `docs/`.
2. Ensure `docs/01` through `docs/10` exist, including `docs/06_API_Specification.md` (**this is present in the GitHub repository**, even though not in the uploaded bundle).
3. Run the read-only doctor:

```powershell
py -3.12 tools/harness.py doctor
```

4. Install dependencies according to existing project lockfiles/configuration (once, in the appropriate environment):

```powershell
py -3.12 -m venv backend/.venv
./backend/.venv/Scripts/python.exe -m pip install -e "./backend[dev]"
npm ci --prefix frontend
```

On macOS/Linux, use `python3.12 -m venv backend/.venv` and `./backend/.venv/bin/python -m pip ...` instead.

5. Run the fast feedback gates:

```powershell
py -3.12 tools/harness.py backend
py -3.12 tools/harness.py frontend
py -3.12 tools/harness.py verify
```

**Expected at current scaffold stage:** some gates may fail because code, tests, and frontend lint configuration are incomplete. Failure is a truthful TODO, **not** permission to disable a check.

6. For local service smoke checks, **use local/synthetic data only** and fill `.env` privately from `.env.example`. Never commit or print it. Start the existing Docker stack (`docker compose up -d --build`) and, once M0 migrations and health endpoints are implemented, run:

```powershell
py -3.12 tools/harness.py smoke
```

**Important:** the current `GET /api/v1/health` handler in CFO's `backend/app/api/v1/admin.py` still raises `NotImplementedError`; smoke must fail until it is implemented. The source-system health endpoint exists.

## Harness gates and actual proof

| Gate | Command / evidence | Milestone |
| --- | --- | --- |
| Context presence | `python tools/harness.py doctor` | immediately |
| Backend static + unit | `python tools/harness.py backend` | M0 onward |
| Frontend lint / test / build | `python tools/harness.py frontend` | M0 onward |
| Running services | `python tools/harness.py smoke` | M0 exit |
| DB schema correctness | Alembic migrations from **empty local PostgreSQL** + DB integration tests | M0, Dev 1 |
| OpenAPI contract diff | compare generated OpenAPI against an **approved machine-readable contract**; current markdown spec alone is not a safe auto-diff baseline | M0–M1, Dev 1/2 |
| AC test traceability | Each applicable `US-... AC...` maps to an automated test and result | per milestone |
| E2E and permission matrix | Playwright + real PostgreSQL, critical flows and RBAC/location-scope test | later milestones |

The wrapper intentionally does not implement/misrepresent migration, OpenAPI diff, AC coverage, or E2E gates. Add them after the corresponding test suites or machine-readable baselines actually exist.

## Add it to the existing workflow (Dev 2 review)

Minimal non-destructive integration: in the existing `.github/workflows/ci.yml`, after checkout and setup-python for backend, add a root-level command to run the doctor, or adopt the proposed replacement under `harness_templates/ci.yml` **after review**. The proposal adds frontend `npm run lint` and `npm run test`, but requires completing their configurations/tests; it should **not** be green until those gaps are fixed.

If using the existing Makefile, append only `harness-*` targets from `harness_templates/Makefile.append.txt`; preserve its `up/down/migrate/seed/test/lint` targets.

## Recommended M0 implementation order

1. Dev 2: verify environment and Docker build; fix Docker images/dependency install without altering product contracts.
2. Dev 1: real Alembic migrations `0001`–`0008`, DB smoke from empty DB, JWT/RBAC, audit, actual CFO `/api/v1/health`.
3. Dev 3: existing frontend dependencies and ESLint/Vitest configuration; login shell + API client mocks/tests.
4. Dev 2: connect real DB-backed smoke + CI, then verify M0 end-to-end with synthetic seed.

## Existing doc drift to resolve explicitly

`docs/09_AI_Coding_Rules.md` §4 invariant 10 includes multi-vehicle planning in v1.2, but one bullet in §13 still says multi-vehicle planning is outside MVP. Before implementing that area, team should correct the stale bullet via a reviewed doc change; do not silently reinterpret it.

`docs/10_Team_Assignment.md` still says "23 bất biến" in one checklist, while `09` v1.2 numbers **25**. Fix the count when editing documentation.

## Definition of "harness is ready"

A script existing is not proof that the project is finished. The M0 harness is ready only when: docs/contract gates are present; reproducible local setup works; migrations from empty PostgreSQL pass; CFO/source health succeed; backend and frontend checks run without fake skips; CI reports failures transparently; and an authenticated synthetic-data flow is demonstrably working.
