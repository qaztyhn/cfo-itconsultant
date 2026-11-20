# Open contract questions — DEC-R3-03 / T22

Status: proposed for owner and DB/API contract review; no implementation approval inferred from this file.

## T22-01 — Human planning interaction time

`planning_time_min` is human handling time per committed order, split by the approval path of the current plan. The existing `approved_at - submitted_at` includes queue and source waiting time and is therefore not the approved metric. Which server-side start, pause/resume and end events or persisted columns constitute one interaction? How are repeated planning runs and handoff between Sales and Dispatcher attributed? The implementation must return `null` without those events and keep `order_to_commit_min` separate.

## T22-02 — Trip-specific ETA snapshot at Dispatch

`ops.eta_forecast` persists one order-level `forecast_eta` per version. Its in-memory response may contain trip forecasts, but no durable trip-specific value is available for historical queries. Please approve a precise storage contract (for example, a child row keyed by forecast version and trip ID) and the timestamp ordering used to select the last forecast strictly before each trip's `DISPATCHED` milestone. The first approved forecast must cover every trip; later GPS forecasts must not rewrite the Dispatch snapshot. KPI uses `abs(pre_dispatch_trip_eta - POD.completed_at)` per delivered trip, then median and P90 for the selected period. Missing snapshot or POD means `null`, never an order ETA substituted for a trip ETA.

## T22-03 — Counter commit evidence and override definition

Which persisted event or source field proves that a confirmed order was committed at the store counter? `origin_store_id` and Sales approval alone do not prove physical counter commitment. Define numerator, denominator and event time for `counter_commit_rate`. Also specify which audit actions count as an override for `manual_intervention_rate`, apart from current plan `manual` / `manual_reason_code`. Count each committed order once.

These are contract questions under `docs/09_AI_Coding_Rules.md` §14. Update `docs/05_Database_Design.md`, `docs/06_API_Specification.md`, migration, code, tests and `docs/CHANGELOG.md` together after approval. T27 Step 12 remains NOT VERIFIED until the five actual metrics are checked in Chrome against API/PostgreSQL on T26 seed.
