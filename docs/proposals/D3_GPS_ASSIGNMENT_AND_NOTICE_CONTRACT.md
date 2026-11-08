# D3 GPS authorization and individual notice — review proposal

**Status: proposed, not approved.** Dev 1 owns trip execution; Dev 2 owns GPS ingestion/read service; privacy/legal must review use with real employees. This document does not authorize a migration, API route, GPS read, or real-worker collection. It follows `DEC-DEV2-D3-001`, `docs/04` §9 and `docs/05` §6; Draft PR #137 continues to return 403 for every GPS read.

## Existing boundary

- Only a Dispatcher assigned to the **specific trip** may read live/history positions while the driver is in an official shift. Dispatcher market membership alone is insufficient.
- The present `ref.compliance_record` with approved `GPS_NOTICE` is market-level document evidence. It cannot establish that a particular driver received the relevant notice.
- A driver may upload device points only during the assigned `on_road` trip and official duty. Raw points are purged when trip or duty ends, whichever occurs first. The cleanup job is a backstop; the terminal event must purge in its transaction.
- `gps.retention_days=30` is a legacy config value, not a permission to retain raw GPS for 30 days. Simulator points must have trusted producer provenance, never a client-supplied `source` label alone.

## Proposed persisted authorization (logical model only)

An assignment record would bind `trip_id` to a **Dispatcher employee**, not just to a market/role. Proposed fields for review: `assigned_by`, `assigned_at`, `valid_from`, `valid_to`, `revoked_by`, `revoked_at`, `reason`, `version`, and audit reference. The record is append-only or versioned; revocation closes its validity rather than erasing history. Every change writes an approved decision-log action in the same transaction. The owner must first decide who can assign and whether multiple Dispatchers may be assigned concurrently.

The read service would check, at request time, all of: authenticated active Dispatcher role; actor's employee and market; a currently effective assignment to that exact trip; trip still `on_road`; driver still within an official duty interval; market GPS enabled; and no terminal/duty purge. `GET /gps/live` would query only assigned trip IDs, not all trips in the market. `GET /trips/{id}/positions` would apply the same filter before pagination. Outside-scope trip identity should remain concealed under the existing 404/403 policy. Assignment changes and terminal transitions need row locking or an equivalent transaction boundary so a revoked assignment cannot race a read authorization decision.

**Illustrative DDL choice for review:** a versioned `ops.trip_dispatcher_assignment` keyed by `(trip_id, dispatcher_employee_id, version)` with foreign keys to trip and employee, validity interval constraints and an index on `(dispatcher_employee_id, valid_from, valid_to)`. If only one active Dispatcher per trip is approved, add a PostgreSQL overlap/exclusion constraint; if several are permitted, constrain overlap only per `(trip, employee)`. Exact names, actions, migration/backfill and authorization endpoints require Dev 1/2 review and owner answers below. No implicit backfill from market-wide Dispatcher access.

## Proposed individual notice evidence (logical model only)

Bind a driver employee to the **version** of the approved market `GPS_NOTICE`, with delivery/acknowledgment time, method, issuer, document reference/hash, market, and revocation/supersession status. The evidence should reference a notice, not copy private employment documents or location data into audit/logs. A changed notice requires new evidence according to the owner-approved re-notice rule. Server collection should fail closed if the relevant individual evidence or privacy/legal pilot gate is missing; a market-level notice by itself is not enough for real employee tracking. Synthetic-only demo remains distinguishable from real-worker data.

**Illustrative DDL choice for review:** `hr.driver_gps_notice_evidence(employee_id, market_id, notice_record_id, notice_version, informed_at, acknowledged_at, method, recorded_by, source_ref_hash, status, created_at)` with a unique active binding per employee/notice version. Whether acknowledgment is legally required, or reliable delivery evidence suffices, is an owner/privacy/legal question. No new column or endpoint is approved by this sketch.

## Trip lifecycle, load and device contract

- Dev 1's execution transaction should change trip status and call Dev 2's `purge_trip_on_terminal(session, trip_id)` before commit. Failure rolls back both. Shift-end cleanup may run separately but must reject subsequent offline replay. Multi-vehicle orders purge each terminal trip independently. Duty/tachograph history remains.
- PR #137's exact timestamp lookup and narrow cadence probes use the existing `(trip_id, recorded_at DESC)` index, avoiding materializing all historical positions on each upload. A maximum batch count/size and supported offline span still require approval; reject oversized batches atomically without echoing coordinates.
- Simulator use should require a separate authenticated producer identity and explicit synthetic provenance. The driver endpoint accepts only device reports. Neither request body nor a market flag authenticates simulator origin.
- Migrate or deprecate `gps.retention_days` only with a reviewed settings/API change; event-based deletion remains authoritative. Backup/device-queue deletion requires separate operational evidence.

## PostgreSQL and E2E acceptance matrix

1. Assigned Dispatcher sees only that trip during duty; unassigned, revoked, expired, wrong-market, admin, driver, Sales and CS see no coordinates. Verify concurrent revocation/read and terminal/read races.
2. Assignment create/revoke has authorized actor, scope, version, audit and rollback; no market-role backfill grants access.
3. Individual notice absent, wrong version or revoked blocks **real-worker** upload; approved market notice alone is insufficient. Evidence reference does not leak through GPS responses/logs.
4. Terminal completion, failure and cancellation purge points in the same PostgreSQL transaction. Rollback restores both trip and points; concurrent upload waits then rejects. Overnight shift expiry purges first, including DST boundary cases.
5. Large history, exact replay, conflicting duplicate timestamp, nearest-point cadence, oversized batch and old offline replay preserve atomicity and omit coordinates from errors.
6. Source `simulator` spoof from driver is rejected; trusted simulator data remains segregated. No GPS-derived ETA without verified remaining-route evidence.

## Owner and privacy/legal decisions required

| Question | Options | Recommendation for review |
|---|---|---|
| Who assigns a Dispatcher to a trip? | Admin; Dispatcher supervisor; existing dispatcher of the order | Named supervisor/admin grant with market scope and audited revocation; do not infer from role. |
| How many Dispatchers may be active on one trip? | One; several explicitly assigned | Several only if operational handover requires it; each must be individually recorded. |
| When does assignment expire? | Fixed interval; trip/duty end | Earliest of explicit expiry, revocation, trip terminal or duty end. |
| What proves an individual driver was informed? | Delivery record; acknowledgment | Privacy/legal to decide; bind evidence to approved notice version and block real-worker collection until present. |
| Who authorizes real-worker pilot use? | Market admin; privacy/legal sign-off | Require recorded DPIA/notice review and owner/privacy/legal sign-off before real data. |
| What GPS upload limit applies? | Point count; byte cap; shift-span cap | Bound by one active duty and approved 30-minute cadence, with a documented atomic limit. |
| How is simulator authenticated? | Separate service credential; isolated demo process | Separate credential/provenance, never a driver-supplied source field. |
| How is `retention_days` retired? | Remove field; deprecated ignored field | Explicit config/API migration; no 30-day raw GPS fallback. |

Until these answers and the corresponding `05`/`06`/`09` changes, migration, tests and review exist, PR #137 remains Draft and its GPS read endpoints remain fail closed.
