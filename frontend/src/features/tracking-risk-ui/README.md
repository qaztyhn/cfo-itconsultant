# M7 — Isolated Order Tracking & Risk UI

**Scope:** six reusable, display-only React components with local TypeScript view models and synthetic fixtures. These are **not** API DTOs, route handlers, business decisions or backend authorization. They run without an API, store, query cache, customer data, driver personal information or GPS.

## Components and props

All components accept `model: … | null` plus `loadState?: "ready" | "loading" | "error"`, `errorReference?: string | null` (correlation ID **only**) and `className?: string`. A null model or empty collection renders an explicit empty state. A loading state renders an accessible skeleton; an error state renders a generic message (no raw server response).

| Component | Local view model | What it displays |
|---|---|---|
| `RiskSummary` | `RiskSummaryModel` | Committed delivery window; confirmation time if supplied; planned/forecast ETA; backend-supplied reserve consumption, status and provenance |
| `MilestoneTimeline` | `MilestoneTimelineModel` | Six fixed milestone labels: Approved, Start prep, Goods ready, Loaded, Dispatched, Delivered; independent planned/actual/forecast timestamp evidence |
| `VehicleStatusList` | `VehicleStatusModel` | One or more vehicle codes and trip refs, supplied state, per-vehicle timestamps, **supplied overall order ETA** |
| `RiskExplanation` | `RiskExplanationModel` | Backend-generated rule explanation, status, reason codes and provenance; never computes risk |
| `OrderEventLog` | `OrderEventLogModel` | Event time, type, authorized actor **role**, sanitized effect |
| `NotificationHistory` | `NotificationHistoryModel` | Type, channel, status, timestamp; **read-only**, no message content or recipient information |

Import from `./index` once a parent feature is approved to integrate them. No router, Tracking.tsx, AppShell, API client, OpenAPI contract or shared component was modified.

## Evidence/freshness semantics

`TimeDatum = { at: ISO8601-with-offset | null, quality, source?, asOf? }` where `quality` is exactly one of `verified | stale | missing | unknown | unavailable`. UI **never** infers freshness by clock arithmetic, never replaces missing with the current time, and never treats the absence of data as on-track. The parent adapter must explicitly supply freshness and verification. Stale values remain visible only with a **Stale** label.

- Every model carrying times requires a `timeZone` (IANA). A timezone-less timestamp is marked **Unverified timestamp**; invalid time zones are not silently converted to UTC. Times are displayed as `en-GB` with the supplied timezone, never guessed market-local.
- `RiskStatus` is the supplied backend `ON_TRACK | AT_RISK | PREDICTED_LATE | OVERDUE`; the UI never derives it from an ETA, risk color, consumption %, vehicle status, or SLA.
- `Provenance.routeQuality` is an **explicit upstream** `verified_ors | estimated_fallback | unknown`. `estimated_fallback` always prints **Estimated fallback route — not verified ORS**. No silent promotion based on the source name.
- `VehicleStatusList.overallForecastEta` is a separate backend value, **never** computed from per-vehicle times. Visual reserve bars only clip their width to the container; the numeric value is rendered exactly as supplied (including over 100%), with no local threshold or decision.
- Absent milestones remain visibly missing even if adjacent steps have timestamps. There is no automatic transition, notification, acknowledgement, reschedule, timer or action.

## Synthetic fixtures and tests

`fixtures.ts` contains fixed, non-PII examples for on-track, at-risk, predicted-late, missing forecast, stale data, six milestones, multi-vehicle execution, notifications and authorized event history. Samples are **illustrative**, not a source of business rules, live data or permission grants. No coordinates, person names, addresses, contacts or messages are embedded.

Run from `frontend/`:

```sh
npm ci
npm run lint
npm run test
npm run build
```

For the focused suite: `npx vitest run src/features/tracking-risk-ui/tracking-risk-ui.test.tsx`.

Tests cover all six components, explicitly supplied risk categories, missing/stale/unavailable states, missing milestone, multi-vehicle (including FAILED), supplied overall ETA unchanged, fallback provenance, read-only notification controls, synthetic privacy-field injection, semantic tables/regions and load/empty/error states.

## Integration handoff / blockers

1. **Server authorization required:** the presentation components do **not** authorize users. The eventual container must enforce the existing `docs/06` role/location matrix server-side and construct **redacted role-specific view models**; do not pass full order/contact/driver/trip payloads into UI props. Event actor is `actorRole`, not a personal name; event `effect` must be an authorized, PII-free summary. Reject unapproved records before rendering.
2. **API fields are not yet guaranteed:** `GET /orders/{id}` provides latest risk including forecast/planned ETA and reserve consumption; `GET /orders/{id}/timeline` provides selected milestone/ETA/decision/notification events with role filtering. Planned/actual/forecast per milestone, complete multi-vehicle state and verified ORS/fallback provenance may need an approved backend read-model/adapter. Do not invent endpoints, calculate the backend's overall multi-vehicle ETA, or manufacture timestamps.
3. **Notification contract:** `GET /orders/{id}/notifications` and `GET /notifications` are specified but their integration readiness must be checked. There is **no send/edit/discard UI** here, even for draft DELAY. The eventual dispatcher page can use authorized controls outside this module following a separate reviewed scope.
4. **Data freshness:** `quality`, `source`, `asOf` and `routeQuality` must come from trusted upstream provenance. Missing/stale tracking input cannot be promoted to verified by components. No GPS metadata is modeled or displayed. Backend still controls permission to location data.
5. **i18n:** labels in this isolated module are English demonstration copy. Shared i18n bundles are intentionally untouched; the integrating owner should map local labels to approved translation keys as a separate reviewed change.
6. **Isolation:** this PR intentionally does **not** import from unmerged PR #124/#125, shared Tracking.tsx or unimplemented backend service endpoints; it changes nothing outside `frontend/src/features/tracking-risk-ui/`.

Sources: `AGENTS.md`, `docs/03_UI_UX_Specification.md` §5.4 and §2, `docs/06_API_Specification.md` §§5.1–5.5 and 8–10, `docs/09_AI_Coding_Rules.md`, `docs/ASSUMPTIONS.md` (approved D3/D4 privacy and notification constraints). **Assumptions: reviewed; no new business decisions.**
