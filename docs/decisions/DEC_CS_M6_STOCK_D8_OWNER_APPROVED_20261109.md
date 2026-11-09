# Owner approvals — CS search/privacy, M6 Prep Queue, Stock Admin grants, D8 staging schedule (2026-11-09)

**Status: OWNER APPROVED for the five decisions below; documentation/contract update only.** Source: direct owner confirmation in the ITConsultant conversation on 2026-11-09: “CS-01: Mở rộng q để tìm số điện thoại, kiểm soát truy vấn ở backend; CS-02: CS chỉ xem thông tin khách đã che; backend loại bỏ các trường nhạy cảm; M6: Duyệt Prep Queue contract chuẩn trong PROPOSAL-M6-PREP-QUEUE-001; STOCK: Chỉ System Admin được Owner ủy quyền cấp/thu hồi Stock Admin grants; D8: Duyệt lịch job đề xuất để triển khai và kiểm thử staging, chưa bật production.” The owner expressly required documentation in `docs/ASSUMPTIONS.md`, a reviewable PR, **no code-PR auto-merge**, and left all unselected items unapproved.

These approvals authorize contract alignment and staged implementation work **only within the limits stated**. They do not assert that a route, migration, WMS integration, compliance clearance, CI result, production scheduler, real-user authorization or E2E already exists.

## DEC-CS-SEARCH-20261109 — Search by contact phone through existing q (CS-01)

- Preserve `GET /api/v1/orders?q=...`; **do not invent a new query parameter**. `q` searches `order_no`, `external_ref`, customer name, and the order's contact phone number (required by US-CS-01 AC1 and docs/03 A14).
- Implement **server-side** normalization of phone punctuation/spacing and equivalent international formatted forms; require an adequately specific phone query, rather than enumerating contacts by a short suffix. Keep existing order number/name matching. Normalization and any index strategy require Dev 1 review; no new public query DTO is authorized.
- Existing market/role scope, rate/abuse controls, pagination and 403/404 policy remain enforced. Do not put the unmasked phone into URL/access/error/analytics logs or broaden CS access across markets. CS search results must not expose raw phone fields.
- **Dev 1** implements and tests backend query, scopes and abuse/PII protection; **Dev 3** calls the same `q` and displays clear unavailable/error behavior until real API tests pass. Frontend-only search over the loaded page is not a substitute.

## DEC-CS-PRIVACY-20261109 — Role-scoped CS response and default masking (CS-02)

- CS sees only information required to answer order status, committed delivery window, ETA and permitted notification history, plus a **masked** phone/email representation; use existing `MaskedText` presentation without a CS reveal action. No raw phone/email values in the CS DOM, network payload or logs.
- For CS responses, the **backend** must omit sensitive fields not authorized for CS: GPS/coordinates (`delivery.lat/lon`), `receiving_restrictions` (including gate/access codes), internal risk scores, private/internal planning decisions, and other secret notes. A `delivery` summary, if provided, must contain only safe customer-service fields, never raw restrictions. In particular, frontend hiding alone is insufficient.
- Document a CS-specific allowlisted DTO/projection and implement it in Dev 1 API/service; agree the exact masked field names/types during API contract review so generated types match the runtime. Other roles' contracts are unchanged by this CS-specific decision.
- CS cannot approve, dispatch, replan, change delivery promises or send DELAY notifications. Server rejects unauthorized mutations independently of hidden UI controls. `GET /orders/{id}/notifications`, `GET /orders/{id}/eta-forecasts`, and `GET/POST /orders/{id}/contact-logs` remain backend integration blockers where stubbed.
- Dev 3 may build a **clearly marked mock-only** contact-log form using CS-local mocks, without editing shared router/global mocks or claiming persistence. No mock production data, fake successful save or E2E completion claim.

## DEC-M6-PREP-QUEUE-20261109 — Approve PROPOSAL-M6-PREP-QUEUE-001 (M6)

