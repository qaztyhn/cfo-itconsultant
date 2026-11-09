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
| `api.ts` | `GET /prep-queue?warehouse_id=&date=`, response shape check |
| `usePrepQueue.ts` | TanStack Query hook, 20 s poll, stops on 401/403/404, no placeholder data |
| `useWarehouseSelection.ts`, `timezone.ts` | Which warehouse and which "today" to show |
| `format.ts`, `queueDate.ts` | Pure formatting helpers (hh:mm, `Thu 12 Nov`, narrow-space thousands) |
| `capacityLayout.ts`, `CapacityCard.tsx` | "Capacity today" card, per-shift bar and cut-off marker |
| `OrdersTable.tsx` | Read-only orders table, one column below 1024 px |
| `fixtures.ts`, `mswHandlers.ts` | Synthetic data and local MSW handlers (not registered in `api/mocks/handlers.ts`) |

## Dependencies and assumptions (need an owner decision)

1. **Endpoint path.** Appendix A (`GET /prep-queue?warehouse_id=&date=`) is followed because it defines the payload. `06` §8.2 and `03` §5.6 list `/warehouses/{id}/prep-queue` and `/warehouses/{id}/capacity`. Dev 1 to confirm the final path.
2. **`schedule_verified`.** Not in Appendix A. Optional local field based on ASSUMPTIONS Q12d (ASM-007). Capacity is shown as verified only when it is exactly `true`; missing or `false` shows "Capacity not verified". It is never inferred from `present`, `shifts` or `expected_staff`. It does not block any button and is not used to promise delivery.
3. **Units.** `share` is read as a 0–1 ratio and `booked` as minutes (Appendix A gives no units). Dev 1 to confirm.
4. **Time zone.** `GET /locations` on the real backend does not return `timezone` (only the shared mock does). Without it the screen stops with a clear message and does not call the API. "Today" is computed in the warehouse time zone from an explicit `now` parameter.
5. **Time formats.** API times may be `hh:mm` or ISO 8601 with offset. An ISO time without offset is shown as "Unverified time", never guessed.
6. **Types** are hand-written until `schema.d.ts` exists.
7. **`next_action`** is not used; row actions (next PR) are derived from `status` and `prep_state`.
8. **Warehouse choice.** The sidebar scope is used. With several allowed warehouses and "All warehouses", the user is asked to pick one; the first warehouse is never assumed.

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

- Request cancellation (`AbortSignal`) is not tested: the hook tests strip the signal because jsdom's `AbortSignal` is rejected by Node's `fetch`. Production code still passes it.
- Screen reader behaviour of the stacked layout below 1024 px (table semantics) needs a manual check.
- No integration against the real backend (endpoint path, `timezone`, `schedule_verified` are open dependencies).