# Sales Sync & Check local browser failure — 2026-11-09

## Scope and dependency

This fix is **stacked on PR #208** and changes local CFO API CORS + fail-closed Sales error handling, not the Source or approval contracts. No new business assumption is approved.

- Vite can start on `localhost:5174` if port `5173` is occupied.
- CFO API's default CORS accepted only `http://localhost:5173`; the browser therefore reported a network-style error on the `POST` preflight. The local `APP_ENV=local` API now admits only the additional exact origins `http://localhost:5174` and `http://127.0.0.1:5174`. Staging/demo/production origin policy is unchanged.
- **Separate hard dependency:** at PR #208's base, `POST /api/v1/integration/orders/sync-now` was **not registered** in the CFO router. Dev 2 [PR #204](https://github.com/qaztyhn/cfo-itconsultant/pull/204) provides the reviewed Source-to-CFO HTTP implementation and is Draft; this frontend/CORS hotfix **does not invent or backport the unmerged route**. A missing backend route is now reported as such, not as a scoped order 404 or fabricated success.

## Local verification (PowerShell)

1. Start the legitimate existing CFO API, Source and database with the repository's documented local setup, then inspect `docker compose ps`; don't bypass required environment variables, migrations or synthetic seed prerequisites.
2. Confirm CFO API health at `http://localhost:8000/api/v1/health` and check `http://localhost:8000/openapi.json` for the registered `/api/v1/integration/orders/sync-now` route (health alone does **not** prove this route exists).
3. From PowerShell verify browser preflight:

   ```powershell
   curl.exe -i -X OPTIONS "http://localhost:8000/api/v1/integration/orders/sync-now" -H "Origin: http://localhost:5174" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: authorization,content-type,idempotency-key,x-correlation-id"
   ```

   For `APP_ENV=local`, the expected response is HTTP 200 with `Access-Control-Allow-Origin: http://localhost:5174`. **Preflight success alone does not prove Sync & Check works.**
4. Open `http://localhost:5174/store/sync-check` and inspect DevTools Network after using a **synthetic** submitted POS reference:
   - `status 0` / failed fetch: check the configured `VITE_API_URL`, API availability and browser CORS.
   - `404` with a non-CFO error body: route is absent on the running backend; reviewed PR #204 must be integrated and the API restarted.
   - `404` with a structured CFO error: reference missing or outside store scope, not permission to read another store.
   - `403, 409, 422, 503`: preserve existing safe outcomes and idempotent retry rules. No automatic legacy choice/plan/approval on failure.

## Evidence limits

Local 5174 preflight and error-state regression tests are code-level tests in this PR; real Source → CFO PostgreSQL sync cannot pass against a backend without PR #204. Even with that API, planning/approval remains gated by proven worker duty and authoritative WMS reservation ACK. No real POS writes, production CORS expansion, remote URL change, secret disclosure, or auto-merge.
