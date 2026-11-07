# M1 source contract proposal — pending approval

Owner: Dev 2. Review: Dev 1 (adapter/ingestion DTOs), Dev 3 (POS UI).
Requested by project owner on 2026-11-07. This document proposes decisions;
it does not amend approved `05` / `06` and does not authorize implementation.

## Why a decision is needed

`06` section 16 shows contact, receiving restrictions and special requirements
in an order, and requires a delivery address/coordinate snapshot. `05` section
10 and the current source models only reference a mutable address/customer.
The write request/response schemas and validation-error details are incomplete.
`07` section 2 also requires working-day and receiving-hours validation, but
the source has no receiving calendar or country calendar configuration.

Affected stories: US-SRC-02 AC1, US-SRC-03 AC1, US-ORD-01;
rules: BR-GEN-02, BR-ORD-01. CFO remains read-only toward the source.

## Decisions to approve

| ID | Proposed decision | Impact |
|---|---|---|
| SRC-Q1 | Store order-level address, lat, lon and contact name/phone/email as snapshots, plus nullable receiving_restrictions/special_requirements. | Add explicit columns to the source table definition in 05; no CFO schema change. |
| SRC-Q2 | POST/PUT accept customer_id, address_id, contact, date fields, sales/store codes, requirements and lines. Snapshot address/coordinates server-side from the selected address; never trust client coordinates. | Specify exact write schema in 06; reject extra fields. |
| SRC-Q3 | POST returns 201 with the order representation; PUT, validate, submit and cancel return 200 with that same representation. | Common DTO for POS and adapter; specify money strings, numeric quantities, aware timestamps. |
| SRC-Q4 | Validation failure returns 422 VALIDATION_ERROR with details.errors containing field paths and stable reasons, no echoed customer data. | Agree exact field paths/reasons with Dev 3 before coding. |
| SRC-Q5 | A successful validate moves DRAFT to VALIDATED; editing a validated order resets it to DRAFT; submit revalidates under a row lock before SUBMITTED_FOR_PLANNING. | Prevent validation becoming stale. Group must approve status/version semantics below. |
| SRC-Q6 | All list reads use {items,page,page_size,total}, default page=1/page_size=50, maximum 500, and X-Total-Count; /stock keeps its explicit {as_of,items} snapshot shape. | Clarify whether pagination applies to customers/products/inbound/fleet/addresses as well as orders. |
| SRC-Q7 | Incremental reads use updated_at >= updated_since, stable timestamp + natural-key ordering; orders use id, products sku, composite-key entities use all key parts. | Ties do not disappear at a checkpoint boundary; adapter overlap/upsert handles duplicates. |
| SRC-Q8 | Introduce source instance calendar configuration and receiving hours per address, or explicitly defer these validations with an approved spec change. | No guessed workweek, holiday market or opening hours in validation. |
| SRC-Q9 | A stock snapshot is an atomic batch with one as_of; empty snapshots also retain batch time. | Current per-row as_of cannot represent an empty snapshot or guarantee a consistent batch. Agree storage/seed rule. |
| SRC-Q10 | Specify stock normalization when several local SKUs map to one global product, including units_to_base and whether source rows represent distinct physical inventory. | Source key is warehouse/SKU; CFO key is warehouse/global_product_id. Neither last-row-wins nor unconditional summation is safe without this rule. Blocks stock persistence, not the read-only stock transport. |

The ASM-005 legacy-routing decision merged in main is authoritative for ingestion: an order with any
unconfirmed SKU must remain in the existing process, and later mapping must not automatically pull
that historical order into CFO. This source proposal does not override that decision. The legacy
handoff marker and double-fulfilment protection still need an approved integration contract.

## Proposed order representation

Keep the existing names from 06: id, version, updated_at, status, customer_id,
address_id, contact {name, phone, email}, date_mode, date_from, date_to,
window_start, window_end, receiving_restrictions, special_requirements,
sales_code, store_code, lines [{line_no, sku, qty, unit_price}].

Add explicit `address`, `lat`, `lon` snapshot fields to the example/schema.
Define nullable fields and draft completeness before code: 05 currently requires
customer_id/address_id even for DRAFT, whereas incomplete POS drafts might not
have them. Recommendation: keep these two references required for persisted
drafts; let the UI hold an incomplete form locally. Group approval required.

Order IDs are server-generated opaque strings. `version` and `updated_at` are
server-owned. PUT replaces editable fields and all lines atomically; request
includes the expected version, and stale writes return 409 ILLEGAL_TRANSITION
unless the group approves a distinct conflict code. No new code is added here.

## Proposed lifecycle (requires approval)

- Create: DRAFT, version 1.
- Edit DRAFT/VALIDATED: DRAFT, version +1, old validation invalidated.
- Validate DRAFT: VALIDATED, version +1 only on actual state change.
- Submit VALIDATED: recheck references/snapshot/date rules and transition to
  SUBMITTED_FOR_PLANNING, version +1, in one transaction.
- Repeat submit of an unchanged submitted order: return the current order.
- Cancel DRAFT/VALIDATED/SUBMITTED_FOR_PLANNING: CANCELLED, version +1;
  repeat cancel returns the current order.
- Edit a submitted/cancelled order: reject until the team specifies how source
  edits interact with CFO's ORDER_CHANGED_AFTER_APPROVAL behavior.
- Specify cancellation delivery to CFO: the documented orders filter defaults
  to SUBMITTED_FOR_PLANNING, which would otherwise hide CANCELLED updates.

The last two points are open business decisions, not implementation defaults.

## Validation acceptance to finalize

Require existing customer and address belonging to that customer; valid
latitude/longitude; at least one line with known SKU, unique positive line_no,
positive quantity and permitted price precision; valid exact/range/latest
dates and ordered receiving windows. Define whether zero price is allowed.
Specify which special requirements are structured constraints versus free text,
how invalid requirements are reported, and which receiving calendar applies.
Reject changes atomically: validation errors must not leave partial lines or
advance status/version. Never check CFO stock feasibility in source validation.

## Delivery after approval

1. Amend 05/06 and CHANGELOG with approved decisions; add source upgrade/bootstrap
   handling that preserves existing data. Dev 1 reviews schema/DTO alignment.
2. Define Pydantic schemas and generate the source OpenAPI baseline; contract
   tests run identical requests against SE and a second configured instance.
3. Implement read endpoints and deterministic pagination, then draft/validate/
   submit/cancel with real PostgreSQL transaction and concurrency tests.
4. Dev 3 consumes the approved schemas for POS. Dev 2 implements REST adapter
   ingestion, cancellation/version handling and full deterministic M1 seed.

Independent slice already implemented on `feat/m1-source-auth`: X-API-Key
protection on business routes (health public), instance-local secret configuration,
credential-free auth errors and OpenAPI security declarations. This is only
the authentication portion of US-SRC-02, not the full source contract.
