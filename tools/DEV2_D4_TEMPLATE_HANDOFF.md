# D4 template delivery handoff — 2026-11-08

DEC-DEV2-D4-001, US-NOT-01/02/03 subset. No new business decision, schema or API change.

`notification_templates.render_message` is the canonical version-1 renderer for the five existing
status templates. English pilot locales only; unsupported locales fail closed pending reviewed
translations. Variables are restricted to a typed public reference and optional ordered aware
`eta_window {start,end}`. DELAY requires an ETA. Unknown fields/free text fail validation.

The existing outbox now renders immediately before transport and persists the canonical subject/body,
ignoring any legacy raw text. Automatic templates derive windows from the order's approved promise;
DELAY uses the stored validated ETA. Invalid template data fails without transport, with a sanitized
error and no delivery attempt. Existing quiet hours, draft guard, shadow mode, recipient allowlist,
attempt cap and at-least-once limitation remain.

Required follow-up for complete D4 acceptance:

- Reuse the same renderer for preview and explicit Dispatcher Send; do not accept arbitrary body or
  subject. API/authorization/enqueue/deduplication remain separate implementation tasks, not complete.
- Review/localize literal template copy and typed reason choices before adding more variables. No
  GPS, staff/recipient names, CS notes, source free text or internal scores can become variables.
- Renderer version is code metadata; do not claim persisted immutable template-version history yet.
- DELAY creation/send/discard still requires proper Dispatcher scope/idempotency/audit; a queued row
  alone is not proof that those missing workflow boundaries have been implemented.
- No real-customer email: SMTP/DB commit reconciliation is still required by DEC-NOTIFY-001.

Validation: unit injection/locale/ETA tests plus PostgreSQL outbox tests for canonical email/SMS,
invalid DELAY, quiet hours, retries, suppression and concurrent workers. No real messages sent.
