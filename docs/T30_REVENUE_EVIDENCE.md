# T30 — Orders & revenue (A16b) browser evidence and T27 step 12b handoff

**Product contract:** US-REV-02 AC1–AC7; UI §A16b; API §19.11. Work starts from
`main` `2c3a16ac5196b0a7eb7b923dd4c4b886d152bf75`. T30 is read-only.
No production order states, WMS or customer email are changed.

## Verified real-browser fixture (T29, not T26)

- Browser: actual Google Chrome via Playwright; real CFO Vite frontend + FastAPI
  + PostgreSQL 16, separate `cfo_t30_*` database created/dropped on each run.
  No MSW, mock network responses or generated success ACKs.
- Fixture: **six synthetic T29-style orders**, two `APPROVED`, one `DISPATCHED`,
  one `DELIVERED`, one `FAILED` and one `CANCELLED` before approval.
  The cancellation is recorded through the real `transition()` and
  `ORDER_CANCELLED` audit. These statuses were pre-seeded, **not** reached
  through POS → Sales → Approval → Driver workflow.
- `APP_NOW=2026-11-19T10:05:00+01:00`, market/browser timezone
  `Europe/Stockholm`. Test explicitly selects **2026-11-01..2026-11-30**.
- Screenshots: `01-period-five-groups.png`,
  `02-group-selected-location-required.png`,
  `03-group-orders-db-matched.png`. JSON `t30-evidence.json` includes only
  synthetic order counts and `path/http/query` (no JWT, passwords, names, or
  customer GPS). The fixture DB is destroyed after results are recorded.
- Confirmed baseline: [real Chrome GitHub Actions #44553315102](https://github.com/qaztyhn/cfo-itconsultant/actions/runs/44553315102) **PASS** on
  `00dbf24de8964f292564f113be305ef8d1a4f452`.
  Current PR head needs its **own** matching Chrome and frontend CI evidence.

| T27 12b fixture subcheck | Real observation |
| --- | --- |
| Choose 01–30 November | `GET /revenue/order-status` **200**, `period.from/to` match |
| Five group cards | `approved=2`, `in_transit=1`, `completed=1`, `failed=1`, `cancelled=1`; `total.orders=6` |
| Revenue source | `GET /revenue/summary` **200** with recognised from actual delivery date; UI shows `303 SEK` for the synthetic delivered order |
| Click approved, all locations | UI holds selected group, requests a concrete location; **zero list GETs** |
| Choose Store 1 | `GET /revenue/order-status?view=store&location_id=2&from=2026-11-01&to=2026-11-30` **200**; selected scope total 5, approved 1 |
| List matched to card | `GET /revenue/orders?view=store&location_id=2&from=2026-11-01&to=2026-11-30&status_group=approved&page=1` **200**; `total=1`, matches approved card |
| Customer privacy | Business owner sees neither customer-name column nor customer values |

## Reproduce on a disposable local stack

Prerequisites: Python 3.12, Node 20, Google Chrome, PostgreSQL 16 on
**loopback** with a role permitted to `CREATE DATABASE`; `TEST_DATABASE_URL`
is an environment value, **never checked into Git**.

```sh
cd frontend
npm ci
npm run lint
npm run test -- src/features/revenue/Revenue.test.tsx src/features/revenue/Revenue.msw.test.tsx src/features/revenue/revenueApi.test.ts
npm run build
cd ../backend
python -m pip install -e ".[dev]" "playwright>=1.50,<2" tzdata
python -m playwright install chrome
python -m tests.e2e.t30_revenue_browser --output ../t30-browser-evidence
```

The [T30 workflow](../.github/workflows/t30-revenue-browser.yml) provisions its
own PostgreSQL 16 instance, runs Chrome and saves screenshot/JSON artifacts
with a short retention period. MSW tests cover HTTP query parameters, date,
view/location, pagination, 403/404 behavior, owner scoping, zero proportions
and the Business owner privacy projection. Existing Revenue tests retain
daily chart, location breakdown and CSV export regression.

## T27/T28 acceptance boundary

**T30 implementation and T29-fixture integration can be accepted independently.
T27 step 12b on the official demo dataset remains NOT VERIFIED** until T26
has been integrated. T26 owner (Hương) should provide a stable seed version,
run ID, exact 5-group counts and revenue expectations, period, market-local
`APP_NOW` and authorised Store/Warehouse location IDs. Replay the same
period → five groups → select group → choose location → compare
`groups[].orders == /revenue/orders.total` flow on that official seed. Validate
`/revenue/summary.recognised` separately from status group values; never use
`groups[].amount` as recognised revenue or add Store and Warehouse totals.

Save all runs by **exact commit SHA**. Browser fixture PASS is not evidence of
T26 production/demo data readiness and not a substituted full 14-step journey.
