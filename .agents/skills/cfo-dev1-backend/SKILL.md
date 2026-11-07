---
name: cfo-dev1-backend
description: Implement or review CFO IT Consultant Dev 1 backend-core tasks: FastAPI APIs, SQLAlchemy models, Alembic migrations, RBAC, planning engine, reservation, approval, execution, risk, KPI, revenue and audit. Do not use for frontend or source-system infrastructure work.
---

# CFO Dev 1 — Backend core

Use this skill for Dev 1's owned workstream, not as permission to change another developer's files.

## Source of truth

1. Read `AGENTS.md` and **all** of `docs/09_AI_Coding_Rules.md` before making code changes. Its priorities, invariants and definition of done override this skill.
2. Check `docs/10_Team_Assignment.md` for ownership, `docs/08_Development_Plan.md` for M0–M9 dependencies and the active issue/PR for the current task. Never assume the next milestone from a stale prompt.
3. Read task-specific `docs/05_Database_Design.md`, `docs/06_API_Specification.md`, `docs/04_Tech_Stack_and_Architecture.md`, `docs/01_PRD.md`, `docs/02_User_Stories_and_Acceptance_Criteria.md`, and `docs/07_User_Flows.md` as needed. Identify exact US, AC and BR IDs before coding.

## Owned modules

- `backend/alembic/`, `backend/app/core/`, `backend/app/domain/`, `backend/app/engine/`, `backend/app/audit/`.
- Dev 1-owned `backend/app/services/` and `backend/app/api/v1/` modules, based on `docs/10_Team_Assignment.md`.
- Relevant backend unit and integration tests. Dev 2 owns adapters/providers/jobs/seed/infrastructure; Dev 3 owns frontend.

## Mandatory implementation workflow

1. Check `git status --short`, branch, existing code, test baseline, active milestone and dependencies. Do not overwrite another agent's uncommitted changes.
2. Produce a 5–10-line plan listing touched files, US/AC/BR, tests, and cross-owner dependencies. Keep each PR approximately <=400 changed lines of logic; split larger changes.
3. Add acceptance and failure-path tests before or alongside implementation. Name AC tests `test_US_<EPIC>_<NN>_AC<k>_...`. Use real PostgreSQL for migrations, constraints, locking and transaction tests.
4. Implement thin FastAPI routers, typed Pydantic schemas, service transaction boundaries, exact API error codes, RBAC **and location scoping**, and auditable business operations. Do not silently change `05` or `06`.
5. For engine changes, write pure, deterministic functions without I/O, DB, logging, external clocks or network. Use `Decimal`/integer-minute arithmetic, injected time and config; table-driven edge-case tests; target >=90% line coverage of engine.
6. Protect all domain invariants: dispatcher-only approval; plan holds may overlap, stock/labour locks are acquired **on approval**; deterministic lock order; order status via `transition()`; decision log in the **same transaction**; a single order may use several vehicles, but no trip combines orders; GPS is dispatcher-only.
7. Run relevant tests and `python tools/harness.py backend`, then `python tools/harness.py verify` from repo root (PowerShell: `py -3.12 tools/harness.py ...`). Mark skipped/unavailable gates **NOT VERIFIED**, never PASS.
8. Review `docs/09_AI_Coding_Rules.md` sections 4 and 16 before a PR. Report files, tests, ACs met, assumptions, migration impact, and blockers. Create a focused branch/PR when requested; never auto-merge.

## Coordination and stop conditions

- Contract changes require team approval and synchronized spec, migration, tests and `docs/CHANGELOG.md`.
- If an API needed by Dev 3 changes, coordinate OpenAPI/Pydantic contracts before implementation.
- Escalate ambiguities involving approvals, delivery-date negotiation, GPS, SKU mapping or revenue; do not invent requirements.
- Never write secrets, customer PII or passwords into source, seed, logs or PR descriptions.
