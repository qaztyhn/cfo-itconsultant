# Dev 2 — decisions and handoff after independent tasks

## Current T07 contract status — 2026-11-08, main 361bd73

This section supersedes earlier stock-persistence and pending-PR statements below.
PRs #105, #106, #111 and T14 #117 are merged. T07 runner/reference/order PRs #115,
#116 and #118 were merged by the owner. Scheduler #119 and stock-readiness #121
remain review work; no automatic merge is enabled.

DEC-CFO-STOCK-SCOPE-001 requires an explicitly fixed CFO SKU scope before ingestion;
confirmed mappings and the Source batch cannot define that scope implicitly.
DEC-CFO-STOCK-INDEPENDENCE-001 requires verified physical independence before summing
SKUs. Scope/evidence storage, versions, effectivity and authority are not yet contracted.
PR #120 is a pure-normalizer proposal, not an approved persistence repository.

Accordingly the earlier whole-market stock replacement is withdrawn. Production
scheduler runs customers, products, orders, inbound and fleet only. Explicit stock
CLI diagnostics record a failed run/reject (STOCK_SCOPE_NOT_CONFIGURED), preserve all
cached stock and commitments, and never advance the checkpoint. A complete empty
Source batch also cannot clear CFO stock without the scoped contract. Stock usability
returns false; this is a dependency gate, not implemented availability proof.

T14 now has a real suggest_replan core. Its default loader reads the existing CFO
order/version; wiring it directly to a newer Source DTO would plan the old approved
order. A reviewed fresh-source input adapter and risk integration remain necessary.
The trusted callback tests prove transaction guards, not a real T14/T16 E2E flow.
No edits to planning_service.py, approval_service.py or api/v1/planning.py are made.

Verification below with older commits/counts is historical. Final exact-head checks
are recorded in PR #121. No new business decision, schema, public API or config key
is introduced. Assumptions: reviewed; existing approved stock-scope/independence rules.

## Historical implementation notes (superseded where stated above)

2026-11-08. This is a review checklist, **not approval**, an API baseline or a modification of 05/06.
No sensitive business rule is inferred from CI success. Assumptions/decisions register was reviewed.

## Current decision register and T07 handoff — 2026-11-08

This section supersedes the historical D1–D8 questions below. Consult `docs/ASSUMPTIONS.md` and
the approved decision documents; historical proposal wording does not reopen an approved decision.

| Item | Current state |
|---|---|
| D1 | Approved DEC-SRC-D1-001; Q10 pool direction **superseded** by DEC-SRC-Q10-SKU-001. #105/#111 both merged, fixed SKU units and 503 STOCK_UNAVAILABLE. #106 current reconciled OpenAPI candidate still needs review. |
| D2 | Approved encoding/schema/hash/retry policy. Offline bundle validation exists; CSV upload/durable retry repository still needs the reviewed migration/index and IT-only API handoff. |
| D3 | Approved 30-minute, on-road + official-shift GPS and immediate purge; missing Dispatcher-trip assignment/terminal/PWA integration remains an engineering dependency. |
| D4 | Approved server templates/allowlist, no free text, test-only transports; enqueue/execution/risk integration is separate. No owner-approved 5/15-minute retry schedule. |
| D5 | Approved category retention policy; production eligibility/legal-hold classification and legal review remain separate. No immutable audit rewrite or blanket GDPR claim. |
| D6 | Explicitly deferred by owner; no cloud deployment. |
| D7 | Approved synthetic driver/vehicle policy; completeness/provenance/official-duty schema handoffs still required. |
| D8 | Expanded tick/jobs/cadence proposal remains unapproved. T07 implements only the existing market sync interval, with an explicitly started ingest worker. |

T07 review stack: #115 → #116 → #118 → #119 → `feat/t07-stock-ingestion` follow-up. It does not
change `planning_service.py`, `approval_service.py` or `api/v1/planning.py`. Real replan/risk,
authorized Sync & check/initial CFO order creation, source staging, system cancellation transitions
and consuming latest-stock-run availability in approval are Dev 1/2 engineering handoffs, not
requests to choose new business rules. Inbound/fleet deletion and per-record source provenance
also need reviewed schema/source handoffs. See [T07_INGESTION_HANDOFF.md](T07_INGESTION_HANDOFF.md).

Stock currently fails closed for unconfirmed SKU or unverified multi-SKU/global aggregation,
as in merged #111. Skipping rows or adding ambiguous inventories is not implemented or inferred
from CI. Any proposed alternative needs an explicit approved rule; valid complete mapped batches
can be tested without choosing that alternative. Full T07/M2/E2E is not claimed complete while
the listed production handoffs remain outstanding.

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
| [#82](https://github.com/qaztyhn/cfo-itconsultant/pull/82) | Explicit warehouse demo roster after migrations 0009/0010; exact-head CI tracked in PR |

The roster fixture is an offline synthetic dataset attributed to the demo Warehouse Manager,
not a production job or a replacement for the schedule API. It neither creates attendance nor
invents driver duty history or vehicle regulation data. Existing schedules/cancellations are retained.

## Historical questions — superseded by the current register above

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
