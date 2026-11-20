# T27 same-order E0-04 → E1 → E2 → E3 → Driver → CS browser evidence

**Scope:** disposable synthetic Sweden pilot only; evidence goes to T28. This runner
starts with Source order `SE-2026-000249` submitted but **no CFO order**,
`APP_NOW=2026-12-01T10:05:00+01:00`, browser `Europe/Stockholm`.
It exercises **real CFO Sales UI Sync and Check**, a **real Dispatcher UI Approve**
with E1's WMS simulator on **the same application container loopback**,
the E2 opt-in worker/Mailpit and warehouse/driver/CS UI.

## Preparatory work: not counted as user clicks

Run from a clean disposable `cfo-demo-e004` Compose project **before December 1, 2026,
10:05 Europe/Stockholm**. The existing E0-04 fixed scope uses the current database
approval timestamp, and refuses starting the frozen demo after its clock expires.
Never backdate grants or use this on non-disposable databases. Future demos beyond
that date need new approved future clock and aligned Source/driver/shift fixtures.

1. Install Python 3.12 backend development dependencies, `python-dotenv`, Playwright
   and Google Chrome (for CI: `python -m playwright install chrome`), Node 20,
   `npm ci` in frontend and Docker Compose v2.
2. Create a **private, untracked** `.env` from `docs/DEMO_SETUP.md` with
   `APP_ENV=test`, `DEMO_DISPOSABLE=1`,
   `COMPOSE_PROJECT_NAME=cfo-demo-e004`, `APP_NOW=2026-11-04T10:05:00+01:00`,
   localhost ports `8000`, `5173`, `8025`, separate Source/CFO databases,
   private demo auth, tick and a new `SYNTHETIC_WMS_API_KEY`.
   `VITE_USE_MOCKS=false` and `CORS_ORIGINS=["http://localhost:5173"]`.
   Never print keys, recipients or raw JWTs.
3. From repo root, in a shell with `.env` exported:

```sh
export COMPOSE_FILE="docker-compose.yml:tools/t27_e1_compose.override.yml"
export PYTHONPATH=".:backend"
python tools/e0_04_prepare.py --stop-before-sync
# This *only* seeds Source, scope, shifts, T12 verified demo evidence, market stock,
# routing inputs. CFO order must still be absent; no TestClient Sync/Plan.
export APP_NOW="2026-12-01T10:05:00+01:00"
python tools/t27_integrated_browser.py --output t27-e004-run-01
```

`tools/t27_integrated_browser.py` generates the exact E1 WMS native-SKU fixture
**after** browser Sync + feasible proposed plan. It copies it into `cfo-api`,
starts the reviewed SQLite WMS simulator at `127.0.0.1:8188` **inside that
container**, and clicks Approve from the Dispatcher page. `DisposableWmsPort`
continues to allow loopback only. WMS service is synthetic and cannot execute
production WMS writes. Worker profile `demo-worker` starts explicitly after seed
and approval, **never** with default `docker compose up`.

## Retest manually on a running `cfo-demo-e004`

Use the same checkout and private `.env` used to start `cfo-demo-e004`. From
the repo root, with the backend Python environment activated and Docker running,
leave `SE-2026-000249` in `PLANNED`, then run in Git Bash:

```sh
PYTHONPATH=.:backend python -m tools.t27_integrated_browser --prepare-wms
```

Including `backend` lets Python import `tests.e2e.t27_http_evidence` from
`backend/tests`.

This rebuilds CFO API and web in the existing project, preserves PostgreSQL,
and prepares WMS for the proposed rank-1 plan from the latest run. If you used
**Plan Again**, the output shows the new `plan_id`. The command stops if an
active WMS intent already exists. For a fresh stack, `python tools/e0_04_prepare.py`
prepares the proposed plan first. Run both commands before the fixed E0-04
deadline described above. Use the backend venv with `python-dotenv` and
`playwright` installed. Manual mode starts no browser and needs no Chrome install.

