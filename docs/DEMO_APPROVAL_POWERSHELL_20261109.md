# SE-2026-000149 approval demo: PowerShell status and safe execution gates

Run in Windows PowerShell. The existing Compose project is `cfo-demo-local`; these commands do not delete volumes. Set your working directory to the Compose checkout and keep its existing secret environment mechanism. Do not print `.env` values.

```powershell
Set-Location D:\Project\itconsultant\cfo-demo
docker compose -p cfo-demo-local ps
docker compose -p cfo-demo-local exec -T postgres psql -U cfo -d cfo -At -c "SELECT external_ref,status,date_mode,date_to,approved_plan_id FROM ops.customer_order WHERE external_ref='SE-2026-000149'"
docker compose -p cfo-demo-local exec -T postgres psql -U cfo -d cfo -At -c "SELECT id,status,created_by,approved_by,effective_from FROM ops.stock_scope_version ORDER BY id DESC LIMIT 1"
docker compose -p cfo-demo-local exec -T -e DEMO_DISPOSABLE=1 cfo-api python -m app.demo_stock_preflight --external-ref SE-2026-000149
```

Observed on November 9: order `SUBMITTED`, exact delivery date November 5; scope version 1 approved by user 132 after author 2, effective `2026-11-09T15:24:19.464914Z`; both grants have append-only audit. The API and Source containers are still frozen at `APP_NOW=2026-11-04T10:05:00+01:00`. Read-only stock preflight reports `STOCK_SCOPE_NOT_EFFECTIVE`, `NO_ACCEPTED_STOCK_BATCH`, and `STOCK_SNAPSHOT_MISSING`. The existing Source batch 1 has 300 rows but `as_of=2026-11-04T08:55:00Z`, before scope approval. There are zero WMS reservation intents and zero driver duty log rows. **Stop here on this environment.** Neither replaying batch 1 nor moving its timestamp is valid. Advancing the clock to November 9 leaves the exact November 5 delivery date in the past. No safe current command can produce `APPROVED` for this order under the existing contract.

## After the timeline and evidence are legitimately resolved

The Owner and Dev 1/Dev 2 must provide a valid forward delivery date through the reviewed source/customer-agreement workflow, plus a fresh authoritative WMS capture. Do not edit `ops.customer_order`, Source stock rows, approval timestamps, driver duty, or WMS ACK directly. Review PR #216 and its PostgreSQL tests before deploying it. To deploy reviewed code from the `cfo-demo` checkout after integration into that checkout:

```powershell
Set-Location D:\Project\itconsultant\cfo-demo
docker compose -p cfo-demo-local build cfo-api source-se cfo-web
docker compose -p cfo-demo-local run --rm --no-deps cfo-api alembic upgrade head
docker compose -p cfo-demo-local up -d --no-deps cfo-api source-se cfo-web
docker compose -p cfo-demo-local ps
```

Dev 2 then publishes a **new complete observed Source/WMS batch** through `source_system/app/stock_batches.py` using its reviewed `--complete-snapshot --snapshot` command and a manifest from the actual simulated WMS capture, with `as_of > scope.effective_from`. Verify source batch ID, capture provenance, content hash, row count, expected GBG/STO/MLM × `SE-BRD-GYP-13` coverage, and freshness. The existing `app.demo_ingest` and `app.demo_stock_preflight` commands hard-code the November 4 clock; Dev 2 must review and update these disposable guards for the new legitimate timeline before using them. Then use the reviewed stock ingest command and read-only preflight, and require accepted `ops.stock_write_run` plus fresh `ops.stock_snapshot` rows in PostgreSQL. An old or rejected batch is never a pass.

After the order's date and governed stock are valid, log into `http://localhost:5173` with the existing dispatcher demo account, open `SE-2026-000149`, run Check Feasibility, choose a valid plan, and use the actual Approve action. Before clicking Approve, resolve any server-reported WMS intent/ACK and batch-inclusion gate, warehouse staffing, vehicle and driver compliance. Verify the exact persisted outcome:

```powershell
docker compose -p cfo-demo-local exec -T postgres psql -U cfo -d cfo -At -c "SELECT o.external_ref,o.status,o.approved_plan_id,p.status,o.approved_at FROM ops.customer_order o LEFT JOIN plan.fulfilment_plan p ON p.id=o.approved_plan_id WHERE o.external_ref='SE-2026-000149'"
```

Only `o.status=APPROVED`, a persisted approved plan ID/status and the matching decision audit after the real UI transaction count as approval. Record HTTP responses, the accepted Source batch and WMS evidence IDs, Planning run, and PostgreSQL result in the demo report. Browser E2E remains **not verified** while the current timeline and evidence gates fail.
