# Dev 2 — M0 integration (PR #41)

Updated against origin/main at 798aa22. This PR contains only M0 seed/build/smoke
changes; M1 source APIs, complete scenario seed and later Dev 2 components remain
separate. Assumptions: reviewed ASM-001/002/003 and the decisions register; no new
business decision or contract change.

## Minimal account seed

Run migrations first, then make seed-m0 or make seed-m0-docker. Supply
SEED_DEMO_PASSWORD privately through the environment. The seed creates the five
accounts required by docs/M0_BACKEND_HANDOFF.md, with Argon2 password hashes,
employees and one assignment each. Roles and KPI scopes come from hr.position.

DC/HQ/ST-001 and fixed 2026-01-01 dates are synthetic M0 login fixtures. Existing
identities, assignments, passwords, roles/scopes and disabled state are preserved;
conflicting identities/assignments roll back. No passwords are committed or reset.
make seed remains the separate full M1 generator and is not marked complete.

## Reproducible Docker build

The API image copies app before package installation so Alembic can import it.
Backend/frontend Docker contexts exclude environment files, local dependencies,
logs and build output. The web image uses npm ci with the committed package lock.
No frontend UI, dependency versions, auth implementation or migrations change.

## Isolated live-stack verification

Run python tools/m0_smoke.py --docker <docker executable> with the backend dev
Python environment. It creates a unique Compose project, random credentials in
memory and tmpfs PostgreSQL, without resetting existing projects or deleting volumes.

The runner:

1. Validates Compose and starts postgres, mailpit and source-se.
2. Creates dedicated cfo_test/source_test databases for destructive pytest fixtures.
3. Bootstraps the source, builds CFO, migrates to head and seeds minimal accounts.
4. Starts API/web and checks valid source/CFO health responses and web HTTP.
5. Checks login, profile, missing/invalid token and disabled-account revocation;
   restores the isolated account after the check.
6. Runs Harness verify against the test databases and Harness smoke against the apps.
7. Repeats authentication after Harness to prove test migrations preserved app data.
8. Reports service status and stops only its new test project's containers.

Published PostgreSQL is IPv4-only, so test DSNs use 127.0.0.1. Application and
pytest databases remain separate. A failed gate makes the runner exit nonzero.

## Validation and limits

Current-head Windows/Docker results and GitHub CI are recorded in the validation
section of https://github.com/qaztyhn/cfo-itconsultant/pull/41. Historical results
from older heads are not certificates for the updated head.

The former Windows Alembic INI encoding blocker was fixed by Dev 1 in PR #42 and
is included through main. No workaround or test suppression is added here.
Source tests run on real PostgreSQL. Seed integration tests cover Argon2 hashes,
roles/scopes, assignments, repeatability, disabled-account preservation and rollback.

The approved OpenAPI baselines are still absent/empty: contract comparison is
BLOCKED / NOT VERIFIED, independently of unit/integration test success. UI browser
login verification remains Dev 3's responsibility; HTTP/auth smoke is not UI E2E.
GNU Make is unavailable in this Windows shell; equivalent container/module commands
are executed by the runner. No unexecuted make target is claimed as verified.

npm ci reports existing audit findings in the committed frontend dependency tree;
this M0 infrastructure change does not upgrade packages or run npm audit fix --force.
Dependency remediation remains a separate Dev 3 task.

Files: Makefile, backend/Dockerfile, backend/.dockerignore,
backend/app/seed/m0_accounts.py, backend/tests/integration/test_m0_seed.py,
frontend/Dockerfile, frontend/.dockerignore, tools/m0_smoke.py and this report.
No API/schema/business contract is changed; this PR does not declare all M0 or M1 complete.