1. Reload CFO as Dispatcher. Check **Plan review** in both the sidebar and
   the Order queue toolbar. The review list should contain only `PLANNED`
   orders. In Order queue, click the selected **Open** chip to clear it, then
   click it again to restore the Open group. Stock freshness uses the last
   successful load in the Dispatcher's market. In this demo the hold uses the
   same fixed Stockholm clock as the API, so its remaining time stays fixed.
2. Open the row's **Plan review** and select the proposed plan. Before clicking
   **Approve**, open DevTools → **Network**, enable **Preserve log**, and filter
   by `/plans/{plan_id}/approve` using the ID printed by `--prepare-wms` (for
   example, `/plans/2/approve`). Click **Approve** and confirm. A feasible
   `tight` plan requires no separate acknowledgement. Capture the `POST` and
   verify HTTP `200`, `order.status = APPROVED`, the selected `plan.id`,
   `plan.status = approved` and `trip_ids`. The UI shows **Plan approved** and
   disables Approve with **Only a proposed plan can be approved.** When the
   response includes a `CONFIRMED` notification with status `queued`, the UI
   also shows **Confirmation email queued**. The integrated runner verifies
   simulated WMS separately against its reservation and accepted stock batch.
   To verify Sales approval independently, use a separate clean run with an
   eligible initial plan in the Sales user's own store, then click **Confirm
   standard delivery plan**. This patch implements the tight-plan clause of
   DEC-R3-10. Other T19 cases are tracked separately.
3. For the confirmation email, start the existing disposable worker once
   approval has queued the message. In Git Bash or a POSIX shell:

   ```sh
   APP_NOW=2026-12-01T10:05:00+01:00 docker compose --env-file .env \
     -f docker-compose.yml -p cfo-demo-e004 --profile demo-worker \
     up -d --no-deps cfo-worker
   ```

   Record the `CONFIRMED` notification ID from the Approve response. Check that
   the same ID reaches `sent`, then open Mailpit at `http://localhost:8025` and
   verify exactly one confirmation with the CFO order number and committed
   delivery window. For Warehouse/Driver execution-day setup and evidence,
   use the full Chrome runner on a fresh stack.

Each runner writes `t27-integrated.json` and `t27-integrated.md` with **14
rows (including 12b)**, one row per actual checklist step, `PASS / FAIL /
BLOCKED / NOT VERIFIED`, originating fixture, requested vs actual UI start
and precise last verified action. Evidence includes only synthetic IDs, HTML
screenshots, sanitized HTTP method/route/status/error.code, WMS batch provenance,
Mailpit message count and authoritative PostgreSQL statuses. No raw request
headers, passwords, tokens, recipient values or GPS go in the artifact.
Keep any Playwright trace containing authentication data private, never upload
it to a public Actions artifact.

The Actions workflow `.github/workflows/t27-integrated-e004.yml` creates
new random disposable passwords at runtime, runs E0-04 pre-Sync setup,
Chrome and the above path, uploads only sanitized evidence, then destroys
**only** `cfo-demo-e004` volumes. It is not a production deployment.

## Acceptance boundaries

- **Step 1 (CFO Sales input)** is **PASS** only when Chrome opens CFO
  **Sync & Check**, enters the external order reference and verifies the
  field value. The task board defines step 1 this way. POS Create/Submit
  is separate synthetic Source setup, not a scored CFO UI step.
- **Step 2 (Sales)**: Chrome opens CFO Sync & Check, enters the Source
  reference and clicks both Sync and Check; HTTP 200 and the still-proposed
  plan are checked. The E0
  route-matrix import between them is explicitly recorded as setup and
  never labelled a UI step. After Sync, the runner reads the CFO `order_no`
  from the returned `order_id` and uses it in Mailpit, Prep Queue and CS.
- **Dispatcher**: Approve must be on a still-proposed unexpired plan.
  HTTP 200 must match `APPROVED`, same trip IDs, one queued `CONFIRMED`
  notification ID, synthetic ACK and signed stock batch in PostgreSQL.
  Task-board step 4 **also requires T15 market rotation**; the approval
  subcheck may PASS while whole-step status remains BLOCKED (NULL assignment)
  or NOT VERIFIED (assignment exists but rotation fairness/eligibility
  untested). If Approve fails, preserve HTTP/error.code and last state.
