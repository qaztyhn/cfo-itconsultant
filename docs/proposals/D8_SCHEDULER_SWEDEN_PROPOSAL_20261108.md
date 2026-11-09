# D8 proposal — market-aware scheduler and secure internal tick (Sweden SE pilot)

**2026-11-08 — PROPOSED OVERALL; OWNER APPROVED TWO TIMES ONLY ON 2026-11-09.** The owner specifically asked for a reasonable D8 recommendation compatible with the Swedish market and the new approved D3/D4/D5 privacy, working-hours, retention and customer-notification rules. This is an implementation proposal only: do not claim the scheduler is deployed or running. Retain `DEC-HOLD-001` 15-minute TTL, `DEC-DRIVER-001` 11-hour rest, official warehouse/driver shifts, and Dispatcher authorization. Automated scheduler **never approves plans, assigns drivers outside official shifts, sends DELAY without Dispatcher, or turns on GPS**.

**Partial owner approvals:** [DEC-D8-OPS-20261109](../decisions/DEC_GPS_7D_AND_D8_REVIEW_TIMES_20261109.md) confirms **07:00 and 13:00 Europe/Stockholm** for *operational review*, not the complete scheduler registry. [DEC-GPS-RET-20261109](../decisions/DEC_GPS_7D_AND_D8_REVIEW_TIMES_20261109.md) supersedes immediate deletion of all lawfully collected GPS: **stop collection/live access on trip/shift end, retain only restricted historical points up to 7 days, then delete**. Physical cleanup/cadence and D6 hosting remain proposed; do not automatically enable jobs.

## Frequency proposal (SE = Europe/Stockholm IANA timezone incl DST)

| Job name | Scope | Proposal cadence | Guard / effect |
|---|---|---|---|
| `ingest_orders` | market | every **5 min**, plus Sales explicit sync-now | read source `SUBMITTED_FOR_PLANNING` and `CANCELLED` versions with durable independent checkpoints; never decide CFO/legacy routing automatically |
| `refresh_stock` | market | every **5 min** | only published coherent snapshot `as_of`, check data freshness; no last-row-wins and no double-counted stock aliases (SRC-Q9/Q10 approved under DEC-SRC-D1-001; publish and pool/adapter code still pending) |
| `stock_freshness` | market | every **5 min** | raise stale alert if latest stock `as_of` older than **15 min** market-configured; no fabricated zero stock |
| `hold_expiry` | global single owner (idempotent across markets) | every **1 min** | expire *only* 15-min unapproved holds; `PLANNED → SUBMITTED` only if latest eligible run; Plan Again is manual; no automatic approve/rehold |
| `notify_outbox` | market (or globally scoped DB worker honoring each market timezone) | every **1 min** | status/ETA allowlisted templates, market quiet hours **21:00–07:00** except Dispatcher-triggered DELAY exception; no real-customer send per DEC-NOTIFY-001 |
| `gps_lost` | market | every **5 min** | only trip `on_road` AND verified driver shift; with 30-minute sampling, raise `GPS_LOST` after **60 min** no fresh fix; resolve when trip/shift stops or source GPS disabled; do not query out-of-shift location |
| `gps_live_revoke_and_history_cleanup` | on trip/shift terminal event; scheduled cleanup cadence **still proposed** | live revocation immediately; historical expiry at max **7 days** (OWNER APPROVED) | stop tracking and live access on end, delete invalid device/offline pending queue, store authorized historical GPS separately with case-based access/audit only; erase after seven days with backup policy and DPIA/legal sign-off; do not erase all valid historical points immediately |
| `milestone_overdue` | market | every **5 min** | compare actual milestones vs deadlines and **30 min grace**; generate alerts/ETA recalculation only when overdue, never auto-dispatch |
| `eta_recalculate` | event-driven **only**, not periodic | new valid GPS fix / milestone / source change / material risk | with 30-minute GPS fixes, avoid inferring continuous actual position; stale GPS uses labeled route/milestone estimate |
| `operational_review` (replaces single morning check) | market | **07:00 and 13:00** market-local daily (TIMES OWNER APPROVED) | review orders, stock freshness, warehouse schedule and driver verified shifts/rest; *may alert*, **never auto-assign or approve** |
| `nightly_metrics` | market | **04:00** local daily | aggregate previous local business day, immutable completed history, no live GPS positions, role-filtered outputs |
| `retention` | market | **04:15** local daily | use approved D5 category/purpose/hold rules (not blanket 365/730 days), dry-run and audit; GPS deletion remains near-immediate event-triggered regardless of nightly job |
| `attendance_gen` | market | **DISABLED until code and official roster/attendance contract complete** | must not synthesize actual present staff or assign shifts via `expected_staff` |

