# CFO MVP — Instructions for AI Coding Agents

> Applies to the repository root and all subdirectories. This is a **routing and execution guide**, not a replacement for the versioned specifications in `docs/`.

## Mission and current state

CFO is a real, synthetic-data MVP for delivery orchestration over existing POS/WMS/ERP systems. It proposes fulfilment plans; **only the dispatcher decides**. Core stack: FastAPI / Python 3.12, PostgreSQL 16 / SQLAlchemy / Alembic, React 18 / Vite / TypeScript, and a separate simulated source system.

The repository contains scaffolding; **do not treat declared endpoints, stub screens, or TODOs as completed features**. Verify behavior by running checks. Implement in dependency order M0 → M9 (`docs/08_Development_Plan.md`), using `docs/10_Team_Assignment.md` for ownership.

## Mandatory reading and source of truth

Before **any code change**, read `docs/09_AI_Coding_Rules.md` in full, especially §4 (all **25** invariants), §13 (prohibited changes), §14 (ambiguity), and §16 (definition of done). Before each PR, recheck §4 and §16.

When documents disagree, apply the precedence specified by `docs/09_AI_Coding_Rules.md` §2:

1. `docs/09_AI_Coding_Rules.md` — invariants and agent workflow
2. `docs/05_Database_Design.md` — exact DDL, enums, constraints
3. `docs/06_API_Specification.md` — endpoints, schemas, permissions, error codes, Appendix A
4. `docs/04_Tech_Stack_and_Architecture.md` — layers, engine algorithm, config, security
5. `docs/01_PRD.md` — FR / BR and MVP scope
6. `docs/02_User_Stories_and_Acceptance_Criteria.md` — US and testable AC
7. `docs/07_User_Flows.md` — transitions and user journeys
8. `docs/03_UI_UX_Specification.md` — UI, especially §7 corrections to design images
9. `docs/08_Development_Plan.md` — milestone order, seed, tests

`docs/10_Team_Assignment.md` assigns file ownership and review responsibilities. Do not interpret its schedule as overriding the specifications. If a required file is missing, **stop work that depends on it and report the missing contract**; do not invent it.

**Known documentation inconsistency to flag, not silently fix:** `09` §4 invariant 10 and v1.2 explicitly require **multiple vehicles for one order**, whereas a stale bullet in `09` §13 describes that algorithm as outside MVP. Before implementing affected behavior, request that the team reconciles this bullet; do not bring back the removed `MANUAL_PLANNING` or `HANDLED_EXTERNALLY` statuses.

## Load only the context needed for the task

- **All tasks:** `09`; relevant milestone/owner (`08`, `10`); targeted US/AC (`02`) and BR (`01`). State the exact `US-…`, `AC…`, `BR-…` IDs.
- **DB and migrations:** `05`; `06` for affected payloads; `04` for transaction architecture.
- **API and permissions:** `06` (including role/location matrix), `05`, relevant flows (`07`).
- **Engine, planning, allocation:** `04` §6–8, `05`, `06`, `02`; pure-function restrictions in `09` §4.
- **External integrations and jobs:** `04`, `06` §16 for source-system contract, `05`, `07`.
- **Frontend/PWA:** `03` (especially §7), `07`, `06`, affected US/AC from `02`.
- **Infrastructure, CI, seeds:** `08` M0 and §6–8, `04`, `09`, `10`.

Read targeted sections, not all ten specifications every turn; `09` is the explicit full-read exception.

## Non-negotiable safety and product rules (summary; `09` controls)

- **No automatic approval**, date changes without agreed negotiation, or automatic sending of DELAY notices.
- **GPS access is enforced server-side for dispatcher only**. Never expose GPS or customer PII in logs or unauthorized responses.
- **CFO reads source systems; never write back** to POS/WMS/ERP.
- **Engine is pure**: no DB, network, clock, filesystem, environment, or I/O. Use injected inputs and clock.
- **One warehouse per order; no combining orders in one trip; one order may require multiple vehicles.**
- **Planning holds may overlap; only approval acquires prescribed locks and rejects overcommit**. Close superseded plans in the same transaction.
- **All order state changes go through `transition()`** and relevant decisions are appended to `audit.decision_log` in the same transaction.
- Do not change exact tables, fields, enums, routes, error/action codes, permissions, or business formulas without an approved contract change.
- **No hard-coded secrets or real customer data**. Never expose environment values in PRs or agent summaries. Do not commit `.env` or print tokens/passwords.
- Do not add microservices, paid services, Redis/Celery, WebSockets or an AI decision engine to this MVP.

## Mandatory task loop

1. **Inspect**: examine relevant source files and status; identify scope, owner, US/AC/BR, and dependencies.
2. **Plan**: show a 5–10-line implementation plan, touched files, tests, risks; split changes > ~400 lines of logic. For an audit-only request, **do not edit code**.
3. **Test**: add tests first or alongside code; use `test_US_<EPIC>_<NN>_AC<k>_...` names for ACs. Test both allowed and forbidden permissions. DB constraints require real PostgreSQL integration tests.
4. **Implement**: smallest change that satisfies the AC. Respect current architecture and file ownership. Do not disguise TODOs or `NotImplementedError` as implemented features.
5. **Verify**: run affected tests and the harness gates below. A command that did not run is **NOT VERIFIED**, not PASS. Never disable tests/checks just to get green CI.
6. **Report**: US/AC/BR covered; files changed; commands and results; risks, assumptions, and remaining work. Before reporting done, use `09` §16 checklist.

## Harness commands (run from repository root)

After adding `tools/harness.py` and installing the project's dependencies:

```bash
python tools/harness.py doctor      # docs / environment / tooling status (read-only)
python tools/harness.py backend     # Ruff, Black, mypy, import-linter, pytest
python tools/harness.py frontend    # npm lint, npm test, npm build
python tools/harness.py verify      # both suites; returns nonzero if any gate fails
python tools/harness.py smoke       # running local stack: CFO and source health endpoints
```

On Windows PowerShell replace `python` with `py -3.12` if needed. The harness **does not install dependencies, start containers, change the database, or print secrets automatically**. See `docs/HARNESS_SETUP.md`.

The existing `Makefile` / `.github/workflows/ci.yml` are owned by Dev 2. Keep them working; propose changes as reviewed diffs, not blind replacement.

## Scope, uncertainty and team handoff

- Work on the assigned milestone and workstream only. Never change another workstream's API/DB contract behind its owner's back.
- If a business rule is undefined: follow `09` §14. Small safe assumptions require `docs/ASSUMPTIONS.md` with an `ASM-xxx` and PR note. Contract changes or sensitive decisions require team approval before implementation.
- If `05` or `06` changes with approval, include the spec update, migration/code changes, tests and `docs/CHANGELOG.md` together.
- Branch `feat/<epic>-<description>`, `fix/...`, or `chore/...`, conventional commits, reviewed PR. Owners/reviewers: `10`.
- No claim of "feature complete" based solely on imports, scaffolds, 200 responses from `/openapi.json`, or green unit tests; verify the story's actual acceptance criteria.