- **E2**: same notification ID must be `sent` with one DB audit and
  exactly one Mailpit message matching the CFO order number and both
  endpoints of the persisted commitment, formatted in Stockholm time;
  worker begins only after the seed. A synthetic queued email on another
  order does NOT satisfy step 5.
- **E3/Driver**: after the Mailpit check, stop the Dec 1 worker and recreate
  only the CFO API at the trip's planned departure on its Stockholm
  `target_date` (Dec 2). Warehouse and Driver Chrome contexts use that same
  clock. The database, order, plan and trip remain those from Approve.
  T12 must have a verified availability row for Dec 2 and a current
  qualification for that vehicle. Each UI event ID/trip ID must match
  `ops.milestone_event`. See [T12 commands and HTTP evidence](T12_DRIVER_VERIFICATION.md).
- **CS**: same order lookup and ETA version-history are separate checks.
  The report records the lookup independently. ETA is `BLOCKED` under T14
  only when an HTTP 500 `INTERNAL_ERROR` matches a backend
  `NotImplementedError` for the same route and correlation ID. An unexpected
  rejection or missing response is `FAIL`.
- **Other cases** use separate sources: E5 draft DELAY fixture may verify
  Dispatcher Send `draft→queued` but not a real risk-generated draft or
  Mailpit unless worker evidence is recorded; T30 Chrome/T29 fixture already
  covers step 12b **on synthetic T29**, but official T26 seed remains a
  separate NOT VERIFIED replay. Rank 1–3, untouched Plan Review, KPI and
  FAILED exception require their own explicitly identified orders.

## T28 handoff and dependencies

- Run `SE-2026-000249` **only** after the Source pre-Sync fixture exists,
  starting Sales/Approve and worker at `2026-12-01T10:05:00+01:00`. The
  runner advances the CFO API, Warehouse and Driver to the approved plan date.
- For any failed/rejected action, report **last committed milestone**, HTTP
  status, `error.code` and owning task (E1/E2/T12/T13/T14/T16 etc).
- When T26 seed is available from Hương, rerun step 12b on the **official
  period and expected counts** using the T30 workflow and separate revenue
  orders. Do not claim T26 counts from a six-order T29 fixture.
- The E3 one-/two-trip APPROVED fixture evidence in #226 remains historically
  valid, but is not a substitute for an integrated Sales→Approve proof.
- If this branch has not run on an isolated stack, all new UI steps remain
  **NOT VERIFIED** despite code existing. T27 should close only after a
  dated exact-commit actual run and a validated 14-row ledger.

**Assumptions:** existing DEC-R3 and WMS-simulation gates reviewed; no new
business decisions, no data-gate or privacy bypass. No merge/deployment by QA.

## Task-board-aligned 14-row QA accounting (2026-11-20)

The authoritative [Round 3 task board](TASK_BOARD_R3_E2E_DEMO.md)
defines step 1 as **opening CFO Sales Sync & Check and entering the reference**
and step 2 as **Sync now → Check feasibility**. Earlier PR notes incorrectly
relabelled step 1 as POS submission, which is only synthetic setup. When real
Chrome verifies the CFO form, step 1 is PASS.

Step 4 also includes T15 Dispatcher rotation. Successful UI Approve with
WMS ACK and PostgreSQL evidence is **approval subcheck PASS** but not whole
step PASS. NULL `assigned_dispatcher_employee_id` makes full step BLOCKED;
when all trips have assignments but fairness/turn provenance is not tested,
full step remains NOT VERIFIED. The runner preserves both subcheck statuses.

A current-main replay with approval success and unassigned trips is expected
to report **4 PASS / 5 BLOCKED / 5 NOT VERIFIED / 0 FAIL**. This count must
be confirmed by an exact-head Chrome run, not assumed from code edits.
CS lookup separately PASS under step 11; ETA API HTTP 200 is not proof
of version-history rendering. Dispatch 409 retains its exact D7 blocker.
Keep Source external ref and generated CFO order number distinct.

