---
name: cfo-dev2-integration
description: Implement or review CFO IT Consultant Dev 2 integration, simulated source system, ingestion, adapters, seed, routing, GPS, notifications, jobs, Docker Compose, CI and staging tasks. Do not use for backend planning-engine or frontend feature ownership.
---

# CFO Dev 2 — Source integration, data and infrastructure

Use for Dev 2's workstream; collaborate with Dev 1 and Dev 3 through documented contracts, not unsanctioned edits.

## Source of truth

1. Read `AGENTS.md` and **all** of `docs/09_AI_Coding_Rules.md` before editing code; its invariants and definition of done prevail.
2. Confirm active milestone, story and dependencies from `docs/08_Development_Plan.md` and `docs/10_Team_Assignment.md`. Also inspect the current branch, open work and the relevant US/AC/BR.
3. Read relevant sections of `docs/04_Tech_Stack_and_Architecture.md`, `docs/05_Database_Design.md`, `docs/06_API_Specification.md` (including the source-system contract), `docs/02_User_Stories_and_Acceptance_Criteria.md`, `docs/07_User_Flows.md` and `docs/HARNESS_SETUP.md`.

## Owned modules

- `source_system/` except `source_system/pos_ui/` (Dev 3).
- `backend/app/adapters/`, `backend/app/providers/`, `backend/app/jobs/`, `backend/app/seed/` and Dev 2-owned integration/notification/GPS services.
- `tools/`, `docker-compose.yml`, `Makefile`, `.github/workflows/`, source/contract/integration tests, and staging configuration.
- Coordinate changes to `backend/app/domain/`, `engine/`, `audit/` and API contracts with Dev 1 first.

## Mandatory implementation workflow

1. Check `git status --short`, active branch, actual code and current milestone; never overwrite someone else's uncommitted work.
2. State the exact US/AC/BR and a short plan with files, dependency order, test cases and any contract handoff. Split changes larger than ~400 lines of logic into reviewable PRs.
3. Implement the simulated POS/WMS/ERP source under its separate database and `source_system/openapi.yaml`. CFO only **reads** upstream source data; do not add write-back paths.
4. Make ingestion repeatable: checkpoints with required overlap, idempotent upsert/version handling, explicit rejects and pending unmapped SKUs, actionable run status and tests for duplicates/retries/stale data.
5. Keep seeds deterministic (specified random seed `20261104` and injected `APP_NOW`); reproduce documented scenario orders, vehicle capacity and permissions; derive demo password from `SEED_DEMO_PASSWORD`, not a committed value. Never overwrite existing environments or reset production databases.
6. For jobs/outbox/GPS/routing: use injected clock/config, idempotent task execution, supported retry/dedupe and fallback behavior. Enforce dispatcher-only GPS server-side, privacy/retention, and no PII or secrets in technical logs. Do not turn on paid/external integrations without authorization.
7. Run focused contract/integration tests, `python tools/harness.py backend` and `python tools/harness.py verify` (PowerShell: `py -3.12 tools/harness.py ...`). Run `smoke` only against an explicitly prepared local stack. A test not executed is **NOT VERIFIED**.
8. Hand over any source OpenAPI or backend response schema change to Dev 1/3. Report exact tests, services affected, migration/seed implications and blockers. Open a PR when requested; never auto-merge.

## Coordination and stop conditions

- Do not unilaterally change `05` or `06`; approved contract changes must update specifications, affected implementation, tests and `docs/CHANGELOG.md` together.
- Test concurrency with real PostgreSQL for approvals, exclusion constraints and stock/labour commitments, coordinating with Dev 1.
- Do not disable CI jobs, suppress failures, weaken auth, expose tokens, or claim green CI without observing it.
