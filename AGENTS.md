# CFO MVP — Instructions for AI Coding Agents

> Applies to the repository root and all subdirectories. This is a **routing and execution guide**, not a replacement for the versioned specifications in `docs/`.

## Mission and current state

**Product decision (2026-11-07):** Sales may confirm eligible standard plans in CFO; POS remains unchanged. Read `docs/DECISION_SALES_CONFIRMATION.md` before related work.

**Round 3 decisions (2026-11-18, DEC-R3-11…14 cancelled 2026-11-19):** [DEC-R3-01…10, 15](docs/decisions/DEC_R3_SCOPE_CRM_20261118.md) supersede conflicting older rules: continuous GPS/offline PWA/SMS/contact log, transfers and the Transfers/Users/Vehicles/Employees/Market config screens deferred; an Orders & revenue report (5 status groups by committed delivery date; cancelled by cancellation date; pending orders excluded) is kept; driver-initiated location updates (mandatory at DELIVERED/FAILED), no map — the rotation-assigned Dispatcher sees one "last position · updated at · ETA" line; coordinates deleted when the order closes; day-level warehouse capacity; fleet-verified driver availability; no auto-replan after FAILED/vehicle issue; **Sales has Dispatcher-equivalent pre-approval authority for own-store orders** (rank 1–3 any warehouse, rerun, date agreement). Read it before any related task.

CFO is a real, synthetic-data MVP for delivery orchestration over existing POS/WMS/ERP systems. It proposes fulfilment plans; **dispatcher decides exceptions/full plans; Sales may approve rank 1–3 for their own store's orders within DEC-R3-10 scope**. Core stack: FastAPI / Python 3.12, PostgreSQL 16 / SQLAlchemy / Alembic, React 18 / Vite / TypeScript, and a separate simulated source system.

The repository contains scaffolding; **do not treat declared endpoints, stub screens, or TODOs as completed features**. Verify behavior by running checks. Implement in dependency order M0 → M9 (`docs/08_Development_Plan.md`), using `docs/10_Team_Assignment.md` for ownership.

## Mandatory reading and source of truth

**Approved assumption/decision register:** Before starting or reviewing a task, consult `docs/ASSUMPTIONS.md` for applicable ASM/DEC decisions. Every newly owner-approved decision must be recorded there within the same PR as related spec changes, with unique ID, date, approver, precise rule, source PR/comment, affected files and implementation status. Do not treat dev proposals or CI success as owner approval; logging a decision does not mean implementation exists.


Before **any code change**, read `docs/09_AI_Coding_Rules.md` in full, especially §4 (all **27** invariants), §13 (prohibited changes), §14 (ambiguity), and §16 (definition of done). Before each PR, recheck §4 and §16.

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

**Owner-approved amendments (2026-11-09):** `docs/ASSUMPTIONS.md`, [DEC-CS/M6/STOCK/D8](docs/decisions/DEC_CS_M6_STOCK_D8_OWNER_APPROVED_20261109.md), [DEC-WMS-RESERVE-SYNC](docs/decisions/DEC_WMS_RESERVE_SYNC_20261109.md) and [DEC-INTEGRATION Q2–Q10](docs/decisions/DEC_INTEGRATION_UNBLOCK_Q2_Q10_20261109.md) supersede older, conflicting prose. Multi-vehicle plans remain in MVP; the obsolete warning about `09` §13 has been reconciled. Approved policy is **not** proof of implementation, WMS write permission, GPS legal clearance or passing end-to-end tests.

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

- **No automatic approval**. Sales may explicitly approve rank 1–3 (reason for 2–3), rerun planning and record a customer-agreed date for own-store orders via the same approval transaction (DEC-R3-10); approval needs only feasible/not feasible (no tight-schedule tick for anyone); dispatcher retains manual plans/overrides, post-execution exceptions/replan, DELAY sending and other stores. No unagreed dates or automatic DELAY notices.
- **Location in the Round 3 pilot (DEC-R3-01)** is driver-initiated only (tap to update, on incident, mandatory at DELIVERED/FAILED); no periodic collection. It is **role- and trip-scoped on the server**: only the Dispatcher assigned to the trip (rotation at approval, audited handover) may read positions while the trip is on_road. After the trip ends, access stops immediately; coordinates are deleted when the order is DELIVERED/CANCELLED (FAILED orders: at most 7 days); no historical access. No customer/CS/Sales GPS access, PII logs or real-worker GPS before sign-off.
- **CFO reads POS/ERP and authoritative WMS stock, never changes physical WMS on_hand or transfer/receipt records.** Owner approved the *business intent* for a narrowly scoped CFO→WMS **reservation/release request at authorized plan confirmation**, requiring verified original WMS SKU/unit, precise ACK, idempotency and immediate stock re-read. **Real WMS outbound writes remain disabled pending separately reviewed API, permissions and rollout**; synthetic reserve/status/release is staging-only and labelled simulated. Sales sync-now reads POS via CFO; 5-minute polling is fallback. No POS/ERP write-back.
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
6. **Report**: US/AC/BR covered; files changed; commands and results; risks, assumptions, and remaining work. Include `Assumptions: reviewed; new/changed decision IDs or none` in PR summaries. Before reporting done, use `09` §16 checklist.

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
- If a business rule is undefined: follow `09` §14. Dev proposals are marked `proposed` in `docs/ASSUMPTIONS.md` under a unique `ASM-xxx` after checking for collisions. Once owner approves, immediately mark approved or add a `DEC-xxx` product decision with source and impact. Contract changes or sensitive decisions require team approval before implementation. Preserve superseded historical decisions.
- If `05` or `06` changes with approval, include the spec update, migration/code changes, tests and `docs/CHANGELOG.md` together.
- Branch `feat/<epic>-<description>`, `fix/...`, or `chore/...`, conventional commits, reviewed PR. Owners/reviewers: `10`.
- No claim of "feature complete" based solely on imports, scaffolds, 200 responses from `/openapi.json`, or green unit tests; verify the story's actual acceptance criteria.
