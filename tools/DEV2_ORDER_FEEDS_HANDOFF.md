# Submitted/cancelled REST feeds — 2026-11-08

DEC-SRC-D1-001 D1-A/C: independent read methods for `status=SUBMITTED_FOR_PLANNING` and `status=CANCELLED`,
using inclusive aware updated_since, all-page validation and the existing duplicate/ordering guards.
Submitted rows preserve source version, snapshot/contact/SKUs and address_ref; no mapping or routing is
decided. Source exact dates normalize date_to=date_from in the internal CFO DTO (which requires an end),
without changing the source DTO or a promised delivery date. Cancellation DTO retains only identity,
version/time and cancellation provenance; it does not require/expose customer address/contact.

The source produces these feeds in #100/#102/#104 and candidate contract #106. Review/merge source stack
before runtime integration. No source writes, DB persistence, checkpoint updates or notifications occur here.

## Required Dev 1/2 integration

- Maintain separate submitted/cancelled durable checkpoints; advance only after every page succeeds.
  Retry failed feeds with overlap/idempotent versions, never mark a partially consumed iterator complete.
- Polling never decides cfo/legacy or creates CustomerOrder for undecided source orders (DEC-ROUTING-002).
- Do not apply raw Source cancellation directly to CFO status: review allowed transitions, release holds
  atomically and append audit. Approved pre-dispatch changes generate suggestion only; after dispatch,
  escalate without replacing committed fulfilment. Protect duplicate/source-version/routing decisions.
- `address_ref` enables a later structured receiving-calendar lookup; do not treat missing source window
  as 24/7 or assume source/customer calendar equals market defaults. Source address slots and CFO
  warehouse/driver schedules are distinct. Schema/context handoff is required before planning acceptance.
- Source free text/reasons and sales/store codes are not trusted safety flags, authorization or customer
  message variables. Do not copy raw PII into technical or immutable audit logs.

Assumptions: reviewed; DEC-SRC-D1-001 / DEC-ROUTING-002; none new. This is transport, not full ingestion.
