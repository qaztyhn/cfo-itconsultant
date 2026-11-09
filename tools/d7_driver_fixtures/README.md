# D7 — Synthetic Driver & Vehicle Golden Fixtures

**Scope:** Offline, deterministic, synthetic inputs for Swedish (`SE`) driver, vehicle, and schedule-gate regression tests. **Not** legal advice, a production seed, an authoritative API/DB schema, or permission to import/update official schedules. No new runtime dependency, database writes, network calls, or clock-based randomness.

**Approved provenance:** [`DEC-DEV2-D7-001`](../../docs/ASSUMPTIONS.md) (D7-A–E, approved 2026-11-08); [`DEC-DRIVER-001`](../../docs/ASSUMPTIONS.md) (11 continuous hours default, 9-hour reduction disabled); [`DEC-SHIFTS-001`](../../docs/ASSUMPTIONS.md) (one manager-approved shift per person/day, may cross midnight, absent shift is not availability). Exact source references and future integration ownership remain with Dev 1/Dev 2. Schema and seed references examined: `docs/05_Database_Design.md`, `backend/app/domain/models/{hr,ref}.py`, `backend/alembic/versions/0009_*`, `backend/app/seed/{fleet,workforce,roster}.py`, `backend/app/engine/{delivery,types}.py`.

## Contents

| File | Local meaning |
|---|---|
| `generate.py` | Purely offline, stdlib deterministic generator; `--write` or `--check` |
| `validate.py` | Structural, interval and reference validation; **not** driving-law evaluation |
| `test_fixtures.py` | 20+ local tests including deliberate corruption tests |
| `fixtures/manifest.json` | Version, market, coverage window, counts and files |
| `fixtures/vehicles.json` | 9 synthetic vehicles, separately provided payload / permitted mass / scope |
| `fixtures/drivers.json` | 10 synthetic driver identities and licence validities |
| `fixtures/history_week_01.json` … `history_week_08.json` | 56 calendar days × 10 drivers = **560 coverage records**, including a missing-data marker |
| `fixtures/future_shifts.json` | 51 synthetic official-format future shift **examples**, not DB-approved shifts |
| `fixtures/scenarios.json` | 13 golden scenarios and expected *gate-level* dispositions |
| `fixtures/verification.json` | Explicit revocable, hash-matched synthetic-only attestation with reviewer identifier, expiry and legal_verified=false; never a regulatory certification |

**Fixed window:** history `2026-09-09` through `2026-11-03` inclusive (56 days before the approved demo clock `2026-11-04T10:05:00+01:00`), future shifts `2026-11-09`–`2026-11-14`; all timestamps are ISO 8601 with an explicit offset in `Europe/Stockholm`. One recorded night crosses the DST fall-back on **2026-10-25**: `00:30+02:00` through `04:30+01:00` is **five elapsed hours**, not four. One scheduled future shift crosses midnight `2026-11-14T20:00+01:00` → `2026-11-15T04:00+01:00`.

## Regenerate and validate

Run from the repository root (Python **3.12+**, stdlib; no installed backend needed):

```sh
python tools/d7_driver_fixtures/generate.py --check
python tools/d7_driver_fixtures/validate.py
python -m unittest discover -s tools/d7_driver_fixtures -p 'test_*.py' -v
```

`--check` does **not write**. `--write` regenerates only under `tools/d7_driver_fixtures/fixtures/` and replaces those synthetic files, never a database. The output JSON uses UTF-8, sorted keys and stable 2-space indentation. No random seed or current time dependency; the fixed date anchor is part of the **test fixture**, not a market business rule. Generated files are intentionally committed to permit code review and golden-file diffs.

## Local JSON schemas (not CFO DB/API contracts)

