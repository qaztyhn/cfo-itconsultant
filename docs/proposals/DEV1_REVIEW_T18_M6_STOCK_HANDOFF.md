# Dev 1 review — T18 (#127), M6 (#129) and stock scope/evidence handoff (#121)

Status: **assessment and proposals only**. No code, schema, route or business-rule change. Items marked *needs decision* must not be implemented before the owner approves a contract.

## 1. PR #127 — T18 stock transfer (Draft; keep Draft)

Done on the branch: merged current `main` (only `docs/CHANGELOG.md` conflicted); transfer and OpenAPI tests pass (36) on real PostgreSQL.

| Concern | Finding | Action |
|---|---|---|
| Double counting after later WMS snapshots | `confirmed_inbound()` counts only `confirmed AND NOT received` inbound rows; `receive()` flips `received=true` in the same transaction as `TRANSFER_RECEIVED`. A WMS snapshot ingested **between** `source_confirmed` and `received` can already contain the goods while the inbound row is still counted. | *Needs decision* **PROP-T18-01**: reconciliation rule. Proposal: a transfer inbound row stops counting as soon as a published WMS snapshot of the destination, with `as_of >= source_confirmed_at + lead`, exists for that SKU scope; require Warehouse Manager receipt as the authoritative close; never auto-mark received. Needs Dev 2 (snapshot publication) agreement. |
| Lead-time provenance/fallback | Lead comes from the persisted suggestion (`transfer_lead_days_default`, route provenance stored in `suggestion`). Default must be int ≥ 1, otherwise `PLAN_NOT_APPROVABLE` (fail closed). | Documented. *Needs decision* **PROP-T18-02**: is the config default an approved fallback or must an official inter-warehouse lead table exist? Until decided the default stays explicit and recorded in `suggestion`. |
| Cancel/reversal after `source_confirmed` | `cancel()` allows only `suggested`/`approved`; later stages return `ILLEGAL_TRANSITION` (fail closed, nothing changes). No unsafe reversal is implemented. | *Needs decision* **PROP-T18-03**: reversal contract (who, reason, effect on inbound row, audit action). Not invented. |
| CFO OpenAPI | OpenAPI parity/baseline tests pass after merge. | none |
| Integration with #134 | Independent files; recheck gates read stock via `planning_inputs`. No conflict. Merge order: #127 first, then update #134 from `main`. | none |

Ready for review: **no** (three open decisions above).

## 2. PR #129 — M6 execution backend (Draft; partial, fail-closed)

Remaining blockers (none bypassed):

1. **M6 → M7 risk recalculation**: M6 calls `risk_service.recalculate` without the caller's session; #131 makes it session-aware and closes risk alerts on `DELIVERED`. #129 must adopt the `session=` form after #131 merges (same transaction, no separate commit).
2. **Notifications**: must be transaction-aware (enqueue in the caller's transaction). Dev 2 owns notification/ingestion — coordinate, do not edit their services.
3. **Official shifts**: warehouse shift availability and driver shifts need an official source; a nonempty duty log is **not** proof of a complete 56-day history (DEC-DEV2-D7-001: the history-complete marker is not persisted, so the real `safety` gate fails closed).
4. **Driver/vehicle legality**: licence class, rest, legal vehicle scope (`regulation_561_scope`, default `unknown` → fail closed) and permitted mass (`max_permissible_mass_kg` may be NULL → fail closed).
5. **POD uniqueness — contract contradiction** *(needs decision, **PROP-M6-01**)*: `docs/05` ~L584 says POD per `trip_stop`; ~L595 and migration 0005 define `ux_pod_one_delivered ON ops.proof_of_delivery(order_id) WHERE result='delivered'`, which forbids a second delivered POD for a multi-vehicle order; docs/09 invariant 22 and US-EXE-02 AC6 require one POD per trip stop. Proposal: replace the index by uniqueness on `(trip_stop_id) WHERE result='delivered'` via a reviewed migration + docs/05 update.
6. **Migration/API changes** required by 3–5 need an approved contract; none made.
7. **Full real-PostgreSQL E2E** (plan → approve → dispatch → deliver → risk) not run; M6 cannot be called complete.

Ready for review: **no**.

## 3. Feedback to Dev 2 on #121 (stock scope/evidence)

Aligned with approved DEC-CFO-STOCK-SCOPE-001 (B), DEC-CFO-STOCK-INDEPENDENCE-001 (A), D1-03/04.

- **Scope**: versioned per market/pilot, effective-dated (`valid_from`, `valid_to`), immutable once approved (new version instead of edit), bound to the sync batch by version id so the scope is fixed *before* sync, never derived from mapped SKUs.
- **Authorization / separation of duties**: author ≠ approver; approver is an admin with scope authority; every create/approve/retire is audited (`audit.decision_log`, actor, reason, before/after). Warehouse Manager supplies independence evidence but cannot approve scope.
- **Evidence lifecycle**: `submitted → approved | rejected → superseded/expired`; carries SKU set, warehouse, evidence reference, approver, version, validity; expired or unapproved ⇒ fail closed; no client-supplied evidence accepted by planning.
- **Coverage semantics**: expected warehouse × in-scope SKU matrix is part of the scope version. Missing row ⇒ batch rejected (not zero); explicit zero ⇒ zero; stale batch (older than the freshness limit) or unavailable source ⇒ `503 STOCK_UNAVAILABLE` (DEC-SRC-Q9-ERROR-001); never substitute the previous snapshot silently.
- **Handoff**: SourceOrder/SourceRisk handoff to Dev 1 adapters (`replan_source`) must run inside the caller's transaction and carry the source version; one replan suggestion per source version, no holds.
- Not editing #121; changes proposed here are for Dev 2 to adopt in their own PR.

## 4. Owner decisions required

| ID | Contract/assumption | Decision needed |
|---|---|---|
| PROP-T18-01 | T18 inbound vs WMS snapshot (docs/05, docs/06 transfers) | WMS reconciliation rule |
| PROP-T18-02 | `transfer_lead_days_default` | fallback vs official lead table |
| PROP-T18-03 | D1-01 (cancel) | reversal after `source_confirmed` |
| PROP-M6-01 | docs/05 L584 vs L595, docs/09 inv. 22, US-EXE-02 AC6 | POD uniqueness |
| PROP-DTO-01 | docs/06 §6.2 | `checks.pass` vs `checks.passed`; `rejected_candidates` shape |
| — | DEC-DEV2-D7-001 | official 56-day history source for the safety gate |
