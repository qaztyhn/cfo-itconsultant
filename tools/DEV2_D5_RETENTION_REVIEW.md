# D5 synthetic retention review — 2026-11-08

Run with the backend environment:

```text
python tools/retention_review.py --metadata metadata.json
```

Input is non-PII metadata, not a customer export. `APP_NOW` sets the injected clock. Example:

```json
{"policy_version":"2026-11-08.1","synthetic_only":true,"items":[
  {"category":"customer_contact","anchor":"2026-01-01T00:00:00Z","timezone":"Europe/Stockholm",
   "legal_hold":false,"other_valid_purpose":false,"regulated":false,"terminal":true}
]}
```

The versioned rule register is `backend/app/jobs/retention_policy.py`: 90-day contact/CS/former-staff,
365-day nonfinancial operational order, 24-calendar-month shifts, 30/90-day app/security logs,
30-day staging backup. Tachograph (12 months), driver work records (24 months), qualifying accounting
evidence (through Dec 31 of year seven after fiscal-year end) produce statutory-review outcomes only.
Audit/milestone 24 months is review-only. Raw GPS uses trip/duty workflow, never a 30-day period.

Output is counts only, `dry_run=true`, `deletion_enabled=false`; there is no deletion switch or DB
connection. Unknown anchor/hold/shared purpose/statutory classification prevents an ordinary candidate.
Calendar months and accounting dates use business timezone and actual fiscal-year end, not 30-day months.

## Handoff and limits

- DEC-DEV2-D5-001 implements product policy, not a legal-compliance certificate. No real-data deletion.
- Controller/legal review must supply lawful basis/purpose, holds and true shared-record anchors.
  Extracting these from DB needs reviewed closure/hold/statutory metadata; updated_at is not a closure.
- DB, device/cache and provider backup erasure/restore propagation remain separate tasks. Immutable
  audit/milestone rows are never updated or deleted by this tool. Regulated archives need access controls.
- DSAR one-month and reportable breach 72-hour procedures are organizational workflows, not automatically
  enforced by a numeric retention calculator.
- D6 remains deferred; D8 scheduler remains unapproved. No cloud deployment or automatic purge enabled.

Assumptions: reviewed; DEC-DEV2-D5-001 / DEC-GDPR-001 / D3 override; none new.
