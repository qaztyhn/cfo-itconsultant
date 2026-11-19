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
# This *only* seeds Source, scope, shifts, D7 synthetic proof, market stock,
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

- **POS creation** is a Source fixture, NOT a POS UI click; step 1 remains
  NOT VERIFIED for POS UI.
- **Sales**: Sync and Check are two real browser button clicks. The E0
  route-matrix import between them is explicitly recorded as setup and
  never labelled a UI step.
- **Dispatcher**: Approve must be on a still-proposed unexpired plan.
  HTTP 200 must match `APPROVED`, same trip IDs, one queued `CONFIRMED`
  notification ID, synthetic ACK and signed stock batch in PostgreSQL.
  If blocked, preserve HTTP status/error.code and latest verified state.
- **E2**: same notification ID must be `sent` with one DB audit and
  exactly one Mailpit message referencing the order and delivery window;
  worker begins only after the seed. A synthetic queued email on another
  order does NOT satisfy step 5.
- **E3/Driver**: every actual UI event ID/trip ID must match
  `ops.milestone_event`. Unknown/non-verified 56-day D7 history, shifts
  or vehicle context must fail closed; never insert approvals or legal proof
  merely to push Driver forward. A 409 remains BLOCKED with task and reason
  when the specific prerequisite is known.
- **CS**: same order lookup and ETA version-history are separate checks.
  An authenticated order-detail 200 does NOT prove ETA history; a 500
  must not be silently converted to 200.
- **Other cases** use separate sources: E5 draft DELAY fixture may verify
  Dispatcher Send `draft→queued` but not a real risk-generated draft or
  Mailpit unless worker evidence is recorded; T30 Chrome/T29 fixture already
  covers step 12b **on synthetic T29**, but official T26 seed remains a
  separate NOT VERIFIED replay. Rank 1–3, untouched Plan Review, KPI and
  FAILED exception require their own explicitly identified orders.

## T28 handoff and dependencies

- Run `SE-2026-000249` **only** after the Source pre-Sync fixture exists,
  and pin the browser and services to `2026-12-01T10:05:00+01:00`.
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