Every JSON document has `schema_version: "d7.synthetic.v1"`, `source: "synthetic_demo"`; driver/history/scenario documents use `kind`, `records: []`; `verification.json` is a signed-inputs metadata record, not a duty or entitlement record. `manifest.json` has `market`, `timezone`, `history_start`, `history_end`, `history_days_per_driver`, `future_start`, `vehicle_count`, `driver_count`, `files`, and `offline_only: true`.

- `vehicles.records[]`: `vehicle_code` (stable demo fleet code), `market`, `warehouse_code`, `vehicle_type` (descriptive ONLY), `capacity_kg` (**payload**, positive integer), `max_permissible_mass_kg` (**gross/permissible mass**, independently provided positive integer, strictly greater than payload), `required_licence` (`B|C|CE`), `regulation_561_scope` (`in_scope|out_of_scope|unknown`), nullable `scope_evidence` (synthetic assertion, **not legal proof**), `transport_context` (`country`, `operation`, `trailer_attached`, nullable `trailer_max_permissible_mass_kg`, nullable `exception_claim`), and `scope_note`. Do not convert `unknown` to `out_of_scope`, and do not infer legal scope from van/truck type.
- `drivers.records[]`: `driver_code` (`D01`–`D10`), `employee_no` (matches existing demo naming pattern, not a real identity), `market`, `warehouse_code`, `licence_class`, `licence_expires_on`, `adr`. D10's licence is intentionally expired.
- `history_week_XX.records[]`: `driver_code`, `work_date`, `coverage_status` (`complete|missing`), nullable `duty_start`, `duty_end`, nullable `driving_min`, `driving_intervals` (each `{start,end,elapsed_min}`), nullable `rest_before_duty` (`{start,end,elapsed_min}`), boolean `verified_off_duty`, nullable `verified_rest_window` (`{start,end,elapsed_min}`). Time durations count **elapsed UTC time**. A complete off-day includes a verified rest window; a **missing** day has `driving_min: null`, `verified_off_duty: false`, no assumed rest. For the first in-window duty and the first duty following a missing interval, `rest_before_duty: null` means **not proven**, never zero or approval. `rest_before_duty` describes only the recorded gap to the preceding known duty; it does not certify regulatory rest. This is **fixture evidence**, not a complete tachograph record.
- `future_shifts.records[]`: `driver_code`, `warehouse_code`, `work_date` (local date of shift start), `status: scheduled`, `shift_start`, `shift_end`, `assigned_by_employee_no` (synthetic existing demo manager code), `authority_status: synthetic_offline_not_db_confirmed`, `record_kind: official_shift_fixture`. Each driver has at most one future shift per local start date. These rows mimic manager-scheduled shifts but have **not** been approved/inserted by a real Warehouse Manager; until validated/committed by the authorized scheduling workflow, they are **not** official operational availability.
- `scenarios.records[]`: `scenario_id`, `driver_code`, `vehicle_code`, `proposed_duty_start`, `proposed_duty_end`, `proposed_driving_min`, `expected_outcome` (`candidate_for_planner_review|block_automatic_approval|unknown_fail_closed|historical_evidence_only`), `expected_reason_codes` (non-binding golden signals), `input_overrides` (scenario-local overlay; never mutate base fixtures; `additional_duty` must include `supersedes_verified_off_duty_on` to invalidate contradictory baseline off-duty evidence), and `legal_compliance_certified: false`. A **candidate** is merely an input suitable for subsequent safety-gate review, **never** an automatically approvable plan.

These types and reason signals are **fixture-local mappings**, not additions to `05/06`, SQL tables, enum values, or REST schemas. The real engine may have a different reason-code mapping; Dev 1/2 must reconcile it explicitly.

## Scenario catalogue / expected business outcomes