- **Owner approves the existing proposal's contract**, not any PR implementation: canonical `GET /api/v1/warehouses/{id}/prep-queue?date=YYYY-MM-DD`; legacy `GET /prep-queue?warehouse_id=&date=` if retained is a same-implementation/same-shape alias. One authoritative `capacity + orders` response, per-vehicle `loading[]`, nullable `next_action`, correctly typed JSON numbers, offset-aware instants.
- `capacity.schedule_verified` is required boolean; missing verified official roster gives **zero verified availability**, `schedule_verified=false`, no fabricated capacity, with read-only orders only when trustworthy. All plan approval/driver shift/history safety remains fail-closed.
- `GET /locations` list/detail expose authoritative non-null `timezone` IANA from market. UI must not fall back to browser timezone; business date uses warehouse market-local date.
- Existing `docs/06` Appendix A.1 and `docs/ASSUMPTIONS.md` proposal details are the approved baseline. Dev 1/Dev 3 still need aligned OpenAPI, PostgreSQL/API integration tests, multi-vehicle, cross-midnight/DST and real-backend E2E. Draft/stacks #129/#159/#154/#160 are not automatically approved or merged.

## DEC-STOCK-GRANT-CONTROL-20261109 — Owner-delegated System Admin controls Stock Admin grants (STOCK)

- **Only a System Admin expressly delegated by the Owner** can issue **or revoke** market-specific Stock Admin grants, both initial and later grants. A normal `admin` role, a Stock Admin grant, or market membership alone is insufficient; Stock Admin may not issue/revoke another Stock Admin's grant or self-grant.
- Require a verified delegation/authority record, explicit market/scope, grantor distinct from grantee, reason, effective/revoked status, immutable actor/time/before/after audit and server-side checks. Preserve S1/S2 separation of duties for scope/evidence approval, including independent approver. Technical representation of delegation, bootstrap endpoint, revocation, races and audit action names require Dev 1/2 review before implementation.
- This extends `DEC-STOCK-GRANT-BOOTSTRAP-20261109` from *first grant only* to **all** Stock Admin grant issuances/revocations. It grants **no** authority to write physical WMS inventory or enable stock ingestion/production writers. PR #148/#164 remain subject to migration/API/RBAC/transaction review.

## DEC-D8-STAGING-SCHEDULE-20261109 — Approve D8 proposed job cadence for staging/demo only (D8)

- The owner approves the **proposed cadence/job list** in `docs/proposals/D8_SCHEDULER_SWEDEN_PROPOSAL_20261108.md` as the **staging/demo implementation and test baseline**, subject to the existing per-job guards. The previously owner-approved `operational_review` slots of **07:00 and 13:00 Europe/Stockholm** remain unchanged.
- This permits Dev 2 to build and test the proposed ingest/stock freshness, hold expiry, template-limited outbox, GPS lost, milestone, metrics, retention, event-driven ETA and review orchestration in staging against synthetic/test data, after Dev 1 concurrency review. `attendance_gen` remains **disabled** until its official roster contract is implemented and reviewed; no synthetic attendance/shifts.
- **No production scheduler/job activation**, no real-customer notification, no real-worker GPS tracking or unapproved historical read, no physical WMS write, no implicit hosting purchase or spend, and no relaxation of approval/shift/quiet-hour rules.
- Tick endpoint authentication/DTO, new error codes, job dispatch internals, failover/SLA, cron provider, prices, source dependency contracts and deployment require **separate technical review and, when applicable, explicit future production/hosting authorization**. This approval does **not** approve previously unresolved technical contract names by implication.
- Update outdated text in the proposal about immediate destruction of legitimate GPS history: `DEC-GPS-RET-20261109` requires immediate stop of collection/live access and authorized history retention **up to 7 days**, followed by controlled erasure.

## Implementation/review gate

- **Docs-only PR:** align `docs/ASSUMPTIONS.md`, `docs/02`, `docs/03`, `docs/06`, D8 proposal, and `docs/CHANGELOG.md` (plus stock governance docs where relevant). Link this record; preserve nonapproved `ASM-004`, `ASM-008` and other undecided requests as pending.
- **Dev 1:** CS search and masked server DTO, Stock Admin authorization, M6 read API/OpenAPI; **Dev 2:** D8 staging jobs, approved market clocks and security; **Dev 3:** CS UI and Prep Queue consuming real DTO without unsanctioned shared-router/global-mock edits.
- Review diff, relevant tests and exact-head CI before code merges. No application source changes, migration, job activation or PR merge are part of this decision-record PR.