Assumptions: reviewed; new decisions none. No WMS production writes,
actual GPS or unverified driving-duty bypass.

## T27 Step 8 — Round 3 same-order Driver continuation (T12/T13/T14)

The updated runner **does not** use TestClient to dispatch, upload GPS or deliver. In
one Playwright Chrome session as the driver assigned to the actual trip generated
from Source `SE-2026-000249`, it presses **Mark dispatched**, **Update location**
and **Confirm delivered**, recording the real API response and a PostgreSQL
checkpoint at each stage. The run cross-checks the Source reference, CFO order
number, `order_id`, approved `plan_id` and exact `trip_id` before interacting.

The `APP_NOW` clock is frozen on FastAPI, so the runner recreates **only**
`cfo-api` between milestones with an incremented Sweden-local timestamp, while
pausing Playwright's Chrome clock at each matching synthetic milestone. The
server stays two seconds ahead as a scheduling allowance. In the disposable
synthetic browser only, Chrome's **actual geolocation override** supplies the
coordinates and the browser test aligns the native fix timestamp with its
Playwright clock. No TestClient or hidden API call creates a driver event,
position or POD. The completion fix is newer than the preceding tap, never
earlier than the actual departure or later than `APP_NOW`.

The `t27-integrated.json` and `t27-integrated.md` artifact contains separate
Dispatch/GPS/Delivered statuses, HTTP status/error, event/position IDs, DB
assertions, SHA, T26 seed file SHA256 digests and milestone clocks. Screenshots
mask the delivery stop/address block, and no GPS coordinates, request bodies,
authentication tokens, demo recipient names or real PII are serialized.

Acceptance conditions: Dispatch HTTP 200 + `DISPATCHED` milestone +
`on_road` trip/order; GPS HTTP 202 + one `driver_tap` point + newly stored
`eta_forecast(trigger=position)` captured **before** terminal cleanup;
Delivered HTTP 200 with a new `payload.position`, persisted POD with
`site_distance_m`, completed trip and DELIVERED order, with **zero** remaining
`ops.vehicle_position` for that order. All three must involve the same
trip; an earlier PASS never implies later stages passed.

**T12 integration (current main):** the E0-04 setup ingests the authoritative
synthetic Fleet availability and vehicle-eligibility feeds for December 2.
Driver Dispatch must pass the unchanged DEC-R3-07 stored verification (official
shift, verified feed, licence and driving budget); the legacy D7 reader remains
disabled after the execution-day clock rollover. There is no custom 56-day
historical-data generator or production gate bypass. Before GPS testing, a
synthetic-only, exact-order fixture enables GPS and records a synthetic notice;
this is never real-worker GPS approval or evidence of legal sign-off. Real Chrome
still supplies the two independent fixes, and a missing Fleet/notice gate
continues to produce an actual backend BLOCKED/FAIL checkpoint.

Run via the isolated `t27-integrated-e004.yml` workflow on branch
`feat/r3-t27-same-order-driver-step8` or by the full `--output` invocation
above, never against a non-disposable environment.

## Round 3 acceptance replay

Use the `t27-integrated-e004.yml` job matrix. Each job starts a fresh disposable
project. The `complete` job follows the original successful delivery. The
`expired_t12` job preserves the Dispatch rejection regression. The `failed`
job follows the same Source order in a fresh project: two spaced position
updates cause the predicted-late alert, the appointed Dispatcher reviews a
same-day window and explicitly sends the DELAY draft, and the Driver completes
with FAILED. Dispatcher acknowledges the resulting critical alert in Exceptions.
The `reporting` job uses the official T26 project for KPI, revenue and the Sales
rank alternative probe. Read the JSON ledgers from all applicable jobs.

