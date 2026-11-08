# D5 — Numeric GDPR-aware retention proposal for Swedish CFO pilot

**Prepared:** 2026-11-08. **Status:** numerical policy PROPOSED FOR OWNER AND LEGAL/PRIVACY REVIEW, NOT OWNER-APPROVED RETENTION PERIODS. Owner has approved the GDPR-by-design objective in DEC-GDPR-001 (see PR #86), **not** these arbitrary deadlines as lawful. Pilot staging uses only entirely synthetic records. Do not run deletion on real data from this proposal.

## Policy table

| category / where | default | retention anchor | action / exception | authority |
|---|---|---|---|---|
| Raw driver GPS, `ops.vehicle_position` | **30 calendar days** | terminal trip `completed_at/cancelled_at` | delete raw positions; live journey GPS only; no worker tracking outside `on_road`; no deadline for trip with no terminal date until investigated; operational default requiring necessity test | internal proposal, **NOT a GDPR fixed period** |
| Customer notification details and CS contact notes | **90 calendar days** | customer case resolved / last relevant order closed | remove PII in free text, recipient and message content; retain minimal coded evidence if needed; legal hold | internal proposal, NOT statute |
| Customer contact data and mutable address/contact snapshots used solely for delivery | **90 calendar days** | last associated order terminal and no open case/active customer purpose | delete/anonymize operational copy; keep purpose-separated financial copies when legally required; shared customer safety | internal proposal, NOT statute |
| Operational orders, route, stock/prep/trip schedule snapshots (excluding mandatory finance records) | **365 calendar days** | `DELIVERED`/`CANCELLED` + close all active cases | delete/anonymize personal fields and transient details in a reviewed process; retain aggregated nonidentifying metrics. Never treat `FAILED` awaiting replan as terminal | internal proposal, NOT statute |
| Employee non-statutory contact/account data | **90 calendar days** | termination AND no active employment/claims/permissions/assigned jobs | disable login immediately at termination; anonymize after 90 days only where no other basis applies | internal proposal, NOT statute |
| Warehouse staff schedule/attendance operational records not otherwise legally prescribed | **24 calendar months** | end of shift / duty period | reviewed HR/collective-bargaining exception; avoid applying this as a blanket legal requirement for all personnel | internal conservative proposal; verify Swedish labour law |
| Driver tachograph records where Regulation (EU) 165/2014 applies | **at least 12 calendar months** | date of record/use | retain longer if another actual duty applies; restrict access | EU Commission: Article 33(2) of Regulation 165/2014, as described in road transport driving/rest guidance |
| Driver regulated working time records where Directive 2002/15/EC applies | **at least 24 calendar months** | end of recorded working time | protect statutory evidence; longer only where justified | Directive 2002/15/EC Article 9(b), EU Commission guidance |
| Driving history **56 days** | **required LOOKBACK for planning / test fixture**, *not a deletion deadline* | planning evaluation date | Dev 2 synthetic seed includes ≥56 days; regulated tachograph/working-time retention remains 12/24 months as above | EU Commission tachograph roadside lookback; **not** a company retention period |
| Accounting information / vouchers for which Swedish bookkeeping retention truly applies | **through 31 December of the 7th calendar year after the calendar year in which the financial year ended** | fiscal year end (NOT order delivered date) | preserve compliant accounting archive and required PII only; restrict it from operations; verify actual document qualifies as accounting information | Sweden Bookkeeping Act 1999:1078 chapter 7 section 2; Swedish Bokföringsnämnden |
| Technical app/debug logs | **30 calendar days** | event time | prune/no raw name, email, phone, address, GPS or auth secrets | internal proposal |
| Access and security logs | **90 calendar days** | event time | restricted audit trail, IP may be personal data; extend with documented incident hold | internal proposal |
| Decision/audit metadata, `audit.decision_log`, `ops.milestone_event` | **24 months tentative review window for non-statutory fields** | terminal order/case | **DO NOT UPDATE/DELETE immutable audit tables to enforce 24 months**. Engineer PII-minimal entries from the start. A separate lawful archive/retention design needs legal review, migration/consent and immutable-history guarantees before automated lifecycle; specific statutory evidence may require longer | internal proposal / unresolved technical conflict |
| Controlled staging backups | **30 days maximum** | backup snapshot creation | encrypted and access-limited; may need shorter; daily secure exports/manual restoration tests if Supabase Free; treat actual provider retention separately | internal proposal (Supabase Free has no managed daily backups) |
| DSAR privacy rights requests | **one calendar month normally**; **up to two additional months** if permitted and properly notified | validated receipt/request timing subject to lawful identity verification | triage within **7 days** is only internal SLA; track legal deadlines and exceptions | GDPR Art 12(3), EDPB |
| Personal data breach to regulator | **72 hours where reporting threshold met** | controller awareness | risk assessment; document unreported events; inform individuals when high risk as applicable | GDPR Art 33 and Swedish IMY |

**Example:** For an accounting fiscal year ending **2026-12-31**, applicable accounting documents must be kept **through 2033-12-31** under the Swedish rule, not merely 7×365 days from individual order closure. For a non-calendar fiscal year, calculate from the *calendar year in which the fiscal year ended*. Never apply this 7-year rule blindly to all CFO operational notes or GPS.

## D5 implementation contract for Dev 2 / Dev 1

1. Create a reviewed retention-policy register with `category`, `purpose`, `lawful_basis`, `legal_source`, `retention_value`, `retention_unit=calendar_days|calendar_months|fiscal_year_calendar_end`, `anchor`, `action`, `is_statutory`, `legal_hold`, `reviewed_by`, `reviewed_at`, `version` and fallback `policy_missing`.
2. **No destructive `retention.run()` on real records** until that per-category policy is explicitly reviewed and a DDL/API implementation PR includes dry-run, permissions and regression tests. Dry-run should report counts and projected dates without PII. A policy missing/unknown => alert for review; do not fabricate a "GDPR-compliant" deadline.
3. Keep `ops.customer_order` and financial evidence distinct. For shared customer/employee rows, inspect *all* open orders/assignments/legal holds before removing identifying data. Maintain FK consistency and immutable events; consider crypto-erasure of separate identifying mappings as reviewed, not hand-updating immutable logs.
4. Data protection by design: purpose/retention in privacy notice + ROPA; verified DSAR intake and status; access controls to GPS and HR, privacy incident process, DPA + subprocessor/EEA-transfer review; no personal data in staging until legal/privacy approval. Pseudonymous stable IDs can remain personal data.
5. Joint Dev 1/2 tests: expiry boundary exactly +30/+90/+365 calendar days, month/year/fiscal-year boundaries, leap year, holidays/DST where relevant, legal hold, shared customer referenced by open order, failed/retried job, role scope, GDPR rights restrictions, backup expiry, audit immutable no-PII payload, export without unintended personal fields, synthetic vs real-data flag.
6. After owner confirms actual numeric policy and legal reviewer accepts rationale, update `docs/ASSUMPTIONS.md` with separate approved retention ID and amend canonical `04/05/06/09` + changelog. **Current PR only proposes figures.**

## Official sources (verified 2026-11-08)

- Swedish IMY storage limits: https://www.imy.se/en/frequently-asked-questions/how-long-can-we-keep-personal-data/
- Swedish Bokföringsnämnden accounting archiving: https://www.bfn.se/fragor-och-svar/arkivering/
- Swedish Bookkeeping Act 1999:1078 (7 kap. 2 §): https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/bokforingslag-19991078_sfs-1999-1078/
- European Commission driver working time / tachograph retention: https://transport.ec.europa.eu/transport-modes/road/mobility-package-i/driving-rest-times_en
- European Commission 56-day roadside tachograph lookback: https://transport.ec.europa.eu/transport-modes/road/mobility-package-i/tachographs/questions-and-answers-tachograph-provisions-mobility-package-1_en
- EDPB DSAR deadlines: https://www.edpb.europa.eu/contact/frequently-asked-questions_en
- IMY breach notification: https://www.imy.se/en/organisations/forms-and-e-services/notification-of-a-personal-data-breach/
