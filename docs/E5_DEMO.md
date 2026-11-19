# E5 DELAY inbox: disposable demo check

This fixture covers the Dispatcher review and Send action in step 9. It creates
one synthetic approved order and one DELAY draft on a fresh PostgreSQL 16
database. It does not represent a live `PREDICTED_LATE` risk calculation or
the outbox worker's Mailpit delivery.

## Prepare

Use a private, untracked `.env` as described in [DEMO_SETUP.md](DEMO_SETUP.md).
For this fixture set `APP_ENV=test`, `DEMO_DISPOSABLE=1`,
`COMPOSE_PROJECT_NAME=cfo-demo-e5`, `APP_NOW=2026-11-09T11:00:00+01:00`,
`POSTGRES_PORT=5434`, `SOURCE_PORT=8104`, `CFO_API_PORT=8004`,
`CFO_WEB_PORT=5174`, `MAILPIT_HTTP_PORT=8027`, `MAILPIT_SMTP_PORT=1027`,
`VITE_API_URL=http://localhost:8004/api/v1`, and
`CORS_ORIGINS=["http://127.0.0.1:5174","http://localhost:5174"]`.
Omit `DEMO_D7_FIXTURE_DIR`: its separate fixed-clock fixture must not run
for E5. Keep the private database, JWT and demo account values from your local
configuration; never commit them.

In PowerShell from the repository root:

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
    [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), 'Process')
  }
}
docker compose -p cfo-demo-e5 up -d --build
python tools/e5_demo_fixture.py
python tools/e5_live_browser_smoke.py
docker exec cfo-demo-e5-postgres-1 psql -U cfo -d cfo -Atc `
  "SELECT id, template, status FROM ops.notification ORDER BY id"
```

The fixture prints `order_id=1`, `order_no=ZZ-000001`, and `draft_id=1`.
The browser smoke uses installed local Chrome in headless mode, logs in as the
synthetic dispatcher, checks the masked email and Stockholm ETA preview, clicks
**Send** once, and verifies `queued` in the UI and live API. It intentionally
prints no password, token, recipient, or message body. The PostgreSQL row is
`1|DELAY|queued`; `NOTIFICATION_SENT` appears only after the separate worker
sends the queued email.

For manual inspection, open `http://localhost:5174/notifications?order_id=1`,
log in as `user1@cfo.test` with your private `SEED_DEMO_PASSWORD`, and inspect
the saved preview before Send. The automated smoke consumes this draft; use a
new disposable Compose project/database for a clean replay. The fixture refuses
unrelated existing data or a second notification. Do not reset a shared stack.

## Observed on 2026-11-19

- Live HTTP login `200`; draft list `200`, `total=1`; detail `200`,
  `order_no=ZZ-000001`, `status=draft`, approved ETA `version=1`, masked
  recipient present.
- Headless Chrome displayed the order, masked recipient, Stockholm timezone and
  saved ETA preview. Clicking **Send** displayed “Queued for delivery”. Live
  detail and PostgreSQL both returned `queued` for notification `1`.
- The `PREDICTED_LATE` risk-to-draft path and queued-to-Mailpit worker path are
  **NOT VERIFIED** by this fixture; verify those during T08/E2 integration.
