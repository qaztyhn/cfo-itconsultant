# Dev 1 — D7 evidence and GPS assignment: technical contracts for review (2026-11-09)

Status: **design for Dev 1/Dev 2 review; not implemented.** Behaviour is fixed by DEC-OWNER-20261109 (D7-1…4, G1/G2). Names below are proposals. Until this ships, `history_complete` stays `false`, the real `safety` gate fails closed and GPS reads stay restricted.

## 1. D7 — verified 56-day driver evidence (Dev 2 importer/verifier, Dev 1 reader/gates)

Proposed persistence (migration after 0013):

| Table | Purpose | Key rules |
|---|---|---|
| `hr.driver_evidence_version` | One verified evidence set per driver | `source_kind`, `source_ref`, `content_hash`, `version`, `verified_by` (named qualified transport/compliance reviewer), `verified_at`, `status` (submitted/verified/revoked), `revoked_at/reason`; `verified_by <> imported_by`; immutable after verification (corrections = new version). |
| `hr.driver_evidence_day` | One row per **market-local date** in the covered window | `evidence_version_id`, `local_date`, `day_kind` (`duty`/`off_duty`/`unknown`), duty/driving/break/rest minutes and segment JSON; `UNIQUE(version, local_date)`. `off_duty` is an explicit verified fact; a missing row is *unknown*. |

Reader contract (`planning_inputs.official_driver_context()`):
1. Pick the latest `verified`, non-revoked version whose reviewer/source is still qualified.
2. Require a row for **each** of the 56 market-local dates ending at the planning/approval/dispatch instant (market IANA timezone, DST-safe date arithmetic); any `unknown` or missing date ⇒ `history_complete=false`.
3. Duty, driving, breaks and daily rest are separate inputs; default **11 h uninterrupted daily rest**, no 9 h exception; future shifts come only from Manager-approved `hr.employee_shift_schedule`, never from history.
4. Re-evaluated at planning, five-gate approval (`approval_recheck.five_gate_recheck`) and dispatch (`execution_service._driver_gate`); revocation takes effect immediately.
5. Missing/unknown licence class or expiry, vehicle `max_permissible_mass_kg`, `regulation_561_scope`, or trailer/transport context ⇒ reject approvable planning and dispatch (already fail-closed today).
6. Synthetic fixtures (`DEC-DEV2-D7-001`) are flagged `source_kind='synthetic_demo'` and can never set `history_complete=true` for a real worker.

Open for Dev 2: importer format, hash algorithm, how the reviewer identity is authenticated.

## 2. G1/G2 — one active primary Dispatcher per trip (persistence for Dev 2's GPS service)

Proposed `ops.trip_dispatcher_assignment`:

- `trip_id`, `dispatcher_user_id`, `assigned_by` (Admin or market-granted supervisor), `assigned_at`, `valid_from`, `valid_to` (explicit expiry), `revoked_at/by/reason`, `handover_from_id` (previous assignment).
- Partial unique index: one **active primary** assignment per trip (`WHERE revoked_at IS NULL`); handover = revoke + insert in one transaction.
- Supervisor authority comes from an explicit market-granted record (same pattern as `ref.stock_admin_grant`), never from the Dispatcher role itself; no role-wide backfill, no market-wide Dispatcher fallback.
- Every create/expire/revoke/handover audited in the same transaction (`audit.decision_log`).

Read-time authorization (Dev 2's GPS service calls one function): allowed only if the caller is the assignee, assignment not expired/revoked, `trip.status='on_road'` and the driver is within official active duty now. Effective end = earliest of expiry/revocation, trip terminal, duty end. Terminal transaction in `execution_service` already deletes raw `ops.vehicle_position` for the trip (G4); Dev 2 owns the cleanup backstop and device queue deletion.

## 3. Dependencies

Dev 2: D7 importer/verifier, GPS read endpoint and cleanup, outbox (N4). Owner: confirm who issues the first stock/GPS supervisor grants and the qualified-reviewer roster. No legal/DPIA sign-off is implied.
