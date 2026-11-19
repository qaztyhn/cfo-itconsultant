# E2E (Playwright, Docker Compose)

16 kịch bản ở `docs/08_Development_Plan.md` mục 6.3. Đồng hồ `APP_NOW=2026-11-04T10:05:00+01:00`.

## E3 warehouse to driver browser walkthrough

This walkthrough starts at `APPROVED` with a synthetic plan, a warehouse manager
assigned to `WH-1`, and a separate assigned driver per trip. It covers US-WH-04
AC1–4, the browser handoff in US-EXE-01 AC1 and BR-EXE-01. The existing Prep Queue
Vitest suite covers recovery after a failed send and a conflict. The walkthrough
uses the real application API and PostgreSQL.

Prerequisites are Python 3.12, Node.js, Google Chrome and a disposable PostgreSQL 16
server on loopback. Set `TEST_DATABASE_URL` to that server's admin database via the
environment, using a role that can create databases. The script starts its own
loopback Uvicorn and Vite processes and creates short-lived synthetic credentials.

1. In `frontend`, run `npm ci`.
2. In `backend` with a virtual environment active, run the following.

   ```sh
   python -m pip install -e ".[dev]" "playwright>=1.50,<2" tzdata
   python -m tests.e2e.prep_queue_browser --trips 1 --output ../demo-e3-one
   python -m tests.e2e.prep_queue_browser --trips 2 --output ../demo-e3-two
   ```

| Case | Order | Warehouse | Trip IDs |
| --- | --- | --- | --- |
| 1 vehicle | `SE-E3-1T` | `WH-1` | `1` |
| 2 vehicles | `SE-E3-2T` | `WH-1` | `1`, `2` |

Each synthetic order contains one line with one 5 t pallet per trip. The approved
plan includes the scheduled preparation start as ETA evidence. Plans created
before this evidence was stored can return `409 PLAN_NOT_APPROVABLE` at START_PREP.

The API and browser run the `2026-11-10` business day in `Europe/Stockholm`.
`APP_NOW` is `2026-11-10T10:06:00+01:00`. The browser enters
`2026-11-10 10:05:10` for Start preparation (crew of 3), `10:05:40` for Goods
ready, `10:05:50` for the first Mark loaded, and `10:05:55` for the optional
second Mark loaded. On a Vietnam device the corresponding times are
`16:05:10`, `16:05:40`, `16:05:50`, and `16:05:55` on the same date.

Each run writes `demo-prep-browser-results.json`, screenshots and local service
logs to its output directory. The JSON records the event IDs, payloads, post-ACK
queue reads, reload, assigned driver's trip list and persisted milestone IDs.
The script creates a fresh `cfo_e3_*` database for each run and drops that
database on exit. To reset and run again, use the same command with a new
`--output` directory.

Vehicle issue depends on the backend's approved-plan `loading[].vehicle_id`
DTO and T07. Round 3's prep duration calculation is tracked by T05.
