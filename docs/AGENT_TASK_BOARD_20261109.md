# Agent task board — 2026-11-09 after merges

> Originally based on `main` at [`89a8f3d`](https://github.com/qaztyhn/cfo-itconsultant/commit/89a8f3d33453d4e02df812068ec6944eae2d8499); PR state reverified 2026-11-09. **Coordination only:** not new business approvals, not proof of E2E or production readiness. Check fresh GitHub PR state and `AGENTS.md`, `docs/09_AI_Coding_Rules.md`, `docs/ASSUMPTIONS.md` before code or merge.

## Merged baseline

| PR | Change |
|---|---|
| [#158](https://github.com/qaztyhn/cfo-itconsultant/pull/158) | IT Product Mapping UI (Agent 8): merged; no need to reimplement |
| [#162](https://github.com/qaztyhn/cfo-itconsultant/pull/162) | WMS reserve readiness validator and review only; not a live WMS reserve |
| [#167](https://github.com/qaztyhn/cfo-itconsultant/pull/167) | Owner-approved CS search/privacy, M6 Prep Queue, Stock Admin grant and D8 staging decisions |
| [#168](https://github.com/qaztyhn/cfo-itconsultant/pull/168) | CS lookup implementation handoff |
| [#152](https://github.com/qaztyhn/cfo-itconsultant/pull/152) | Integration monitoring read API (Agent 15): merged |
| [#144](https://github.com/qaztyhn/cfo-itconsultant/pull/144) | Read-only Integration Dashboard UI: merged; no duplicate implementation |
| [#149](https://github.com/qaztyhn/cfo-itconsultant/pull/149) | My Store Orders read-only UI: merged; server isolation E2E remains separate |
| [#156](https://github.com/qaztyhn/cfo-itconsultant/pull/156) | Revenue Dashboard: merged; no unapproved revenue formula |
| [#163](https://github.com/qaztyhn/cfo-itconsultant/pull/163) | Disabled WMS reservation adapter: merged as foundation, not a live write path |
| [#147](https://github.com/qaztyhn/cfo-itconsultant/pull/147) | Read-only Dispatcher Exceptions triage: merged; backend diagnostics still partial, no E2E completion claim |

## Open PRs: reserved file scopes; do not duplicate

- Core/WMS: [#129 Execution](https://github.com/qaztyhn/cfo-itconsultant/pull/129); [#137 GPS](https://github.com/qaztyhn/cfo-itconsultant/pull/137); [#127 Transfers](https://github.com/qaztyhn/cfo-itconsultant/pull/127); [#121 T07](https://github.com/qaztyhn/cfo-itconsultant/pull/121); [#148 scope/evidence](https://github.com/qaztyhn/cfo-itconsultant/pull/148); [#164 scope-gated stock writer](https://github.com/qaztyhn/cfo-itconsultant/pull/164). #164 is stacked on #148, which depends on #129; not an independently mergeable production writer.
- M6 UI: [#154 Prep read UI](https://github.com/qaztyhn/cfo-itconsultant/pull/154); [#159 Prep API](https://github.com/qaztyhn/cfo-itconsultant/pull/159); [#160 Prep contract UI](https://github.com/qaztyhn/cfo-itconsultant/pull/160).
- Frontend and KPI: [#143 KPI API](https://github.com/qaztyhn/cfo-itconsultant/pull/143), [#150 KPI UI](https://github.com/qaztyhn/cfo-itconsultant/pull/150), [#161 Handling Groups](https://github.com/qaztyhn/cfo-itconsultant/pull/161), [#165 No Feasible Date](https://github.com/qaztyhn/cfo-itconsultant/pull/165), [#166 seed](https://github.com/qaztyhn/cfo-itconsultant/pull/166), [#169 Sales UI](https://github.com/qaztyhn/cfo-itconsultant/pull/169), [#146 canonical Plan Review](https://github.com/qaztyhn/cfo-itconsultant/pull/146) (duplicate #151 closed unmerged), [#153 Manual Plan](https://github.com/qaztyhn/cfo-itconsultant/pull/153). These PRs are still open; an open PR is not approved, implemented or E2E-tested.

## Next independent assignments

| Priority | Agent/owner | Narrow scope | Completion/dependency |
|---|---|---|---|
| P0 | **Agent 26 / Dev 2** — Sales Sync & Check backend | New `sales_sync_service` and route, own PostgreSQL tests, only minimal reviewed API registration | Issue [#72](https://github.com/qaztyhn/cfo-itconsultant/issues/72). Polling never writes routing; authorized Sales/Dispatcher check on fresh Source; 100% confirmed SKU or legacy; immutable decision, one CFO order, idempotent concurrency, safe unresolved. Coordinate UI #169. Do not touch T07 ingestion. |
| P0 | **New CS backend agent / Dev 1** | `backend/app/services/order_read_service.py`, targeted `backend/app/api/v1/orders.py`, CS-only tests | Phone-normalized adequately specific `GET /orders?q=` under market scope with abuse/PII-log protection; CS server-side masked allowlisted DTO, no raw phone/email, coordinates, gate codes or internal planning/risk fields. Read [#167](https://github.com/qaztyhn/cfo-itconsultant/pull/167) and [#168](https://github.com/qaztyhn/cfo-itconsultant/pull/168). |
| P0 | **Agent 11 / Dev 3** — CS Order Lookup | `frontend/src/features/cs/OrderLookup.tsx` and feature-local files | Follow `docs/proposals/CS_ORDER_LOOKUP_ASSUMPTIONS_20261109.md`; mock-only contact log visibly **not saved** until backend; safe allowlisted timeline. No shared routes/global mocks. |
| P0 | **Agent 6 / Dev 3** — Driver PWA | `frontend/src/features/driver/TodaysTrips.tsx` and feature-local files | Driver-scoped trip list, per-stop POD, idempotent offline retry, explicit GPS consent; backend #129/#137 pending; no fake completed E2E. |
| P1 | **Agent 3 / Dev 2** — Notification service/API | `backend/app/services/notify_service.py`, `backend/app/api/v1/notifications.py`, own tests | N1–N5: DELAY draft authorized send, immutable template version+allowlisted vars, transactional outbox, Mailpit/test recipients only, no exactly-once claim. |
| P1 | **Agent 30 / Dev 2** — Market config backend | Only GET/PUT config stubs in `backend/app/api/v1/admin.py` plus separate service/tests | Preserve existing monitoring endpoints from #152, admin scope, audit and secret-free DTO; do not activate production scheduler. |
| P1 | **Agent 31 / Dev 3** — Source POS demo | `source_system/pos_ui/` only | Approved Source D1 Draft/Validate/Submit/Edit/Cancel. Known Source SKU may submit even when unmapped to CFO. Do not modify CFO Sales UI #169. |
| P1 | **Agent 29 / QA** — Playwright foundation | New `tests/e2e/` only | 18 documented scenarios, each PASS/FAIL/BLOCKED/NOT VERIFIED with real evidence; #166 seed remains partial/open. |
| P1 | **New D8 staging agent / Dev 2** | Isolated staged-job orchestration/tests, no edits to live stock/T07 scheduler in overlapping PRs | #167 approved job cadence for staging/demo only; 07:00/13:00 Europe/Stockholm operational reviews, DST safe. Technical tick/auth review required before activation. No production jobs, real recipients or spend. |

## Latest decision constraints

- [CS, M6, Stock Admin, D8 decisions](decisions/DEC_CS_M6_STOCK_D8_OWNER_APPROVED_20261109.md): server-side CS privacy/phone normalization; canonical Prep Queue `capacity.schedule_verified`; only Owner-delegated System Admin may grant/revoke Stock Admin; D8 approved in staging, not production.
- [WMS reserve intent](decisions/DEC_WMS_RESERVE_SYNC_20261109.md): only controlled reserve-on-confirmation exception to read-only WMS boundary; actual WMS API, ACK/transport, release, deployment not verified. #162 validator and merged #163 disabled port are **not** live integration; no double-count.
- [GPS 7-day retention](decisions/DEC_GPS_7D_AND_D8_REVIEW_TIMES_20261109.md): stop live collection/read immediately at trip/duty end; restricted authorized historical retention **up to 7 days**, then controlled deletion; #129/#137 must be reconciled, not parallel-edited.
- [WMS stock authority](decisions/DEC_WMS_READ_ONLY_STOCK_AUTHORITY_20261109.md): WMS owns physical on-hand and transfer movements, CFO does not invent physical reconciliation or WMS movement writes.
- Never treat docs approval, mocked frontend tests or open PRs as finished implementation.

## Agent prompt footer

> Start on freshly fetched `origin/main` in a separate worktree. Read full `AGENTS.md`, `docs/09_AI_Coding_Rules.md`, applicable `docs/ASSUMPTIONS.md` and owner-approved decisions. Inspect open PR file lists first. Respect assigned ownership, audit, RBAC, WMS/GPS/privacy guards. No fabricated API/DDL or automatic approval/deployment. Add focused tests (real PostgreSQL for DB/concurrency); run actual harness commands. Report PASS/FAIL/BLOCKED/NOT VERIFIED precisely and include assumptions reviewed. Make one focused PR, never auto-merge or force-push. This board makes **no new owner decision**.
