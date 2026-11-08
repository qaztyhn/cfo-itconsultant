# D1-03 / D1-04 — versioned SKU scope and independent-stock evidence: technical contract proposal

**Status: PROPOSAL for Dev 1 + Dev 2 cross-team review. No migration, route, DTO or code is written from this file and
none may be until it is reviewed.** Author: Dev 1. Reviewer: Dev 2 (T07 stock writer, Source/WMS data), Dev 3 only if a
UI is later requested.

It adds **no business decision**. Everything that is not already owner-approved is listed in section 9 as an open
question, with an option and a recommendation, so that the owner can answer it instead of the developers guessing.

## 1. What is already decided (owner, 2026-11-08)

- **DEC-CFO-STOCK-SCOPE-001 (B):** only a SKU scope defined **before** the sync is normalized; out-of-scope SKUs never
  block; one unmapped/inconsistent **in-scope** SKU rejects the whole CFO stock write; the scope is never derived from
  mappings or from the batch.
- **DEC-CFO-STOCK-INDEPENDENCE-001 (A):** several SKUs of one warehouse mapping to one global product are summed only when
  independence is verified; otherwise the write is rejected (no partial snapshot, no max, no last-row-wins).
- **DEC-DEV1-D1-03:** an authorized administrator manages/approves the scope **per market/pilot**, with **version,
  effective time, actor/approver, before/after audit and history**; no retroactive effectivity to fix published data.
- **DEC-DEV1-D1-04:** the **Warehouse Manager** supplies the evidence from the warehouse/WMS; an authorized administrator
  approves it; store the evidence, approver, **version and validity**, with audit; missing/expired/overlapping ⇒ block.
- Not decided: tables, columns, routes, the exact meaning of "authorized", binding to `batch_id/as_of`, completeness,
  revocation, migration, tests (`docs/05` §6.1 and `docs/decisions/DEV1_D1_01_04_APPROVED_20261108.md`).

