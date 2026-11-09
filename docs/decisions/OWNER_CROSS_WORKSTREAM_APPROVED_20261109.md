# Owner approval — 27 cross-workstream decisions (2026-11-09)

**Status: OWNER APPROVED.** The owner expressly approved all of S1–S5, T18-1–T18-3, D7-1–D7-4, G1–G5, N1–N5, M6-1, API-1–API-2 and KPI-1–KPI-2 in the ITConsultant conversation on **2026-11-09**. This record supersedes contradictory *proposed* details in PRs #133, #138, #140, #141 and #142. Existing earlier approvals continue to apply unless expressly superseded below.

**Scope:** Approval establishes product and implementation requirements; it is not evidence that schema, migration, endpoint, testing, privacy/legal review or real-worker launch is complete. Work must be delivered in reviewed technical PRs. No automatic merge of PR code. Legacy POS/WMS is not to be written to without a separate approved integration contract.

## Stock scope and evidence — S1–S5 (#121)

- **S1:** Only an **Admin with an explicit, active, revocable market-specific grant** can manage/approve CFO SKU scope or independence evidence. An unqualified admin role or market affiliation is insufficient. Pilot scope is market SE.
- **S2:** The **scope author differs from its approver**. Warehouse Manager submits warehouse/WMS independence evidence, while a separately authorized Admin approves it; submitter and approver cannot coincide. Record identity, time, reason and before/after audit in the same DB transaction.
- **S3:** Scope is **market-wide in this pilot** (SE, no separate pilot entity), versioned and effective strictly **after approval**. Choose the immutable version effective at the trusted Source batch's `as_of` rather than sync time; persist stock-run binding to scope/evidence versions. No retroactive approval.
- **S4:** Expected **warehouse × in-scope SKU** coverage is explicit. If a required warehouse/SKU row is absent from a complete Source batch, treat it as **unknown and reject the entire CFO stock write**, never as zero. Only an explicit zero from Source means zero. Out-of-scope rows are ignored; failed/partial writes cannot be advertised as fresh stock. Preserve existing Source `503 STOCK_UNAVAILABLE` rules.
- **S5:** Independent-stock evidence validity is **at most 30 days in the pilot**, and renewing requires a new reviewed/approved version. Mapping/global product, unit/conversion, or scope changes automatically invalidate the affected evidence; other WMS anomalies trigger review, not guessed independence. Unapproved/expired/overlapping evidence rejects the relevant complete stock write and never permits an inferred physical stock pool.

## Warehouse transfer — T18-1–T18-3 (#127)

- **T18-1:** Prevent inbound double-counting using **verifiable destination WMS evidence showing that the particular transferred stock is represented**. Timestamp `snapshot.as_of` alone does **not** prove inclusion. Without proof, **do not add pending inbound to available stock**. Warehouse Manager's explicit receipt remains the authoritative operational close; no automatic receipt based on timestamp. Dev 1/2 must agree transfer–batch–warehouse–SKU provenance.
- **T18-2:** A **market-configured and approved** lead-time default can be used when no authoritative warehouse-pair lead exists, only with stored provenance. Absent valid pair-specific proof and approved fallback ⇒ fail closed.
- **T18-3:** Block cancellation/reversal at and after `source_confirmed` until a separately approved reversal workflow exists; maintain `409 ILLEGAL_TRANSITION` and no side effects.

## Driver proof and safety — D7-1–D7-4 (#140, #129, #134)

- **D7-1:** Actual driver eligibility requires verifiable HR/tachograph-type evidence, attested by a **named qualified transport/compliance reviewer**, with source and version/hash. Synthetic fixtures are **demo/test only**, not legally verified driver eligibility.
- **D7-2:** Prove **each market-local date across a rolling 56-day interval**. Explicit verified off-duty days differ from absent/unknown coverage. Re-evaluate source validity, revocation and rolling completeness during planning, five-gate approval and dispatch. Store versioned daily coverage, duty/driving/rest evidence and provenance.
- **D7-3:** Default **11 uninterrupted hours of daily rest**, no automatic nine-hour exception. Duty, driving, breaks/rest, and official future driver shifts are separate inputs; official Warehouse Manager schedules control warehouse/driver work capacity and historical records do not create shifts.
- **D7-4:** Missing/unknown driver licence/expiry, vehicle `max_permissible_mass_kg`, Regulation 561 applicability, or vehicle/trailer/transport context ⇒ reject automatic approvable planning and dispatch. Qualified legal/transport assessment sets applicability; do not infer it from vehicle name or payload capacity.

