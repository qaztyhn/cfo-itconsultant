# Manual plan (`POST /orders/{id}/manual-plan`) — engine adapter proposal and blocking decision

**Status: proposal only (Dev 1, 2026-11-09). Owner subsequently chose Option A in `DEC-MANUAL-PLAN-20261109` (`docs/ASSUMPTIONS.md`, merged PR #185). The decision is no longer blocked; the five-gate verifier/service implementation is still pending. No code, schema or API change in this PR.** `approval_service.manual_plan()` keeps rejecting with `409 PLAN_NOT_APPROVABLE`; Dev 3's Manual Plan UI (`ManualPlan.tsx`, already merged) expects exactly that fail-closed answer until this lands.

## 1. Blocking contract conflict (needs an Owner decision)

| Source | Says |
|---|---|
| docs/06 §6.4, docs/02 US-PLN AC3, docs/04 step 6 | A valid manual plan is created with `status = manual` and **"duyệt luôn" (approved immediately)**; `order → APPROVED`, five-gate re-check, reservations committed, `MANUAL_PLAN_CREATED`. |
| Task statement for this work, AGENTS "no automatic approval" | A manually created plan must **not** be approved automatically. |

Both cannot hold. Options: **(A)** keep §6.4: the Dispatcher's explicit submission of the manual plan *is* the approval decision (authorized Dispatcher only, reason mandatory, full audit) — no system auto-approval, but one step; **(B)** change §6.4: manual plan is saved as `proposed`/held and approved by a separate `POST /plans/{id}/approve` (two steps, requires updating docs/06, docs/02 AC3 and Dev 3's UI result handling). Recommendation: **A**, because it matches approved docs and the UI; the Dispatcher is the decision maker and `09` invariant 21 only forbids *system* approval. **Owner decision (later update): Option A approved in `DEC-MANUAL-PLAN-20261109`. This proposal is not an implementation or production approval.**

## 2. Missing engine piece (technical, no contract needed)

The engine only generates candidates (`plan_order`); `result="manual"` was removed in v1.2, so there is **no function that verifies a dispatcher-supplied assignment**. Required pure function in `app/engine` (no DB/clock/IO):

`verify_manual(order, warehouse_ctx, assignment, cfg) -> ManualVerdict` where `assignment = {warehouse_id, target_date, goods_ready_at, vehicles:[{vehicle_id, driver_employee_id, load_lines:[{line_no, qty_base}], depart_at, eta_at}]}`. It must reuse (not copy) the existing pure parts and return per-gate `CheckResult`s plus the same reason codes as automatic planning:

1. **stock** – ATP for every line at the chosen warehouse/date (`atp`), all lines fully allocated across the vehicles (sum of `qty_base` = order qty per line; no line left over or over-allocated);
2. **preparation** – labour hours and `goods_ready_at` not earlier than the engine computes from official capacity (`schedule`), warehouse cut-off respected;
3. **truck** – per vehicle: kg/m³ (`OVER_LOAD`, `NO_TRUCK_FIT`), capabilities/allowed groups, vehicle free (`vehicle_free`), 1 trip per vehicle;
4. **site_date** – `eta_at` consistent with route drive time and the receiving calendar/hours (`OUTSIDE_RECEIVING_HOURS`), target date allowed by the order's date mode;
5. **safety** – `driver_problem` for each (driver, vehicle, interval): official shift, verified 56-day history (`driver_history`, fail closed without evidence), 11 h rest, working/driving limits, licence, Regulation 561 flag; one driver per vehicle, no driver reused in overlapping trips.

Failure → `422` with the first failing check code (docs/06 §6.4), never a hardcoded pass.

## 3. Service flow once decided (reuse existing pieces)

`manual_plan(order_id, actor, payload, key)` in one transaction: idempotency claim (same key+body replay, different body `409 IDEMPOTENCY_CONFLICT`); Dispatcher only; lock order then reservations (same order as `approve`); load fresh inputs (`planning_inputs.load_inputs`); `verify_manual`; persist run/plan/plan_vehicles (`kind='rerun'`/manual flag), `manual_reason_code` (+text) mandatory with the approved enum, snapshot of the system's best proposal; reservations via `reservation_service` (stock/prep/vehicle `committed` under option A, `held` under option B); transition via `transition()`; audit `MANUAL_PLAN_CREATED`; `manual_plan_count` KPI continues to count `status='manual'` plans. Orders only `PLANNED`/`NO_FEASIBLE_DATE`. Old held plan superseded in the same transaction.

## 4. Test matrix (real PostgreSQL)

normal 1-vehicle and 2-vehicle (loads sum to the order); under-/over-allocated line; `OVER_LOAD`/`NO_TRUCK_FIT`; stock short; prep capacity; receiving-hours; driver without shift / without verified history / rest 10h59 / licence; vehicle busy for another order; Sales/Warehouse/other market denied; missing reason; idempotent replay and conflict; concurrent two manual plans for one order and for the same vehicle (exactly one wins, no overcommit); rollback after failure leaves no plan/reservation/audit; no automatic approval beyond the chosen option.

## 5. Dependencies

Dev 3: response/422 mapping of `ManualPlan.tsx` (check codes) once the option is chosen. Dev 2: verified driver-evidence reader (otherwise every manual plan fails closed on `safety`, correctly). Owner: Option A selected (`DEC-MANUAL-PLAN-20261109`); implementation remains pending.
