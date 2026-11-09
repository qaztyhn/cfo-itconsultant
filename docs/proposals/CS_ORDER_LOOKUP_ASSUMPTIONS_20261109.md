# CS Order Lookup (US-CS-01 / US-CS-02) — owner-approved policy and implementation handoff

**Reconciled with `main` on 2026-11-09.** CS-01 and CS-02 are **OWNER APPROVED** as
[DEC-CS-SEARCH-20261109](../decisions/DEC_CS_M6_STOCK_D8_OWNER_APPROVED_20261109.md) and
[DEC-CS-PRIVACY-20261109](../decisions/DEC_CS_M6_STOCK_D8_OWNER_APPROVED_20261109.md).
They are already recorded in `docs/ASSUMPTIONS.md`, `docs/06_API_Specification.md` and `docs/CHANGELOG.md`.
**Approval of policy is not evidence that the backend or UI has implemented it.** The code gaps below remain blocked.
The old `ASM-CS-...` labels in this handoff identify Dev 3 review topics, **not five new owner-approved decisions**.

Owner: Dev 3 (CS UI), coordinating with Dev 1 (backend), Dev 2 (logging/privacy), and the project owner.
This is a supplemental implementation handoff; it must not supersede existing owner decisions or the API contract.

## How agents must read this file

1. Follow the approved CS-01/CS-02 decisions; treat detailed field/DTO suggestions beyond their scope as subject to contract review.
2. Keep current behaviour marked unavailable where the implementation is still a stub. No mock data or UI masking is evidence of backend compliance.
3. Do not invent endpoints, parameters, fields, approvals or an operational E2E result.
4. If this implementation handoff differs from the latest `docs/ASSUMPTIONS.md`, `docs/06` or owner decision record, those authoritative sources win.
## Verified implementation facts on `main` (rechecked 2026-11-09)

| # | Fact | Where |
|---|---|---|
| F1 | `GET /orders?q=` matches only `order_no`, `external_ref` and customer name (case-insensitive). No phone. | `backend/app/services/order_read_service.py` (`ilike` on those three columns) |
| F2 | `GET /orders/{id}` builds `contact` with `name`, `phone`, `email` from the order. `customer_service` shares the `store` field tier with `sales`. | `order_read_service.py` (`contact` dict; role tier map) |
| F3 | `GET /orders/{id}/eta-forecasts`, `GET /orders/{id}/notifications`, `POST /orders/{id}/contact-logs`, `GET /orders/{id}/contact-logs` are stubs that `raise NotImplementedError`. | `backend/app/api/v1/orders.py` |
| F4 | `/cs/orders` already renders `<OrderLookup />`; role `customer_service` only. `/cs/contacts` is a placeholder. | `frontend/src/app/routes.tsx`, `access.ts` |
| F5 | `ops.customer_contact_log` DDL exists: `channel IN ('phone','email','chat')`, `reason_code IN ('where_is_my_order','change_request','complaint','delay_inquiry','other')`, `note` optional. | `docs/05_Database_Design.md` |
| F6 | `GET /orders/{id}/timeline` is specified in docs/06 §5.5; its backend status was **not** verified by Dev 3. | n/a |

## Approved decisions, implementation blockers and remaining clarifications

### DEC-CS-SEARCH-20261109 — approved phone search (previously proposed as ASM-CS-PHONE-SEARCH-20261109)

- **Rule:** keep `GET /api/v1/orders?q=...`. No new query parameter. Backend extends `q` to also match the order's
  contact phone (`contact_phone`).
- **Normalisation:** `+46 70 123 12 34` and `+46701231234` must find the same order. Prefer a full normalised number
  match. Do not match on a few trailing digits.
- **Safeguards (backend):** restrict to the caller's market scope (docs/06 §5.2); rate-limit or otherwise prevent bulk
  enumeration; never write the raw phone number to access or technical logs (invariant 16).
- **Frontend rule until implemented:** the search box must not claim or imply phone search. Show neutral copy such as
  "Order no., external ref or customer name". Record the gap in the PR. After backend ships, update copy and add a test.
- **Owner:** Dev 1. **Policy:** OWNER APPROVED (CS-01); `docs/06` §5.4 is already aligned on `main`. **Implementation:** BLOCKED until the real backend and safeguards pass tests.
- **Affected implementation:** `backend/app/services/order_read_service.py` and query/scoping/anti-enumeration tests. No duplicate proposed rule should be added to `docs/06`.

### DEC-CS-PRIVACY-20261109 — approved CS-only masked projection (previously proposed as ASM-CS-PROJECTION-20261109)

- **Problem:** per F2, `GET /orders/{id}` can return full phone, email, delivery coordinates and
  `receiving_restrictions` to CS. Masking in the browser does not protect data that is visible in the Network response.
- **Rule:** backend adds a response projection for `customer_service` that returns only allowed fields. For CS the
  response must **omit** (not null): GPS/`lat`/`lon`, `receiving_restrictions` and gate codes, `special_requirements`
  free text unless separately approved, internal risk scores (only `risk{status,color,forecast_eta}` is allowed),
  `approved_plan_id`, `latest_run_id`, decision-log content, `handling_group` and `flags`. Phone and email are returned
  **already masked by the server** or omitted; the CS UI has **no reveal control**.