## GPS permissions and privacy — G1–G5 (#137; prior proposal #138)

- **G1:** Admin or market-granted authorized **supervisor** assigns **one active primary Dispatcher per trip**. Version/expire/revoke assignment with auditable actor, time, reason and handover. No role-wide backfill.
- **G2:** Only that specifically assigned Dispatcher may read a trip's GPS while assignment is valid, trip remains on road, and driver is within official active duty. Revoke at earliest of explicit expiry/revocation, trip terminal or duty end. Check at request time; no market-wide GPS reads.
- **G3:** Store **individual driver notice-delivery and acknowledgment evidence bound to the approved notice version**. Tracking real employees additionally requires privacy/legal sign-off (notices/DPIA and legal basis). A market-level GPS_NOTICE alone is insufficient; acknowledgment alone does not establish GDPR compliance.
- **G4:** Device cadence **30 minutes**; **maximum 100 positions per upload batch** with valid trip/duty/offline window; reject oversized/invalid batch atomically. Delete raw server GPS at trip or duty end, whichever first, including terminal transaction hook, cleanup backstop and device/offline queue deletion. **No raw 30-day GPS retention.**
- **G5:** Simulator must use a separate authenticated producer and explicitly synthetic provenance; never trust a driver-supplied `source=simulator`.

## Notification handoff — N1–N5 (#142, #129, #131)

