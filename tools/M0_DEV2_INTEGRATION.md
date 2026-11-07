# Dev 2 — M0 integration

This branch integrates the Dev 1 handoff locally for verification. It does not
approve pending contracts or merge those branches into main.

## Minimal account seed

Run migrations first, then `make seed-m0` (local backend environment) or
`make seed-m0-docker`. Supply `SEED_DEMO_PASSWORD` through the environment.
The command creates dispatcher, admin, sales, owner and projectlead demo accounts
listed in `docs/M0_BACKEND_HANDOFF.md`. Each gets an employee and one assignment;
roles and KPI scopes are copied from the migrated position records.

Synthetic bootstrap locations are DC, HQ and ST-001. They use Göteborg coordinates
and fixed 2026-01-01 employment/assignment start dates so the documented demo clock
can sign in. These are minimal login fixtures, not the full M1 business dataset.
Existing locations are reused, never overwritten. Existing account passwords,
roles, scopes and disabled status are preserved. Conflicting demo identity or
assignment causes a transaction rollback. No deletes or password reset occur.

`make seed` remains the full M1 entry point and still reports BLOCKED until its
scenario generator is implemented. A successful minimal seed does not satisfy
US-SRC-01 (full dataset and 18 scenarios).

## Isolated smoke

`python tools/m0_smoke.py --docker <docker executable>` starts a uniquely named
Compose project with PostgreSQL on tmpfs and random secrets kept in memory.
It bootstraps the source, builds the API, migrates CFO to head, seeds minimal
accounts, starts API/web, checks health and login/profile/invalid-token behavior,
disables the isolated dispatcher account to verify token revocation and restores it,
then runs Harness verify and smoke. TEST_DATABASE_URL is supplied so backend
PostgreSQL tests execute instead of skipping. Containers in this new project are
stopped afterwards; existing projects and volumes are not removed.

Python subprocesses enable UTF-8 mode. The installed Alembic still reads its INI
with explicit `encoding="locale"`; on Windows cp1252 this fails on Vietnamese
comments in `backend/alembic.ini`. Dev 1 owns the Alembic configuration: replace
those comments with ASCII or supply an approved UTF-8-compatible Alembic setup.
This Windows gate remains failed until that dependency is resolved.

Remaining M0 acceptance includes UI login.
OpenAPI baselines and team approval of Dev 1's pending contracts remain separate.

## Verification — 2026-11-07

- Final isolated stack: Compose config PASS, all five services start, CFO
  `alembic current` is `0008 (head)`, source/CFO health and web HTTP PASS.
  Login/profile, missing/invalid token and disabled-account token revocation PASS;
  the isolated account is restored afterwards. Source: 17 tests passed.
  Harness `smoke`: PASS. Harness `verify`: FAIL on Windows backend pytest only;
  the full smoke script correctly exits 1. Test containers were stopped without
  deleting volumes or touching existing projects.
- Backend Python 3.12 / PostgreSQL 16 in the isolated Linux container:
  `TEST_DATABASE_URL="$DATABASE_URL" pytest -q`: **173 passed**, no skipped tests.
  The container was given dev dependencies and `/docs` for schema-drift tests;
  application images do not need test dependencies or design documents at runtime.
- New seed integration coverage: five accounts and Argon2 passwords, roles/scopes
  from positions, one assignment each, repeatability without resetting disabled
  accounts or passwords, missing password rejection and conflict rollback.
- Harness frontend: `npm run lint`, `npm run test` (1 test), `npm run build`: PASS.
- `python -m unittest discover -s tools/tests`: 4 passed.
- Windows Harness backend: Ruff, Black, mypy and import-linter pass. Pytest fails
  on Alembic's locale decoding described above; Linux success does not turn this
  Windows result into a pass.

Changes: `Makefile`, `backend/Dockerfile`, `backend/.dockerignore`,
`backend/app/seed/m0_accounts.py`, `backend/tests/integration/test_m0_seed.py`,
`tools/m0_smoke.py`, and this report. No auth implementation, migrations,
business logic, frontend UI or API/schema contracts were changed.

Next independent Dev 2 slice is M1 source API and full scenario seed under
`06` section 16 / `08` section 5, with contract review by Dev 1 and POS UI
integration by Dev 3. The minimal seed in this change is not that deliverable.
