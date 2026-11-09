# Warehouse Prep Queue (M6) — PR 1: read-only

Screen: `frontend/src/features/warehouse/PrepQueue.tsx` (route `/warehouse/prep`, warehouse role only).
Spec: `docs/03_UI_UX_Specification.md` §5.6, `docs/06_API_Specification.md` Appendix A and §8, US-WH-02, US-WH-03 (removed), US-WH-04.

## Scope of this PR

Read-only: capacity card, "Orders to prepare" table, loading / empty / error / permission-denied states, 20 s polling.
No state-changing action exists in this PR (no Start prep, Pause, Resume, Goods ready, Mark loaded, exception cards). Those come in the next PRs.

## Files

| File | Purpose |
|---|---|
| `types.ts` | Hand-written types for Appendix A (DEPENDENCY, see below) |
| `api.ts` | `GET /warehouses/{id}/prep-queue?date=`, strict response parser (a wrong payload becomes an error state) |
| `usePrepQueue.ts` | TanStack Query hook, 20 s poll, stops on 401/403/404, no placeholder data |
| `useWarehouseSelection.ts`, `timezone.ts`, `useToday.ts` | Which warehouse and which "today" to show. `useToday` keeps the date in state per warehouse time zone and re-checks every minute and when the tab becomes visible, so the queue date rolls over at local midnight and the previous day's data is not shown (no placeholder data). |
| `format.ts`, `queueDate.ts` | Pure formatting helpers (hh:mm, `Thu 12 Nov`, narrow-space thousands) |
| `capacityLayout.ts`, `CapacityCard.tsx` | "Capacity today" card, per-shift bar and cut-off marker |
| `OrdersTable.tsx` | Read-only orders table, one column below 1024 px |
| `fixtures.ts`, `mswHandlers.ts` | Synthetic data and local MSW handlers (not registered in `api/mocks/handlers.ts`) |

## Contract (agreed with Dev 1) and open dependencies

Agreed contract:
- `GET /api/v1/warehouses/{id}/prep-queue?date=YYYY-MM-DD` returns `200` with `capacity` and `orders` (docs/06 Appendix A shape).
- `share` is a JSON number 0–1; `booked`, `booked_min`, `total_min`, `free_min`, `shifts[].minutes` are integers (minutes); `useful_hours`, `weight_kg` are numbers. No decimal strings.
- `capacity.schedule_verified` is a required boolean. Without an official schedule confirmed by the Warehouse Manager the backend returns `200` with `schedule_verified=false` and zero available capacity; the UI shows "Capacity not verified". Capacity is never derived from `expected_staff` or seed data.
- Times: `cutoff` is `HH:mm`; `loading[].at`, `prep_window.start/end` and shift start/end are ISO 8601 with offset (the UI also accepts `HH:mm`). An ISO time without offset is shown as "Unverified time".
- `GET /locations` returns `timezone` (IANA, from `ref.market.timezone`) for every location. The UI never guesses a time zone.

Still open (not shipped):
1. **Backend.** Backend #129 reportedly still returns `PLAN_NOT_APPROVABLE` for this endpoint, and `/locations` has no `timezone` yet. Until both ship, the screen works only against local MSW fixtures. No integration test against the real backend exists yet.
2. **Types** are hand-written until `schema.d.ts` exists. `timezone` is read through a local type (`LocationWithTimeZone`) so shared `api/locations.ts` is untouched.
3. **`next_action`** is not used; row actions (next PR) are derived from `status` and `prep_state`.
4. **Warehouse choice.** The sidebar scope is used. With several allowed warehouses and "All warehouses", the user is asked to pick one; the first warehouse is never assumed.
5. This screen does not approve plans. The ASM-007 warning never disables the row actions, which only record what happened.

## Viewing the screen locally without touching shared mocks

```bash
cd frontend
npm run dev:mock
```

Sign in as `wm.got@cfo.demo`, open `/warehouse/prep`. The shared mock has no `/prep-queue`, so the screen first shows the error state. In the browser DevTools Console:

```js
const { worker } = await import("/src/api/mocks/browser.ts");
const h = await import("/src/features/warehouse/prep-queue/mswHandlers.ts");
const f = await import("/src/features/warehouse/prep-queue/fixtures.ts");
// scenarios: "verified" | "unverified" | "noSchedule" | "empty"
worker.use(h.prepQueueSuccess(f.buildPrepQueueFixture("verified")));
// other states: worker.use(h.prepQueueFailure(403, "FORBIDDEN", "Denied", "corr-demo"));  (also 404, 500)
```

Click Retry (or wait up to 20 s for the poll). A page reload clears the handlers.

## Not verified

- Request cancellation is tested at hook level (`usePrepQueue.abort.test.tsx`: `fetchPrepQueue` is mocked and the `AbortSignal` from TanStack Query is asserted to abort on warehouse/date change and on unmount). It is not tested end to end through `fetch`: the MSW-based hook tests in `usePrepQueue.test.tsx` strip the signal because jsdom's `AbortSignal` is rejected by Node's `fetch`. Production code still passes it.
- Screen reader behaviour of the stacked layout below 1024 px (table semantics) needs a manual check.
- No integration against the real backend (endpoint path, `timezone`, `schedule_verified` are open dependencies).