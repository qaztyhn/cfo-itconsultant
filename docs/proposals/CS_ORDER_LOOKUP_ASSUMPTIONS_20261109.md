# CS Order Lookup (US-CS-01 / US-CS-02) — assumption proposals

**Status: PROPOSED. Not owner-approved.** No ID below may be labelled "approved" or copied into the approved table of
`docs/ASSUMPTIONS.md` until the owner or the authorised review group confirms it in a reviewed PR
(`docs/09_AI_Coding_Rules.md` §14, `AGENTS.md` "Scope, uncertainty and team handoff").

Author: Dev 3 (stream C, M8, branch `feat/m8-cs-lookup-ui`). Reviewers: Dev 1 (backend owner of the affected
endpoints), Dev 2 (logging/retention), owner.
Source of the direction: written review of `main` against US-CS-01/02, docs/03 and docs/06, recorded in the
Dev 3 task thread on 2026-11-09. That review is a **review comment, not a recorded owner approval**.

Docs affected if approved: `docs/06_API_Specification.md` §5.3, §5.4, §11 and `docs/CHANGELOG.md`, in the **same
docs PR**. This file changes none of them.

## How agents must read this file

1. Treat every ID here as `proposed`. Build UI that works with the **current** contract and fails closed.
2. Do not claim a feature works end to end because the UI exists. Items marked **BLOCKED** need backend work.
3. Do not invent endpoints, query parameters, fields or error codes. If something is missing, report it.
4. If a rule here conflicts with `docs/09` or `docs/06`, the higher-precedence document wins and you stop and report.

## Verified facts on `main` (checked against source, not only documents)

| # | Fact | Where |
|---|---|---|
| F1 | `GET /orders?q=` matches only `order_no`, `external_ref` and customer name (case-insensitive). No phone. | `backend/app/services/order_read_service.py` (`ilike` on those three columns) |
| F2 | `GET /orders/{id}` builds `contact` with `name`, `phone`, `email` from the order. `customer_service` shares the `store` field tier with `sales`. | `order_read_service.py` (`contact` dict; role tier map) |
| F3 | `GET /orders/{id}/eta-forecasts`, `GET /orders/{id}/notifications`, `POST /orders/{id}/contact-logs`, `GET /orders/{id}/contact-logs` are stubs that `raise NotImplementedError`. | `backend/app/api/v1/orders.py` |
| F4 | `/cs/orders` already renders `<OrderLookup />`; role `customer_service` only. `/cs/contacts` is a placeholder. | `frontend/src/app/routes.tsx`, `access.ts` |
| F5 | `ops.customer_contact_log` DDL exists: `channel IN ('phone','email','chat')`, `reason_code IN ('where_is_my_order','change_request','complaint','delay_inquiry','other')`, `note` optional. | `docs/05_Database_Design.md` |
| F6 | `GET /orders/{id}/timeline` is specified in docs/06 §5.5; its backend status was **not** verified by Dev 3. | n/a |

## Proposed decisions

### ASM-CS-PHONE-SEARCH-20261109 — phone search through the existing `q` parameter

- **Rule:** keep `GET /api/v1/orders?q=...`. No new query parameter. Backend extends `q` to also match the order's
  contact phone (`contact_phone`).
- **Normalisation:** `+46 70 123 12 34` and `+46701231234` must find the same order. Prefer a full normalised number
  match. Do not match on a few trailing digits.
- **Safeguards (backend):** restrict to the caller's market scope (docs/06 §5.2); rate-limit or otherwise prevent bulk
  enumeration; never write the raw phone number to access or technical logs (invariant 16).
- **Frontend rule until implemented:** the search box must not claim or imply phone search. Show neutral copy such as
  "Order no., external ref or customer name". Record the gap in the PR. After backend ships, update copy and add a test.
- **Owner:** Dev 1. **Status:** proposed. **Implementation:** BLOCKED (backend + docs/06 §5.4).
- **Affected files:** `backend/app/services/order_read_service.py`, `docs/06` §5.4, tests.

### ASM-CS-PROJECTION-20261109 — dedicated server-side response projection for `customer_service`

- **Problem:** per F2, `GET /orders/{id}` can return full phone, email, delivery coordinates and
  `receiving_restrictions` to CS. Masking in the browser does not protect data that is visible in the Network response.
