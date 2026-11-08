# Dev 2 — decisions and handoff after independent tasks

2026-11-08. This is a review checklist, **not approval**, an API baseline or a modification of 05/06.
No sensitive business rule is inferred from CI success. Assumptions/decisions register was reviewed.

## Delivered PRs and review order

The earlier components were delivered as separate incremental PRs with exact-head CI passing.
The owner has since integrated that stack into main (including #74); the roster PR now targets main.
No automatic merge is enabled. Historical PR links below preserve the delivery trail.

| PR | Task |
|---|---|
| [#60](https://github.com/qaztyhn/cfo-itconsultant/pull/60) | Source API-key protection and pending source-contract proposal |
| [#61](https://github.com/qaztyhn/cfo-itconsultant/pull/61) | Read-only stock transport and per-market registry |
| [#62](https://github.com/qaztyhn/cfo-itconsultant/pull/62) | Additive shadow-market onboarding |
| [#63](https://github.com/qaztyhn/cfo-itconsultant/pull/63) | CFO/source reference fixtures; accounts preserved |
| [#64](https://github.com/qaztyhn/cfo-itconsultant/pull/64) | Independently packaged source catalogue and cross-catalogue test |
| [#65](https://github.com/qaztyhn/cfo-itconsultant/pull/65) | ORS/fallback and route cache |
| [#66](https://github.com/qaztyhn/cfo-itconsultant/pull/66) | Route preparation for existing orders and offline CLI |
| [#67](https://github.com/qaztyhn/cfo-itconsultant/pull/67) | GPS loss/expiry and stock freshness jobs |
| [#68](https://github.com/qaztyhn/cfo-itconsultant/pull/68) | SMTP and simulated SMS transports |
| [#69](https://github.com/qaztyhn/cfo-itconsultant/pull/69) | Queued notification delivery, retries/quiet hours/audit |
| [#70](https://github.com/qaztyhn/cfo-itconsultant/pull/70) | Explicit maintenance CLI and GPS simulator |
| Current roster PR, branch `feat/dev2-confirmed-roster-seed` | Explicit warehouse demo roster after migrations 0009/0010; own CI must pass |

The roster fixture is an offline synthetic dataset attributed to the demo Warehouse Manager,
not a production job or a replacement for the schedule API. It neither creates attendance nor
invents driver duty history or vehicle regulation data. Existing schedules/cancellations are retained.

## Decisions needed from the owner

| ID | Decision to finalize | Work held back |
|---|---|---|
| D1 | SRC-Q1–Q10 direction is approved by DEC-SRC-001 / #79. Finalize the explicitly outstanding details in [M1 source contract](../docs/proposals/M1_SOURCE_CONTRACT.md): draft nullability, exact DTO/error paths, zero price, structured requirements, submitted edits/cancellation delivery, endpoint pagination inventory, calendar configuration, empty batch storage and distinct-inventory normalization. These are not approved implementation defaults. | Reviewed 05/06/schema/API contract, complete source API, remaining adapters, stock persistence, ingestion and scenario seed |
| D2 | Approve CSV column/schema/number/date conventions and retry semantics for a file hash whose previous run failed. Do not infer aggregation or skip failed files merely because their hash exists. | CSV fallback adapter/upload |
| D3 | Finalize GPS ingest/live/history/settings response DTOs and limits. Dispatcher-only reading, driver ownership, gps_enabled/on_road guards and privacy requirements are already fixed and must not be weakened. | GPS API and live simulator/PWA integration |
| D4 | Reconcile notification templates/free-text editing in 03/06 with 09's status/ETA-only content rule. No exception for coordinates/GPS/driver names is proposed. Approve exact payload/content constraints and any retry backoff beyond the next tick. | Rendering, enqueue, DELAY draft/send/discard and customer-message integration |
| D5 | Define the retention eligibility anchor and treatment of shared customer/employee records and audit snapshots. Immutable decision/milestone logs must remain immutable; do not assume they can be rewritten to anonymize PII. | Personal-data retention/anonymization |
| D6 | Select staging accounts/projects and EU region; provide secrets through a private environment/secret store. No passwords/API keys in files or PRs and no paid services introduced. | Staging deployment and external monitoring |
| D7 | Supply/review coherent synthetic vehicle max_permissible_mass_kg, regulation_561_scope and driver-history fixtures. Payload capacity is not sufficient evidence for those fields; current unknowns stay fail-closed. | Driver/golden planning scenarios and legal-rule data acceptance |
| D8 | Finalize /internal/tick supported job names, response/error DTO and market-specific versus global scheduling contract. Current operational CLI runs only implemented jobs. | Internal tick endpoint and automatic scheduler wiring |

No decision is requested again for already approved Q12/Q13/Q14, Sales guards, manager-owned
schedules, no automatic approval, no write-back, or dispatcher-only GPS.

## Dependencies requiring a developer handoff, not a new owner decision

- Dev 1: schedule API and attendance generation from the now-migrated confirmed roster. Existing
  generate_attendance still returns 0; the fixture is not proof that capacity integration works.
- Dev 1: PlanningService / ReservationService / ApprovalService and guarded Sales approval before
  end-to-end planning and concurrency acceptance. Technical route cache/preparation is available.
- Dev 1: execution/risk/ETA integration before morning/milestone jobs and closed-order scenario/KPI seeds.
- Dev 1/2: producer-side routing/scope integration after D1. The routing table and immutable-decision
  constraint exist in 0009/0010; source completeness/freshness and API behavior remain separate.
- Dev 3: UI, private GPS banner/consent, PWA offline queue and notifications/operational screens for E2E.
- Contract owners: reviewed CFO/source OpenAPI baselines. CI readiness can be green while comparison
  remains NOT VERIFIED; no baseline was generated from stubs to disguise this gap.
- Dev 3: existing npm dependency audit findings, separate from the infrastructure/seed changes.

No full M1–M9 acceptance is claimed. Exact CI links and commands are in each PR; historical local
checks and limitations are in [DEV2_INDEPENDENT_WORK_REPORT.md](DEV2_INDEPENDENT_WORK_REPORT.md).
