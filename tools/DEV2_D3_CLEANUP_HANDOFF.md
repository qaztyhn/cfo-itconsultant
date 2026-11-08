# D3 GPS maintenance handoff — 2026-11-08

Implements DEC-DEV2-D3-001 for maintenance and simulator only (US-GPS-03 AC1/AC2,
US-GPS-01 AC4 subset). No new decision or schema/API change.

- `purge_positions(session, now=...)` retains only points in an active on-road trip and currently
  verified official driver shift, with active employee/warehouse assignment and GPS-enabled market.
  It removes terminal/off-duty/unknown-duty points immediately when called, including recent points,
  even when ended_at is missing. Retained points must be within departure/duty bounds and not future.
- Duty uses market timezone, overnight intervals and half-open end; ambiguous DST boundaries fail
  closed. No shift or attendance is created or modified. Driver duty/tachograph logs are untouched.
- Loss checks stop/resolve when authorized duty ends. Simulator uses exactly 1800 seconds.
- Tests: real PostgreSQL checks cancellation/completion, disabled GPS, missing/cancelled shifts,
  inactive employees/assignments, overnight market timezone, point bounds and idempotency.

## Required integration before full D3 acceptance

- Dev 1: call `purge_positions` inside the terminal trip workflow/transaction and on shift end/revocation.
  Coordinate trip row locking with future ingest so completion cannot race an accepted upload. This
  repair function alone does not guarantee immediate cleanup at every workflow boundary.
- Dev 1/2: durable Dispatcher-to-trip assignment schema/auth is still missing. GPS API remains a stub;
  do not expose coordinates to all Dispatchers in a market. Upload must validate driver, shift, consent,
  recorded timestamp and current on-road status under the same concurrency boundary.
- Dev 3: stop collection and purge the offline queue/cache at trip or shift end; server rejects late replay.
- D8 scheduler is not approved: no scheduler cadence is enabled by this task. Operators can explicitly
  invoke the existing maintenance CLI on a prepared synthetic environment.
- Backup/restore/privacy review remains necessary. No claim of GDPR certification or device erasure.
- Legacy `GpsCfg.retention_days` is ignored by this cleanup; Dev 1 owns replacement settings/schema.