- **Rule:** backend adds a response projection for `customer_service` that returns only allowed fields. For CS the
  response must **omit** (not null): GPS/`lat`/`lon`, `receiving_restrictions` and gate codes, `special_requirements`
  free text unless separately approved, internal risk scores (only `risk{status,color,forecast_eta}` is allowed),
  `approved_plan_id`, `latest_run_id`, decision-log content, `handling_group` and `flags`. Phone and email are returned
  **already masked by the server** or omitted; the CS UI has **no reveal control**.
- **Docs:** `docs/06` §5.3 currently gives `customer_service` the same `contact`/`delivery` blocks as `sales`. It must be
  updated in the same docs PR.
- **Forbidden operations:** CS calling approve, dispatch, replan, cancel, date change or DELAY send must receive
  `403` from the server. Hiding buttons is not enforcement.
- **Frontend rule until implemented (defence in depth, not a substitute):** an allowlist projection in
  `features/cs/` copies only permitted fields into state, so forbidden fields never reach component props or the DOM even
  if the server over-returns. Phone/email render through `MaskedText` with `revealed` never set.
- **Owner:** Dev 1. **Status:** proposed. **Implementation:** BLOCKED (backend + docs/06 §5.3).
- **Affected files:** `backend/app/services/order_read_service.py`, `docs/06` §5.3, `docs/CHANGELOG.md`, RBAC tests
  including the forbidden path for CS.

### ASM-CS-CONTACT-MOCK-20261109 — contact-log form is mock-only until the backend exists

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
- **Owner:** Dev 3 (UI), Dev 1 (backend). **Status:** proposed. **Implementation:** UI mock allowed; real path BLOCKED.

### ASM-CS-READ-DEPS-20261109 — ETA and notification history depend on unimplemented endpoints

- **Rule:** the UI may render ETA versions and notification history from `GET /orders/{id}/eta-forecasts` and
  `GET /orders/{id}/notifications`, and may be tested with request mocks **inside test files only**. At runtime, while
  those endpoints raise `NotImplementedError`, the UI shows its error state. It must **not** fabricate ETA or
  notification data and present it as real.
- **Owner:** Dev 1. **Status:** proposed. **Implementation:** BLOCKED.

### ASM-CS-TIMELINE-20261109 — timeline kinds shown to CS

- **Rule (restates docs/06 §5.5, no new contract):** CS timeline shows only `order_submitted`, `milestone` (no
  coordinates), `notification`, `eta` (`forecast_eta`, `risk_status` only). `planning_run` and `decision` must never
  render for CS. The UI filters by allowlist, so an unknown `kind` is dropped rather than shown.
- **Status:** proposed (clarification of an existing contract). **Implementation:** UI only.

## Completion gate

US-CS-01 and US-CS-02 must **not** be marked complete end to end until, against the real backend: phone search works
with normalisation and safeguards; the CS projection is enforced server-side with a forbidden-path test; contact logs
are stored with actor and timestamp; ETA and notification endpoints return data. UI tests with mocks prove UI behaviour
only.

## Draft rows for `docs/ASSUMPTIONS.md` (paste only after approval; status shown is the proposed one)

| ID | Decision | Date | Evidence | Implementation status |
|---|---|---|---|---|
| ASM-CS-PHONE-SEARCH-20261109 | Extend `q` to contact phone, normalised, scoped, rate-limited, no raw phone in logs | 2026-11-09 | Dev 3 task thread review (pending owner approval) | Proposed; backend blocked |
| ASM-CS-PROJECTION-20261109 | Server-side CS projection; no reveal; 403 on forbidden actions | 2026-11-09 | same | Proposed; backend and docs/06 §5.3 blocked |
| ASM-CS-CONTACT-MOCK-20261109 | Contact-log form mock-only and labelled demo until backend exists | 2026-11-09 | same | Proposed; UI mock allowed |
| ASM-CS-READ-DEPS-20261109 | ETA/notification UI depends on unimplemented endpoints; no fabricated data | 2026-11-09 | same | Proposed; backend blocked |
| ASM-CS-TIMELINE-20261109 | CS timeline kind allowlist per docs/06 §5.5 | 2026-11-09 | docs/06 §5.5 | Proposed; UI only |

PR line for the frontend PR: `Assumptions: reviewed; proposed ASM-CS-PHONE-SEARCH-20261109, ASM-CS-PROJECTION-20261109,
ASM-CS-CONTACT-MOCK-20261109, ASM-CS-READ-DEPS-20261109, ASM-CS-TIMELINE-20261109 pending owner approval`.