**Times are technical operational defaults, not statutory Swedish clock times.** Sweden's GPS employment rules concern purpose, proportionality and no out-of-hours tracking; transport rules concern driving/duty/rest. Job workers may run at night without requiring the human driver to work, but must NOT collect/use GPS outside confirmed shifts. Swedish IMY guidance: https://www.imy.se/verksamhet/dataskydd/dataskydd-pa-olika-omraden/arbetsliv/kontroll-och-overvakning-av-anstallda/ . EU driving/rest: https://transport.ec.europa.eu/transport-modes/road/social-provisions/driving-time-and-rest-periods_en .

### Internal tick contract proposal

`POST /internal/tick?job=<whitelisted>&market=SE` uses `X-Internal-Key` over HTTPS, no browser/public access. `market` is mandatory for market-scoped jobs; only explicitly global `hold_expiry` allows `market` absent. Return:
```json
{
  "job": "gps_lost",
  "market": "SE",
  "status": "ok",
  "started_at": "2026-11-08T09:00:00Z",
  "finished_at": "2026-11-08T09:00:01Z",
  "processed": 12,
  "succeeded": 11,
  "failed": 1,
  "correlation_id": "<opaque>"
}
```
- 200 completed, 207/500? **choose 200 with `status=partial` only if per-item failure handling is deterministic**; 503 for failing dependency and prevent false "ok". Keep stable `{error:{code,message,details,correlation_id}}` envelope.
- Missing/wrong key => 401/403 (without credentials leak), unsupported/unimplemented job => controlled 422 `VALIDATION_ERROR` (never 500 NotImplementedError), invalid/missing market => 422, duplicate concurrent job/scope => 409 `JOB_ALREADY_RUNNING` **new code requiring approved 06 contract**, oversized workload => bounded batch and retry.
- One approved job name -> exactly one handler (no arbitrary dotted path/code execution), per-market permissions + structured count metrics; do not include PII, driver IDs or coordinates in scheduler log.
- Postgres advisory/row locks keyed by (job,market) and run id; protect cross-worker and external cron overlaps, `FOR UPDATE SKIP LOCKED` where appropriate, persistent run status/timeouts/checkpoints, idempotent retries. One scheduler leader per job deployment; do not run APScheduler in every Render API replica and external cron simultaneously.
- Source/approval guards: scheduler can ingest source but **cannot** create `order_routing` automatically without Sales/authorized Dispatcher check; cannot auto-approve plans or expired holds; cannot assign drivers to illegal shifts; cannot send DELAY without Dispatcher decision; cannot bypass template allowlist. DST: `Europe/Stockholm`, run at 04:00/04:15 rather than 02:xx local DST transition; ensure exactly once per local date and market.
- D5: raw GPS must be deleted on trip end immediately, NOT only when `retention` runs next day. For other categories, retention legal review and protected dry-run needed before enabling deletion with real data.
- **D6 dependency**: Free Render services may sleep and are not a reliable 1-minute cron. Scheduler SLA is NOT achieved until owner separately chooses a reliable worker/cron and accepts cost/hosting; D6 explicitly deferred by owner. No paid resources created by this PR.

### Development and acceptance

1. Dev 2 gives exact whitelist, config, endpoint DTO, market-aware job registry and CI tests in a reviewed **D8 approval/implementation PR after owner acceptance**; Dev 1 signs off hold/plan/order concurrency, Dev 3 tests UI alert text and privacy.
2. CI cases: wrong key, unknown job, disabled job, concurrent duplicate tick, market isolation, DST spring/autumn, out-of-shift GPS, completion after offline queue, 15-minute hold expiry, stale stock 15 minutes, quiet-hour mail, 30-minute GPS signal with 60-minute lost threshold, retry/outbox dedupe and no prohibited automatic approval.
3. Do not report full M2–M8 acceptance merely because CLI wrapper or API router exists. In current `main`, `jobs/scheduler.py` and `api/v1/internal.py` still contain stubs; `jobs/hold_expiry.py` has a concrete handler. Enable jobs **incrementally after exact-head integration tests**.