The consuming function already exists and is intentionally storage-agnostic:
`normalize_stock(snapshot, mappings, declared, *, scope, verified_independent)` (#111/#120). This proposal defines where
`scope` and `verified_independent` come from.

## 2. Invariants the design must keep

1. **Fail closed.** No effective scope version for the batch ⇒ the stock write is rejected (not "scope = everything").
2. **No retroactivity.** A version becomes effective only from a time **after** its approval; a batch is always processed
   under the version that was effective at the batch's `as_of`, and that binding is stored with the run.
3. **Append-only history.** Approved versions and evidence are immutable; changes create a new version; every state change
   writes `audit.decision_log` (before/after, actor) in the **same transaction**.
4. **Server-side authorization**, per market and (for evidence) per warehouse; client claims are never trusted.
5. **No PII / WMS secrets** in the audit payload or in API responses to roles that may not see them.
6. **CFO never writes back** to the Source/WMS; evidence is a CFO-side record that *refers* to WMS material.

## 3. Proposed data model (logical; names for review)

```text
ref.stock_scope_version
  id, market_id, version_no            -- UNIQUE (market_id, version_no)
  status        draft | approved | retired
  effective_from timestamptz           -- required when approved; must be > approved_at (no retroactivity)
  created_by, created_at, approved_by, approved_at, retired_at, note
ref.stock_scope_item
  scope_version_id, local_sku          -- PK (scope_version_id, local_sku); immutable once the version is approved
```
Effective version for a batch = the approved version of that market with the greatest `effective_from <= batch.as_of`
(**not** `now()`), so a replay of an old batch cannot pick up a newer scope.

```text
ref.stock_independence_evidence
  id, market_id, warehouse_id, global_product_id
  version_no                           -- per (warehouse_id, global_product_id)
  status        submitted | approved | rejected | revoked | expired
  valid_from, valid_to                 -- validity window; approved evidence must have both set
  submitted_by (warehouse manager), submitted_at
  approved_by, approved_at, decided_note
  revoked_by, revoked_at, revoke_reason
  provenance    jsonb                  -- WMS report id / extract reference / content hash; no raw WMS rows, no PII
ref.stock_independence_evidence_sku
  evidence_id, local_sku               -- the group; PK (evidence_id, local_sku)
```
- **Overlap guard:** at most one *approved and currently valid* group may contain a given
  `(warehouse_id, local_sku)`; a second one is refused at approval time (and checked again at use), because overlapping
  groups must never imply transitive independence (the rule already enforced in `normalize_stock`).
- `valid_to` is mandatory so that evidence cannot silently live forever; the default validity length is an owner
  question (section 9).

### Binding to a run
The T07 stock run must persist which scope version and which evidence versions it used, so that a later audit can
explain a snapshot. Proposal: a small `stg.stock_run_binding(run_id, scope_version_id, evidence_ids int[])` (or two
columns on `stg.sync_run`). **Either is a migration and needs Dev 1/Dev 2 sign-off.**

## 4. Authorization (the part that needs an owner answer)

"Authorized administrator" is not defined by the current RBAC (`admin` is an IT role; a system admin may have no
employee/market). Options:
- **A (recommended): explicit grants.** `hr.stock_policy_grant(employee_id, market_id, can_manage_scope,
  can_approve_evidence, valid_from, valid_to)`. Server checks: role `admin` **and** an active grant for that market.
  Mirrors how `hr.location_manager.can_approve` already works for warehouses, and is auditable/revocable.
- B: role `admin` + employee belongs to the market. Simpler, but any admin of that market is "authorized".
- C: role `admin` only. Not acceptable: contradicts "có thẩm quyền theo market/pilot".

The **Warehouse Manager** side reuses the existing effective-manager check (`hr.location_manager`, valid dates,
warehouse in the actor's `location_ids`); `can_approve` is not required to *submit* evidence, only to approve is an admin.

Separation of duties (the approver must differ from the creator/submitter) is a sensible control but is **not** an
approved rule: listed as an owner question.

## 5. Proposed API (admin-facing; all mutating calls take `Idempotency-Key`; standard error envelope)

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/markets/{code}/stock-scope` | admin (authorized), dispatcher read-only | Versions + the currently effective one |
| POST | `/markets/{code}/stock-scope/versions` | admin (authorized) | Create a draft `{local_skus:[…], note}` |
| POST | `/markets/{code}/stock-scope/versions/{id}/approve` | admin (authorized) | `{effective_from}`; audit before/after |
| POST | `/warehouses/{id}/stock-independence-evidence` | warehouse manager of `{id}` | Submit `{global_product_id, local_skus:[≥2], valid_from, valid_to, provenance}` |
| POST | `/stock-independence-evidence/{id}/approve` · `/reject` · `/revoke` | admin (authorized) | Decide / withdraw, reason required for reject/revoke |
| GET | `/warehouses/{id}/stock-independence-evidence` | warehouse manager, admin | History and current validity |

Errors reuse existing codes (`FORBIDDEN`, `NOT_FOUND` for cross-market, `VALIDATION_ERROR`, `ILLEGAL_TRANSITION`,
`IDEMPOTENCY_CONFLICT`, `REASON_REQUIRED`); **no new error code is proposed**. New audit action codes are an open
question (section 9). Routes are a proposal: CFO OpenAPI parity (`contracts/cfo.openapi.json`) does not exist yet, so the
baseline must be created and reviewed together with these routes.

## 6. How T07 consumes it (no code in this proposal)

For a batch: resolve the effective scope by `batch.as_of` → pass `scope`; resolve valid approved evidence groups for each
warehouse at `batch.as_of` → pass `verified_independent`; store the binding; run `normalize_stock`; replace the snapshot
in one transaction or reject everything. Missing scope or an expired/overlapping evidence group for an in-scope product
rejects the **whole** write.

Related findings from the cross-PR QA (not decided here, but this contract must not make them worse):
- A scope SKU that has **no row** in a complete batch is *unknown*, not zero; the persistence rule (reject / keep / mark
  unknown) needs an owner decision.
- A non-empty batch with no in-scope rows must not be treated as an authoritative empty snapshot.
- Planning/approval gates must also consult the latest stock-run availability, not only row timestamps.

## 7. Revocation / invalidation (technical proposal, rule content is an owner question)

Evidence is **suspended automatically** (status `revoked`, reason `auto`) when any member SKU's mapping changes
(global product, unit, `units_to_base`, confirmed→unconfirmed) or when the SKU leaves the scope; it is never re-enabled
automatically (a new submission + approval is required). Whether a *Source stock anomaly* should also suspend it
(e.g. identical quantities across the group) is not proposed because the owner said equal quantities prove nothing.

## 8. Test plan (PostgreSQL, before any PR is merged)

Scope: version create/approve/retire, `effective_from` not in the past, immutability after approval, authority per
market/pilot (other-market admin ⇒ 404/403), effective version by `batch.as_of` (replay of an old batch keeps its scope),
in-scope unmapped ⇒ whole-write rollback, out-of-scope ignored, no scope ⇒ rejected. Evidence: submit by the right/wrong
warehouse manager, approve/reject/revoke authority, missing/expired/overlapping ⇒ blocked, sum only after approval, auto
revocation on mapping/unit change, audit before/after written atomically (rollback when the audit insert fails),
idempotent replay/conflict, no PII in audit, binding stored per run. Plus an E2E using the real source and a real
evidence record in the synthetic data.

## 9. Open questions for the owner (nothing here is assumed)

1. **Who is an "authorized administrator"?** Option A (explicit grant table), B (admin of the market) or other.
2. **Separation of duties:** must the approver differ from the creator (scope) and from the submitter (evidence)?
3. **Effectivity rule:** minimum lead time between approval and `effective_from`; is "immediately after approval" allowed?
4. **Evidence validity:** default/maximum `valid_to` length, and who may extend it.
5. **Revocation triggers:** is automatic suspension on mapping/unit change acceptable, and are there other triggers?
6. **Audit codes:** reuse `CONFIG_CHANGED` or approve new action codes (e.g. `STOCK_SCOPE_APPROVED`,
   `STOCK_EVIDENCE_SUBMITTED/APPROVED/REVOKED`).
7. **"Pilot":** the schema has markets only; is a pilot simply a market (SE), or does it need its own entity?
8. **Per-warehouse scope:** is the SKU scope market-wide (proposed) or can it differ per warehouse?
9. **Missing row semantics** for an in-scope SKU/warehouse absent from a complete batch (unknown vs zero vs reject).

## 10. Sequencing and ownership

1. Dev 2 reviews sections 3, 5, 6 against the Source/WMS data they can actually provide (evidence provenance format).
2. Owner answers section 9. 3. Dev 1 writes the migration + services + API in small PRs; Dev 2 wires T07 afterwards.
No schema or route is created before steps 1-2. Until then `ingest_stock` stays gated and the T07 stock writer stays off.