| Step | Acceptance result on the disposable replays |
|---|---|
| 1 | PASS. Sales entered the submitted Source reference in CFO. |
| 2 | PASS. Browser Sync and feasibility requests returned HTTP 200. |
| 3 | PASS ([reporting job](https://github.com/qaztyhn/cfo-itconsultant/actions/runs/44740227406/job/136301755444)). Sales selected rank 2 for SE-2026-000123 in Chrome with `reason_code=other`: `POST /plans/7/approve` HTTP 200; PostgreSQL plan `approved`, order `APPROVED`, `PLAN_APPROVED` audit actor `sales`, rank `2`, reason `other`, exactly one `CONFIRMED`. |
| 4 | PASS. Approval and reflected synthetic WMS batch agree with the expected rotation candidate, trip assignment and PLAN_APPROVED audit. |
| 5 | PASS. A single CONFIRMED email with the committed window reached Mailpit. |
| 6 | PASS. Dispatcher opened the exact planning run from the order queue and approved it. |
| 7 | PASS. Warehouse preparation, ready and loaded events match PostgreSQL. |
| 8 | PASS. Same-trip Dispatch, one-point GPS checkpoint, delivery POD and terminal GPS purge. |
| 9 | PASS. Assigned live tracking and predicted-late risk, reviewed DELAY draft and explicit Send. |
| 10 | PASS. Each expected lifecycle template reached Mailpit once with the same order reference. DELAY also matches the reviewed window. |
| 11 | PASS. CS order lookup and every rendered ETA version match the scoped API and PostgreSQL. |
| 12 | PASS ([reporting job](https://github.com/qaztyhn/cfo-itconsultant/actions/runs/44740227406/job/136301755444)), ops/admin account. Five cards, Sales/Dispatcher breakdown and ETA target 20/60 shown. Reconciled with PostgreSQL: `on_time_rate` (summary and daily), `manual_intervention_rate`, and `plan_acceptance_rate` total, each path and daily series. Display-only checks: `planning_time_min` and ETA median/P90 stay `null` and the UI shows "Chưa có dữ liệu" (no approved measurement source). |
| 12b | PASS ([same job](https://github.com/qaztyhn/cfo-itconsultant/actions/runs/44740227406/job/136301755444)). Six orders, five groups, SEK 303 recognised and the ST-001 approved-order drilldown. |
| 13 | PASS at the task-board demo checkpoint. Driver FAILED with a POD. Dispatcher saw and acknowledged the critical alert, and no new planning run appeared. Full T18 recovery stays outside this checkpoint. |

The demo worker uses the latest stored scheduled-send instant for terminal
mail, preserving quiet hours. The risk and failure artifacts omit coordinates,
recipient data and authentication data. No decision IDs changed.

## T27 closing run — PR #249 (`feat/t22-five-kpis`)

- **Commit:** `9ec9a6b6a4d778a3fa6a5dc55cbd0123042a9af2`
- **T27 workflow:** [run 55](https://github.com/qaztyhn/cfo-itconsultant/actions/runs/44740227406) — `complete`, `expired_t12`, `failed` and `reporting` all succeeded. Evidence artifacts: `t27-integrated-e004-<scenario>-synthetic-evidence` (JSON and screenshots; 3-day retention).
- **CI:** backend, frontend and source jobs green on this commit.
- **Not yet done:** the post-merge replay on `main`; T27 is closed only after that run.

`plan_acceptance_rate` on the T26 seed (reporting job; PostgreSQL = API = UI):

| Item | Value | Verified against |
|---|---|---|
| Orders in sample | 6 (5 synthetic audit rows added by the test fixture) | PostgreSQL |
| Total | 5/6 = 83.3% | PostgreSQL, API, UI card |
| Sales / Dispatcher | 75% / 100% | PostgreSQL, API, UI card |
| Daily 2026-11-30 / 2026-12-01 | 100% / 0% (rank-2 approval only) | PostgreSQL, API, UI table cell |

Display-only confirmations (no measurement source, not reconciled): `planning_time_min` and ETA median/P90 are `null` and render "Chưa có dữ liệu"; ETA target 20/60 min is shown.