| Scenario | Expected downstream outcome | Signal / handoff |
|---|---|---|
| `valid_candidate` | Candidate for *further* planning checks, not automatically approved | Approved shift fixture + known scope + complete 56-day input |
| `insufficient_rest` | **Block** | Added Sunday duty ends 23:00, next start Monday 07:00: 8h < approved 11h; 9h exception disabled |
| `missing_history` | **Unknown / fail closed** | D07 missing 2026-10-30, `DRIVER_HISTORY_MISSING` |
| `off_shift_driver` | **Block** | Trip outside synthetic future shift |
| `expired_licence` | **Block** | D10 licence expires before scenario date |
| `unknown_vehicle_scope` | **Unknown / fail closed** | `regulation_561_scope=unknown`, even if van |
| `missing_vehicle_mass` | **Unknown / fail closed** | Scenario overlay sets gross permissible mass to explicit `null` |
| `driving_day_over_limit` | **Block** | 550 proposed driving minutes exceeds documented 540-minute normal limit; 660-minute duty separately exceeds default duty bound, so both signals expected; does NOT implement legal exceptions |
| `overnight_duty` | Candidate for *further* checks | D06 official-format shift and duty cross midnight; do not presume 24/7 |
| `missing_shift` | **Unknown / fail closed** | No future shift on Sunday 2026-11-15 |
| `transport_context_changed` | **Unknown / fail closed** | A changed international/trailer context has an unverified scope, not a new legal classification |
| `licence_data_missing` | **Unknown / fail closed** | Explicit `null` licence class in a scenario overlay |
| `dst_overnight_history` | Historical evidence only, not approval | D09 duty across Stockholm fall-back, five elapsed hours; fold encoded in offsets |

## Handoff / unresolved integration contracts

1. **Review before mapping:** Dev 1/2 map `vehicle_code` to `ref.vehicle.code`; `employee_no` to `hr.employee.employee_no`/`hr.driver_staff.employee_id`; `future_shifts` to manager-authorized `hr.employee_shift_schedule`; duty rows to `hr.driver_duty_log`. Do not import JSON directly or silently overwrite previously confirmed shifts/attendance. No database ID assignments in these fixtures.
2. **Missing structural fields:** `hr.driver_duty_log` stores `duty_start`, `duty_end`, `driving_min`, source but not per-driving interval, verified rest window, completeness, or 56-day coverage evidence. Existing `hr.employee_shift_schedule` requires manager actor/assignment at insert time. **No schema change in D7.** Any DTO/migration/ledger for completeness, break history, scope evidence, trailer context or manager authorization requires Dev 1/2 reviewed contract changes and real PostgreSQL tests.
3. **Legal decision boundary:** 561/2006 scope is contextual; synthetic `in_scope`/`out_of_scope` labels are not a legal determination, especially under trailer/transport changes. Weekly/fortnight driving, breaks and exemptions require validated authoritative history and approved country-specific logic. Unknown ⇒ fail closed. 11h daily rest default only; no reduced 9h rest. Nothing here certifies legal compliance.
4. **No coupling:** This tool neither imports nor calls engine, existing seeds, API, jobs or database. Dev 1/2 should implement adapter and integration regression tests in their authorized workstream after review; this PR does not modify them.

**Assumptions:** reviewed `DEC-DEV2-D7-001`, `DEC-DRIVER-001`, `DEC-SHIFTS-001`; no new business assumption or decision.

## Demo-only verification boundary (PR #206 handoff)

The attestation records the canonical UTF-8 SHA-256 digest for `manifest.json`, `drivers.json`, and all eight history weeks. `verified_by` identifies a **synthetic fixture reviewer**, not an employer or official legal verifier. It is valid only for the approved frozen demo clock and expires on 2026-11-05. Missing/mismatched files, revoked or expired attestation and unknown duty remain fail-closed. The existing authorized warehouse-manager shift scheduling workflow remains the only source of official DB shift assignments: these JSON files **must not** be imported as authorized shifts, nor should `legal_verified=false` be treated as a passed production compliance gate.

The D7 fixture is designed for an evidence target of **2026-11-04**. Applying the same history snapshot to a different target date (such as 2026-11-10) is not valid; the reader must return unknown rather than silently slide the 56-day window.