- **N1:** Authorized Dispatcher reviews and approves the **DELAY** customer-facing ETA window; if promised delivery **date changes**, require verified customer-agreed date negotiation. DELAY remains a draft until explicit review/send.
- **N2:** Persist explicit approved `start`, `end`, version, approver and effective time. A forecast ETA **instant** is not a window; never infer start/end from it.
- **N3:** Pin immutable **template version and typed allowlisted variable snapshot** in queued notification; forbid free-text SMS/email and driver/GPS/CS-note/sensitive information leakage.
- **N4:** Event, risk and queued notification/**outbox row** belong in the **same caller-owned database transaction**; failure of required enqueue persistence rolls back the operation. Send externally only **after commit** via transactional outbox; maintain idempotency and dedupe, no exactly-once provider claim.
- **N5:** Retain currently approved retry cap/timing; do not invent new backoff. Send only to **Mailpit/test recipients** until separate real-customer authorization.

## M6, API and KPI — M6-1, API-1–2, KPI-1–2

- **M6-1:** Successful POD is unique **per `trip_stop`**, **not per order**. One multi-vehicle order may have multiple delivered PODs across different stops. A reviewed forward DB migration must drop/replace the old `order_id` successful-POD unique index and test multi-vehicle completion.
- **API-1:** The five feasibility checks use `checks.<gate>.passed` (boolean), **not `pass`**; missing/unknown is never success.
- **API-2:** `rejected_candidates` uses backend's **flat** `warehouse_id`, `vehicle_code`, `failed_check`, `code`, `detail`; do not invent nested DTOs or unauthorized names. Frontend #136 was already merged, so fix via a **new PR**.
- **KPI-1:** Keep **10 published KPI keys**: `planning_time_min`, `on_time_rate`, `labour_hours_per_delivery`, `km_per_delivery`, `prep_error_min`, `eta_error_min`, `plan_acceptance_rate`, `failed_delivery_rate`, `capacity_utilisation`, `manual_plan_count`. Correct text saying eight. The two currently unsupported diagnostics `hard_constraint_violations` and `event_to_alert_latency_s_median` must be `null`, not invented zeros or guesses.
- **KPI-2:** Use **approval date** for planning cohorts, **delivery/completion date** for delivery cohorts and **warehouse work_date** for capacity, in each market's IANA timezone. Any other ambiguous metric cohort needs reviewed definition rather than guessing.

## Further clarification — WMS-only physical stock ledger (2026-11-09)

[DEC-WMS-READONLY-20261109](DEC_WMS_READ_ONLY_STOCK_AUTHORITY_20261109.md) supersedes the **separate CFO WMS movement-reconciliation workflow** contemplated below: **WMS itself performs physical issue/receipt/transfer and reconciles inventory; CFO only GETs complete, fresh WMS stock snapshots**, tracks its own held/committed plan reservations and never creates duplicate physical stock adjustments or approval queues for WMS proofs. No 24-hour CFO reconciliation alarm is required. T18-1 no-double-count, stock freshness and scope remain important. The previously documented proposed WMS proof/reviewer approach is retained as historical context only and **not a task to implement**; PR #127 needs product/contract review for its confirm/receive behavior.

## Additional owner approvals — stock grant bootstrap and WMS transfer reconciliation (2026-11-09)

The earlier S1/S2 and T18-1 rules are supplemented by [DEC-STOCK-GRANT-BOOTSTRAP-20261109 and DEC-T18-WMS-RECON-20261109](DEC_STOCK_BOOTSTRAP_AND_WMS_RECON_20261109.md). An **owner-authorized System Admin** may issue the first explicit, market-specific Stock Admin grant with audit; **no self-grant**, no implicit superuser stock permissions. The owner allows assuming that warehouse managers record transfer outbound/inbound in the legacy WMS, **but not assuming WMS API exposes movement IDs or transfer-linked snapshot acknowledgments**. Reconcile using verified WMS movement/receipt evidence for source and destination; otherwise Warehouse Manager submits proof and an independent appropriately market-authorized reviewer approves/audits it. Never infer reconciliation from timestamps/quantity changes, never double-subtract outgoing or double-add incoming. The suggested 24-hour escalation has **not** been approved.

## Amendment to G4 — approved later on 2026-11-09

**The original G4 immediate raw GPS deletion instruction above is superseded in retention timing ONLY** by [DEC-GPS-RET-20261109](DEC_GPS_7D_AND_D8_REVIEW_TIMES_20261109.md): stop collection/live read at trip/shift end immediately, retain already lawfully captured history for at most **seven days** with approved investigation scope/audit and legal/privacy controls, then erase. The 30-minute device cadence, 100-point cap, absence of out-of-duty collection, individual notices and legal sign-off remain unchanged. The owner separately approved operational reviews at **07:00 and 13:00 Europe/Stockholm**, not all D8 jobs.

## Handoff and safeguards

**Dev 1:** stock-grant/version/evidence schema and APIs with Dev 2; T18 reconciliation, D7 eligibility loader and T16 recheck, M6 per-trip-stop POD migration and event/RiskService integration; backend DTO/contract harmonization and M8 KPI contracts.

**Dev 2:** Source/WMS stock scope/evidence binding, fresh SourceOrder/SourceRisk transaction handoff, D7 importer/verification source, GPS assignment/notice/device cleanup and transactional D4 outbox.

**Dev 3:** independent hotfix PR for merged #136, using the actual backend `passed` and flat rejected candidate fields and correct plan approval guards.

**Required acceptance:** Reviewed migration/API updates where needed, actor + market RBAC, valid/invalid history/stock paths, concurrency, rollback, cross-market privacy, actual PostgreSQL E2E and exact-head CI. Keep fail-closed behavior until fully validated; **do not auto-merge PR code**. This record does not substitute for legal, DPIA or compliance sign-off.

## Latest exception to WMS read-only contract (2026-11-09)

[DEC-WMS-RESERVE-SYNC-20261109](DEC_WMS_RESERVE_SYNC_20261109.md) selects the **narrow reserve-on-authorized-approval business workflow**: CFO checks fresh WMS available, submits a request using confirmed reverse-mapped original WMS SKU, WMS atomically reserves and reduces available, CFO immediately refreshes stock, and no WMS-reflected reservation can be subtracted twice. WMS alone controls physical on_hand. This exception does not authorize CFO WMS transfer reconciliation or on_hand writes, and is not evidence a real WMS API/credential/production write is ready. Review Dev 1/2 contract/implementation before activation.
