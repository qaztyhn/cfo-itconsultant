# D7 driver history completeness — technical review proposal

**Status: proposal only.** Dev 1 owns planning/approval/execution safety gates; Dev 2 owns synthetic evidence fixtures and source/import review. `DEC-DEV2-D7-001` approves the 56-day synthetic demo requirement and fail-closed behavior, but does not approve the storage or legal-classification model below. No migration/API/seed is authorized by this file.

## Verified gap

Merged D7 fixtures contain 56 calendar days per driver, duty/driving/rest details, explicit missing coverage, future official-format shifts and 13 scenarios. `hr.driver_duty_log` currently stores only `duty_start`, `duty_end`, aggregate `driving_min`, `source=trip|shift|manual_record` and optional trip/recorder. No row means either rest or missing source data; it cannot prove complete coverage. It cannot represent driving/break segments or synthetic-import provenance. `planning_inputs.official_driver_context()` correctly leaves `history_complete=False`, so T14/T16/M6 remain fail closed. `hr.employee_shift_schedule` is separate official future work assigned by Warehouse Manager, not inferred from duty history or `expected_staff`.

## Proposed evidence model for Dev 1/2 review

1. **Coverage assertion.** One versioned, immutable assertion per employee + market + bounded calendar interval, with source kind, source version/hash, import time, verified by/at, completeness status and explicit missing dates. A day proven off duty is recorded differently from a day with no data. A rolling 56-day window is complete only if each market-local date has trustworthy coverage and the assertion remains valid at the proposed duty date. Never infer completeness from 56 duty rows, zero minutes, or a single aggregate flag without underlying day evidence.
2. **Duty/driving/rest records.** Link imported records to the assertion. Keep duty start/end separate from actual driving segments and breaks/rest periods; preserve timezone-aware instants and original market-local date. Prevent overlapping contradictory records or mark the assertion invalid until reviewed. Do not convert synthetic demo evidence into legally verified tachograph evidence.
3. **Revocation and replay.** A source correction creates a new version and invalidates affected coverage; old versions remain auditable. Same source version/hash replays idempotently, conflicting payloads reject. When the rolling window advances, newly required days must be present before `history_complete` can become true again.
4. **Official shift and vehicle evidence.** The target duty must be inside manager-confirmed `employee_shift_schedule`; past logs do not create future shifts. Check licence class/expiry and vehicle `max_permissible_mass_kg` independently of payload `capacity_kg`. Keep `regulation_561_scope=unknown` unless a qualified, recorded assessment covers the actual market/vehicle/trailer/transport context; a van label or mass alone cannot establish exemption.

**Illustrative persistence alternatives, for review only:** (A) a new coverage table plus daily coverage and drive/break segment children, retaining `hr.driver_duty_log` for aggregate compatibility; (B) a versioned evidence document with validated structured JSON plus a normalized daily coverage index. A is recommended for PostgreSQL constraints, queries and auditability. Either requires a reviewed `docs/05` migration, an import/verification authority contract, and a read DTO for Dev 1's loader. Do not add `synthetic_demo` to the existing `source` enum silently; store provenance separately or explicitly migrate the enum after review. No public driver-history endpoint is implied.

## Proposed loader contract

Dev 2 supplies a validated evidence reader that returns the verified interval, source/version, exact daily coverage, duty/driving/rest segments and explicit unknowns for the target market/date. Dev 1's `official_driver_context()` computes `history_complete` only from that proof and passes separate duty and driving information to the pure engine. ApprovalService must re-read the proof under the fresh five-gate check; execution must reject dispatch if the proof became invalid after planning. The 11-hour uninterrupted daily rest is the approved MVP default; no 9-hour reduction is enabled. Missing shifts, history, licence, mass or applicable scope must produce specific safety reasons rather than silently becoming an available driver.

## PostgreSQL and E2E matrix

- Import the committed synthetic fixtures twice into an isolated database: identical second run creates no duplicate; a changed hash/version is rejected or versioned explicitly; no manager-confirmed shift/attendance is overwritten.
- Validate 56 complete market-local dates, a true off-duty day and a missing day; missing/overlap/correction revokes eligibility. Test rolling day 57 and timezone/DST fall-back and overnight shift boundaries.
- Distinguish duty time from driving/break limits. Test 11h rest and 10h59m, driving over limit, missing official shift, expired/wrong licence, unknown/missing vehicle mass/scope, changed trailer/transport context.
- Planning and T16 approval fail closed when evidence is absent, stale or revoked; dispatch in M6 rechecks the same source/version. No automatic approval or customer commitment from fixtures alone.
- Use real PostgreSQL for version/uniqueness/immutability/rollback constraints and an E2E plan→approve→dispatch path only after the contracts and Dev 1 integration pass.

## Owner / qualified reviewer questions

| Question | Options | Recommendation for review |
|---|---|---|
| Who attests completeness? | WMS/HR feed; Warehouse Manager; transport compliance reviewer | Named qualified verifier plus immutable source reference; a file import alone is not verification. |
| Which sources count for the MVP pilot? | Synthetic only; verified tachograph/HR import | Synthetic only for demo; real-driver eligibility waits for legal/operations source approval. |
| What proves an off-duty day? | Source explicit no-work record; absence of duty row | Require explicit source coverage; absence is unknown. |
| How are driving/break segments obtained? | Source feed; manual attestation | Reviewed typed feed preferred; manual corrections need actor, reason and audit. |
| Who determines Regulation 561 applicability? | Vehicle label; qualified market/transport assessment | Qualified assessment tied to vehicle, trailer and operation; unknown fails closed. |
| How long is a verification valid? | Rolling recheck; fixed expiry | Rolling 56-day recheck plus explicit source expiry/revocation. |

Until owner and Dev 1/2 review resolve these choices, the existing `history_complete=False` guard remains in place. Fixture validation is not production driver-compliance evidence.


## Implementation status (Dev 1, 2026-11-09)

Implemented without any DB/API change: `app/services/driver_history.py` (pure verifier + `DriverEvidenceReader` seam, default `None`) wired into `planning_inputs.official_driver_context` (planning and T16 re-check) and `execution_service._driver_gate` (dispatch/delivery). Evidence document = the "loader contract" above (daily coverage, separate duty/driving segments, rest window for off-duty days, version, source kind, verifier, expiry, revocation). **Owner decisions still required before any real driver can pass:** (1) persistence option A (coverage + daily + segment tables) or B (versioned document + daily index); (2) who attests completeness (named qualified verifier) and the verified-import source; (3) legal/transport assessment of Regulation 561 scope per vehicle/trailer/operation. Until then production has no reader, so history stays unverified and all operations fail closed.
