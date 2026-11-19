# E1 — approve the E0-04 order with disposable WMS

This is a test-only continuation of [E0-04](E0_04_DEMO.md). The fixed Source
order is `SE-2026-000249`; CFO order 1, proposed plan 1, SKU
`SE-BRD-GYP-13` × 10, warehouse STO, delivery 2026-12-02. The clock is
`2026-12-01T10:05:00+01:00`; the plan hold expires at 10:20 Stockholm.

## Reproduce after reset

1. Run the E0-04 reset and `tools/e0_04_prepare.py` as documented there. Use
   the resulting private `.env`, approved stock scope, Source batch 2, D7
   fixture and feasible proposed plan. Do not run this command on a production
   database. Apply migration head before calling Approve.
2. Remove only `.e1_wms.sqlite` and `.e1_wms_fixture.json` in this worktree
   when resetting the disposable E0-04 database. Keep them when testing an
   uncertain ACK or retry so WMS status can recover the prior reservation.
3. With the backend virtual environment active, run from this worktree root:

   ```powershell
   $env:E0_DEMO_ENV_FILE = '<path-to-private-E0-04-.env>'
   python tools/e1_demo_run.py
   ```

The runner checks `APP_ENV=test` and `DEMO_DISPOSABLE=1`, sets the fixed clock,
enables `WMS_RESERVATION_MODE=simulated`, generates a private WMS signing key,
builds an exact native SKU fixture from the existing order, migrates the local
PostgreSQL to head, runs the loopback SQLite WMS, and calls the **existing API**
twice with the same Dispatcher token, key and payload. It prints only order,
plan, trip, notification, reservation and batch identifiers. The WMS fixture
contains synthetic SKU and quantities; the key is never written there.

The default WMS mode remains disabled. The simulator refuses production, any
clock outside the reviewed demo dates, or a missing explicit mode. A real WMS
contract and production deployment approval remain separate work.

## Observed on the E0-04 PostgreSQL fixture (2026-11-19)

First Approve: HTTP 200, order 1 `APPROVED`, plan 1 `approved`, `trip_ids=[1]`,
`CONFIRMED` 1 `queued`. Immediate replay with the same idempotency key and
payload: HTTP 200 with the same trip ID and notification. PostgreSQL: one
`PLAN_APPROVED`, one trip, one `CONFIRMED`. WMS reservation
`SYN-33d0f396a324991ad54a150f` reflects in batch 2; CFO links it to
`stock_write_run` 2 (`source_kind=wms_synthetic`, batch 2, accepted) and stock
ingest run 6. The earlier Source batch 2 remains a separate accepted write.

The post-ACK stock gate credits this order's own WMS reservation exactly once.
The signed batch and inclusion list, matching ACK and immutable request,
effective scope, ingest run and snapshot are checked again in the final locked
transaction. An unverified ACK or batch cannot create a trip.

The local runner exercises the API through FastAPI's test client and real
PostgreSQL; it does not click the UI. WMS SQLite is persistent during the run.
The PostgreSQL WMS-intent test verifies lost-ACK rollback, status lookup with
the same key, recovered ACK persistence, and rejection of a wrong ACK. A full
API fault injection between reserve and ACK persistence is **NOT VERIFIED**.
Mailpit delivery is outside E1; `CONFIRMED` is queued for the E2 worker.

Verification commands (with `TEST_DATABASE_URL` pointing to the disposable
PostgreSQL host port):

```powershell
python -m pytest -q backend/tests/integration/test_approval_service.py backend/tests/integration/test_ingest_stock_scope.py backend/tests/integration/test_wms_final_approval_gate.py backend/tests/unit/test_disposable_wms_service.py
python -m pytest -q backend/tests/integration/test_wms_intent.py backend/tests/unit/test_wms_mode.py
python tools/harness.py verify
```

The first two groups passed 45 and 16 tests respectively. The full harness
started and passed Ruff, mypy and import-linter; its Black gate initially
failed on formatting and was corrected. The full 1,542-test pytest suite was
stopped at 6%, so the complete harness is **NOT VERIFIED**. The final Black
and Ruff checks passed separately. GitHub CI is reported on PR #224.
