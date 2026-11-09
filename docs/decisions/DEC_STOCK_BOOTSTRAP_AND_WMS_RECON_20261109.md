# Owner decision — initial Stock Admin grant and WMS transfer reconciliation (2026-11-09)

**Status: OWNER APPROVED, with a clearly identified WMS operational assumption.** After the owner's approval of S1–S5 and T18-1–3, the owner confirmed that we may **assume the existing WMS records warehouse-to-warehouse outbound and inbound movements**, and agreed to the proposed Stock Admin bootstrap and WMS-evidence-first reconciliation rules. This decision supplements, rather than replaces, `DEC-OWNER-20261109`.

## DEC-STOCK-GRANT-BOOTSTRAP-20261109 — First market-specific Stock Admin grant

1. The Owner designates/authorizes a trusted **System Admin** to bootstrap the **first Stock Admin grant for a specific market** (SE in the pilot). A normal Admin role, a market affiliation, or absence of any grant does not itself confer stock approval authority.
2. The bootstrap grant must identify market, grantor, grantee, permission scope, activation/revocation time, reason, and an append-only auditable before/after record. No automatic/implicit bootstrap on login, install or migration; no seeding universal Stock Admin permissions.
3. **No self-grant:** the System Admin issuing the grant cannot be its recipient. Continue to enforce S2: scope author ≠ scope approver; WMS evidence submitter (Warehouse Manager) ≠ authorized evidence approver.
4. The first grant is an explicit owner-authorized, controlled administrative operation. Subsequent delegation/revocation must likewise use reviewed server-side authorization and auditing; do **not** infer the right to mint arbitrary grants from mere System Admin or Stock Admin status. The exact authorized operator identity and technical bootstrap procedure/DDL/API must be reviewed before execution.

**Not implemented by this record:** user designation, production grant, DB migration, Admin endpoint, execution runbook or E2E RBAC tests. Related PR: #148.

## ASM-WMS-MOVEMENT-20261109 — Operational assumption: existing WMS records outgoing and incoming transfer entries

The owner expressly permits assuming that Warehouse Managers **do record the warehouse A outbound and warehouse B inbound movements in the existing WMS** for an inter-warehouse transfer. CFO continues read-only toward legacy POS/WMS/ERP and **must not modify WMS**. This assumption does **not** prove a WMS API exists, that it exposes a unique movement ID, an acknowledgment version, or a transfer-to-snapshot reference. Dev 2 must verify the actual read API/CSV export, record format, coverage, permissions, currency/freshness and reconciliation evidence with real Source/WMS contracts. If unsupported, fail closed and use a reviewed manual-evidence workflow, not invented data.

## DEC-T18-WMS-RECON-20261109 — WMS-evidence-first reconciliation (SUPERSEDED BY OWNER CLARIFICATION)

**Superseded in product scope:** Owner subsequently clarified that CFO **only reads stock from the legacy WMS** and must not independently reconcile physical inter-warehouse movements or run a CFO reconciliation approval queue. See [DEC-WMS-READONLY-20261109](DEC_WMS_READ_ONLY_STOCK_AUTHORITY_20261109.md). The below text is retained as historical proposal context **not a current implementation requirement**. It does not authorize a movement-proof workflow or 24-hour follow-up. Stock freshness/coverage and no-double-count remain required.


1. Prefer **authoritative WMS movement/receipt evidence** for **both source outbound and destination inbound** linked to the CFO transfer and its warehouse, SKU/global-product mapping, quantity, movement direction/status and source batch/version/timestamp. Match each transfer line and store immutable references/provenance, reviewer, decision time and outcome; evidence must be sufficiently specific to determine whether a movement is reflected in each stock snapshot. An arbitrary latest `as_of`, unchanged/changed quantities or a numeric coincidence is **not** proof.
2. **Outbound side:** avoid subtracting an already-reflected WMS source movement again. Preserve the unresolved transfer adjustment when WMS incorporation cannot be proven; do not release/de-duplicate adjustments solely from a newer timestamp or a quantity delta. If evidence cannot establish availability, fail closed for the affected stock decision.
3. **Inbound side:** a CFO transfer `inbound_shipment` is not automatically extra on-hand stock. Only treat stock as available when receipt and trusted WMS stock inclusion are verified under existing T18-1 and stock freshness/coverage rules; never add it twice if it is already in the WMS snapshot.
4. **Fallback where WMS movement linkage is not exposed:** a Warehouse Manager provides documented outbound/receipt proof from the existing WMS and an **independent, specifically authorized, market-scoped reviewer** approves the reconciliation evidence with audit. A Warehouse Manager's operational confirmation alone closes the relevant operational stage but is not an invented automated WMS acknowledgment or proof of snapshot inclusion. Missing proof/approver ⇒ no inferred reconciliation, no double count, and an explicit pending/unverified state.
5. Replays must be idempotent, concurrent or conflicting evidence must fail closed, and no partial/bad batch becomes a complete CFO stock snapshot. CFO remains GET/read-only to the legacy systems.
6. **Still separate/unapproved:** the owner has not yet approved a **24-hour (or other) unresolved-reconciliation escalation SLA**, auto-reversal after `source_confirmed`, or a WMS movement API schema/field name. These require further owner/technical review. The documented T18-2 approved market fallback for warehouse-pair lead time and T18-3 reversal block remain unchanged.

### Required handoffs

- **Dev 1 (#148/#127):** review bootstrap grant runbook and server-side RBAC, ensure no self-grants; define transfer adjustment persistence, inclusion acknowledgments and audit/migration with concurrency/rollback tests.
- **Dev 2 (#121/#127):** verify existing Source/WMS outbound and inbound records and exposure over GET/CSV; design evidence mapping for each movement and stock snapshot version, including missing/partial/duplicate cases; coordinate with Dev 1.
- **Acceptance tests:** source snapshot before/after outbound, movement acknowledged vs absent, unchanged quantity despite other activity, destination received before snapshot vs included after snapshot, stale/partial/503 WMS batches, replay/conflicts, concurrent transfers for same SKU, and never count inbound twice.

**Not a production integration acceptance:** This is a policy approval and explicit WMS operational assumption, not evidence that the current Source/WMS adapter or #127/#148 code implements it. No code PRs auto-merged.
