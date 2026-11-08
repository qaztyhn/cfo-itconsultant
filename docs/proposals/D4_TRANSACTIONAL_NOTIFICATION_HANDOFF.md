# D4 notifications — M6/M7 transactional handoff proposal

**Status: proposed, not approved.** Dev 2 owns `notify_service`/delivery; Dev 1 owns M6 execution and M7 risk; Dev 3 owns preview/send UI. This file changes no route, schema, template or business decision. It follows owner-approved D4, `DEC-NOTIFY-001` and `docs/06` §10; real customer email/SMS remains prohibited.

## Current verified boundary

- `notification_templates.py` has fixed versioned `CONFIRMED|DISPATCHED|DELIVERED|FAILED|DELAY` rendering and allowlisted public order/status/ETA variables. `notification_delivery.py` uses market-local quiet hours, the configured attempt cap and Mailpit/test-recipient policy. Its external delivery is at-least-once, not an exactly-once transaction with PostgreSQL.
- `notify_service.enqueue`, `create_delay_draft`, `send_draft` and `discard_draft` are stubs. Their signatures do not accept the caller's `AsyncSession`. M6 event and M7 forecast/alert therefore cannot atomically create a notification today.
- An order forecast is an **instant**. It does not authorize a customer-facing DELAY **window**. M7 correctly reports `blocked_missing_approved_window`/adapter rather than sending.
- `ops.notification` has template, rendered body, `eta_window`, plan and dedupe key, but no explicit immutable template-version or variable snapshot. A later template change could alter a queued message if rendered at delivery time.

## Proposed service interface for Dev 1/2 review

All commands require the **existing caller-owned session**, never open/commit another transaction:

```text
enqueue(session, order_id, template, *, plan_id, event_or_approval_id) -> notification_id | None
create_delay_draft(session, order_id, *, approved_window, reason_code, forecast_version) -> notification_id
send_draft(session, notification_id, actor, *, approved_window_version, reason_code, idempotency_key) -> result
discard_draft(session, notification_id, actor, *, reason_text, idempotency_key) -> result
```

These are logical signatures, not approved API/DTOs. The first four templates may queue only after the corresponding committed approval/execution transition, with a dedupe identity tied to the actual plan/event (multi-vehicle DISPATCHED once per order). `DELAY` is always draft; Dispatcher explicitly reviews/sends/discards it. Both delivery paths render server-side from typed allowlisted variables; ignore/reject legacy free-text bodies and never include driver identity, GPS, recipient name, notes or internal risk score. The customer-facing window must be validated against a separately approved source and version; do not derive bounds from `forecast_eta` alone.

M6 should call `enqueue(..., session=event_session)` after changing event/order state and before commit. M7 should create a DELAY draft in its ETA/alert transaction only if an approved window exists. Failure of required notification persistence rolls back the originating transaction or follows a **reviewed** transactional-outbox policy. Dispatcher send/discard writes the required audit and idempotency record in the same transaction. Outbox transport runs later and may remain at-least-once until a reviewed claim/acknowledgment design exists; test recipients only.

**Persistence choice for review:** pin `template_version` and typed variable/window reference on each notification (migration + `05/06` update), or store an immutable render snapshot with version and verify it matches the allowlisted renderer before delivery. Prefer explicit version + typed snapshot for replay and audit. Do not treat the current `body` column as permission for arbitrary text. No migration is included here.

## PostgreSQL / contract tests after approval

1. Approval queues one CONFIRMED with approved plan and existing promise window; rollback of approval leaves no notification. Repeat approval/event idempotently creates no duplicate.
2. Multi-vehicle DISPATCHED creates one order-level notification; DELIVERED and FAILED use actual terminal outcomes. Event, ETA, alert and notification roll back together on a forced insert/audit failure.
3. DELAY with no approved window produces no draft/send; a single forecast instant cannot become a window. Wrong/expired window version, unapproved reason/phrase, free-text body or wrong Dispatcher scope rejects atomically.
4. Template version and allowlisted variables reproduce preview and delivered content. Unknown locale/version, names, GPS, driver, internal score and raw Source notes never reach transport or logs.
5. Market-local quiet hours including DST, attempt cap, shadow suppression, duplicate workers and test-recipient refusal retain current behavior. No real customer recipient is contacted.

## Owner decisions and reviewer questions

| Question | Options | Recommendation for review |
|---|---|---|
| Who approves a new DELAY window? | Dispatcher; source order; other authorized actor | Dispatcher records a specific reviewed window before draft/send; Dev 1 confirms relation to date-negotiation rules. |
| What bounds and validity does that window have? | Configured range; manual reviewed interval | Explicit approved start/end and version, never inferred from one forecast ETA. |
| How is a template version pinned? | New notification column + typed variables; immutable render snapshot | Persist version and typed variables with migration/audit. |
| What if notification enqueue fails inside M6/M7? | Roll back event/risk; reviewed transactional outbox | Prefer one DB transaction; assess business necessity before allowing event without notification. |
| What retry timing follows a failed transport? | Next tick; 5/15-minute backoff | Keep approved cap; backoff needs owner approval before code. |
| What proves provider delivery? | At-least-once Mailpit/test; external acknowledgment | Retain test-only policy; no exactly-once or real-customer claim. |

Until Dev 1/2 and owner review the window/version/transaction choices, the stubs remain fail closed and M6/M7 notification E2E is incomplete.