- **Docs:** `docs/06` §5.3 already documents the OWNER APPROVED CS-specific masked projection. Its exact generated DTO shape and implementation remain subject to Dev 1/3 review.
- **Forbidden operations:** CS calling approve, dispatch, replan, cancel, date change or DELAY send must receive
  `403` from the server. Hiding buttons is not enforcement.
- **Frontend rule until implemented (defence in depth, not a substitute):** an allowlist projection in
  `features/cs/` copies only permitted fields into state, so forbidden fields never reach component props or the DOM even
  if the server over-returns. Phone/email render through `MaskedText` with `revealed` never set.
- **Owner:** Dev 1. **Policy:** OWNER APPROVED (CS-02). **Implementation:** BLOCKED until backend projection, forbidden-path and privacy regression tests pass.
- **Affected implementation:** `backend/app/services/order_read_service.py`, CS-specific DTO/OpenAPI and RBAC/privacy tests (including forbidden mutations). `docs/06` and `docs/CHANGELOG.md` already record the approved policy.

### CS contact-log demo — limited mock-only UI allowed under CS-02 (previously ASM-CS-CONTACT-MOCK-20261109)

- **Rule:** Dev 3 may build the form (`channel`, `reason_code`, `note`) inside CS-owned files. While F3 holds, the form
  must not call `POST /orders/{id}/contact-logs`.
- **UI honesty rules:**
  - Never show "Saved successfully" or any success wording that implies persistence.
  - Always show a visible "Demo only — not saved to backend" label.
  - Demo entries live only in component state, are labelled as demo and never presented as saved contact history.
  - Do not edit global mocks (`src/api/mocks/*`).
- **Validation (UI):** `channel` ∈ {`phone`,`email`,`chat`}; `reason_code` ∈ the five codes in F5; `note` optional.
  No length limit is invented in the UI; the server owns any limit.
- **Switch-over:** when Dev 1 ships the endpoints per docs/06 §11 (RBAC, actor and timestamp recorded), replace the mock
  with the real call using the approved contract only, then add integration evidence.
- **Owner:** Dev 3 (UI), Dev 1 (backend). **Status:** limited mock-only UI is allowed by OWNER APPROVED CS-02; real contact-log persistence remains BLOCKED. This is not a separate approved ASM decision.

### ETA and notifications — implementation dependency (previously ASM-CS-READ-DEPS-20261109)

- **Rule:** the UI may render ETA versions and notification history from `GET /orders/{id}/eta-forecasts` and
  `GET /orders/{id}/notifications`, and may be tested with request mocks **inside test files only**. At runtime, while
  those endpoints raise `NotImplementedError`, the UI shows its error state. It must **not** fabricate ETA or
  notification data and present it as real.
- **Owner:** Dev 1. **Status:** existing endpoint dependency, currently BLOCKED. The no-fabrication rule follows the approved CS-02 safety boundary; no new API contract is authorized here.

### CS timeline — existing API allowlist (previously ASM-CS-TIMELINE-20261109)

- **Rule (restates docs/06 §5.5, no new contract):** CS timeline shows only `order_submitted`, `milestone` (no
  coordinates), `notification`, `eta` (`forecast_eta`, `risk_status` only). `planning_run` and `decision` must never
  render for CS. The UI filters by allowlist, so an unknown `kind` is dropped rather than shown.
- **Status:** implementation guidance from the existing `docs/06` §5.5; not a newly approved assumption. Backend timeline behaviour still requires real-response verification.

## Completion gate

US-CS-01 and US-CS-02 must **not** be marked complete end to end until, against the real backend: phone search works
with normalisation and safeguards; the CS projection is enforced server-side with a forbidden-path test; contact logs
are stored with actor and timestamp; ETA and notification endpoints return data. UI tests with mocks prove UI behaviour
only.

## Decision and delivery tracking (no duplicate ASSUMPTIONS rows)

| Topic | Authoritative status | Outstanding implementation |
|---|---|---|
| Phone search (`ASM-CS-PHONE-SEARCH-20261109`) | **OWNER APPROVED** as `DEC-CS-SEARCH-20261109` | Dev 1 query normalisation, market scope, abuse controls and real API tests |
| CS masked projection (`ASM-CS-PROJECTION-20261109`) | **OWNER APPROVED** as `DEC-CS-PRIVACY-20261109` | Dev 1 CS-only DTO/OpenAPI, zero raw PII, negative RBAC tests |
| Contact-log demo (`ASM-CS-CONTACT-MOCK-20261109`) | **Mock-only implementation permitted** under CS-02; no separate ASM approval | Dev 3 honest demo; Dev 1 persistence API and tests |
| ETA/notifications (`ASM-CS-READ-DEPS-20261109`) | Documented dependency; not a separate owner decision | Dev 1 implement GET endpoints and prove role-scoped reads |
| Timeline allowlist (`ASM-CS-TIMELINE-20261109`) | Existing `docs/06` §5.5 contract; not a new decision | Dev 3 safe UI allowlist; verify backend real response |

**PR description recommendation:** `Assumptions: reviewed. DEC-CS-SEARCH-20261109 and DEC-CS-PRIVACY-20261109 are owner-approved policies on main; original ASM-CS labels are Dev 3 handoff references only. Backend search/projection and contact/ETA/notification E2E are still blocked.`
