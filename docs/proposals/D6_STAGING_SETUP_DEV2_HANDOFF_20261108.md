# D6 — Cloud staging setup / Dev 2 deployment handoff (CFO Sweden pilot)

**Prepared 2026-11-08. D6 status: technical setup proposal, NOT owner-approved account/region selection.** Owner asked for concrete setup instructions and Dev 2 handoff. Staging uses fully synthetic data only until D5 legal/compliance go-live gate. No credentials, real project refs, personal email addresses or access tokens in this file or PR.

## Target deployment

- **GitHub:** `qaztyhn/cfo-itconsultant`; deploy from **reviewed main** rather than open PR branches.
- **Supabase:** one staging PostgreSQL project `cfo-staging-se` with **specific** AWS region `eu-central-1` (Frankfurt) preferred (or `eu-north-1`, Stockholm if jointly chosen and available); CFO schemas and source `src_se` separate. This **differs** from local Docker Compose where source uses a separate DB. Set schema permissions and least-privilege roles where possible, not merely names. DB data region does not guarantee all processing/logs remain in EU.
- **Render:** two Docker web services in **Frankfurt**, **CFO API** root `backend` (existing Dockerfile listens 8000), **source API** root `source_system` (listens 8100). Source accessible over public HTTPS protected by `X-API-Key`; Render Free does NOT provide private networking and sleeps after 15min idle. Configure exact health check `/api/v1/health`. Verify Render port detection/`PORT`; do not assume deployment is healthy only because image built.
- **Vercel:** Vite/React static site from repo root-directory `frontend`, build `npm run build`, output `dist`, `VITE_API_URL=https://<CFO-API-HOST>/api/v1`; add `frontend/vercel.json` SPA rewrite for deep links. Do **not** put secrets in `VITE_*` because they are in public JS. Wait for Dev 3 PR #55 full merge and real-backend smoke; main frontend has stubs at the time of review.
- **Free tier warning:** Supabase Free can pause inactive projects after ~7 days and has no managed automatic database backups; Render Free sleeps after 15 minutes; Render Free quota 750 hours shared across services per month. Two always-running 24/7 services would need ~1,440 hours/month, so free is **not** a 24/7 staging SLA. Render Cron Jobs have a **minimum $1/month per cron service**; require explicit owner approval before enabling paid resources. No paid service silently provisioned.

## Owner actions (you do these in the vendor UIs)

1. **Supabase:** go to https://supabase.com/dashboard, choose/create staging organization and **New project**, name `cfo-staging-se`, choose **exact EU Central Frankfurt (`eu-central-1`)**, generate a strong DB password (never paste in GitHub/chat). Project **Connect → Session pooler**: Dev 2 needs the connection URI in the secure provider environment, not a copied PR. Invite Dev 2 with only the necessary project/organization role.
2. **Render:** https://dashboard.render.com → connect GitHub account/repo; create or give Dev 2 access to workspace. Dev 2 creates two Web Services (service names `cfo-api-se`, `cfo-source-se`) using existing Dockerfiles, Frankfurt region, branch `main`, backend/source root directories. Select approved cost tier; use Free only for intermittent demonstration; never treat it as reliable scheduler. Invite Dev 2 by supported provider roles, do not give shared account password.
3. **Vercel:** https://vercel.com/new → connect GitHub and import `qaztyhn/cfo-itconsultant`, set **Root Directory=frontend**, framework Vite, build `npm run build`, output `dist`. Dev 3 owns UI and Vite SPA rewrite, Dev 2 links CORS and API endpoint. Give team permissions rather than credentials. Vercel global CDN can access/process metadata outside a single DB region.
4. Share **only** project dashboard links, desired project names, selected regions, approval of Free vs paid and teammate invitations to Dev 2. **Never send DB URL/password, JWT key, API key, SMTP secret or seed password in chat, GitHub, commits, screenshots or PR comments.** Store them in Render/Vercel secret settings and secure approved migration runner.

## Environment contracts (from the actual repo)

```dotenv
# Render cfo-api-se / backend (secrets are injected privately)
DATABASE_URL=<postgresql+asyncpg Session-pooler URI from Supabase>
JWT_SECRET=<strong independent secret>
INTERNAL_TICK_KEY=<strong independent secret>
SOURCE_SE_BASE_URL=https://<source-service-host>.onrender.com/api/v1
SOURCE_SE_API_KEY=<same secret as source API API_KEY>
ORS_API_KEY=<optional private ORS key>
APP_ENV=staging
# APP_NOW: UNSET, never freeze the clock in shared staging
CORS_ORIGINS=["https://<frontend-host>.vercel.app"]
# SMTP external production sending disabled; use only approved test recipients
SMTP_ALLOWED_RECIPIENT_DOMAINS=test

# Render cfo-source-se / source_system
DATABASE_URL=<postgresql+asyncpg Session-pooler URI; separate DB role preferable>
SOURCE_SCHEMA=src_se
API_KEY=<same secret as CFO SOURCE_SE_API_KEY>
# APP_NOW: UNSET

# Vercel / frontend: PUBLIC settings only, no credentials
VITE_API_URL=https://<cfo-api-host>.onrender.com/api/v1
# VITE_APP_ENV=demo only AFTER Dev 3 confirms this feature on main and approval
# VITE_POS_URL=... only after source POS UI URL is verified
```

**Connection footgun:** Source `source_system/app/config.py` **requires** driver scheme `postgresql+asyncpg` and validates a separate `SOURCE_SCHEMA`. Supabase Session pooler URI is typically displayed as `postgresql://...`; Dev 2 must adapt the scheme only, preserve the exact username/hostname/port from the Supabase Connect panel, configure TLS as supported, and test both apps. Session pooler (port often 5432) supports ORM prepared statements and IPv4; **do not casually switch to transaction pooler 6543**, which has prepared-statement/session-behavior constraints. Test advisory locks and migrations in shared staging DB; use least-privilege DB roles. Never print real URIs.

**CORS footgun:** `backend/app/core/config.py` parses `CORS_ORIGINS` as Pydantic `list[str]`; use a JSON array string, not a comma-separated string. Example above. Set the actual Vercel origin once assigned, not `*`.

**Port/worker footgun:** existing Dockerfiles hard-code uvicorn 8000/8100. Have Dev 2 validate Render detects/listens to those ports and update/parameterize Docker CMD if required. Current `backend/app/main.py` does not itself start APScheduler (docstring does not equal implementation); `backend/app/jobs/scheduler.py` and `backend/app/api/v1/internal.py` contain stubs. No scheduler SLA until D8 implementation and a reliable worker/cron strategy, with approval for any paid compute.

## Explicit initialization/deployment order for Dev 2

1. On reviewed `main`, run CI; verify no unmerged business-contract changes are required. Avoid deployment of TODO stubs as if complete.
2. Configure database connectivity using **approved secrets** in a secure migration runner. **Do not** run migration automatically on every Render web-service startup (race risk); use one controlled deployment step.
3. `cd backend && alembic upgrade head` — build CFO schema `ref/hr/stg/ops/plan/audit`. Confirm installed migrations and constraints. Apply migrations with a role authorized for necessary extension/schema changes.
4. `cd source_system && python -m app.init_db` with `SOURCE_SCHEMA=src_se` and source-role credentials — additive source schema bootstrap. This is **not** run automatically by `app.main`.
5. Seed approved, deterministic *synthetic* reference data via relevant repo modules, in correct order (e.g. `python -m app.seed.reference_demo`, `python -m app.seed.m0_accounts` with `SEED_DEMO_PASSWORD`, source `python -m app.seed_reference`). Do not claim M1–M9 scenario seed complete if it still contains stubs. Never commit the seed password; use managed secrets.
6. Deploy **Source API** first, verify `GET /api/v1/health` and a protected `GET /api/v1/stock` with test API key; browser without API key must not access protected endpoints.
7. Deploy **CFO API** second, set `SOURCE_SE_BASE_URL` to actual Source HTTPS URL and `SOURCE_SE_API_KEY` to the Source's `API_KEY`; test `GET /api/v1/health`, `/docs`, protected role gates, source fetch and Pydantic settings.
8. After Dev 3 frontend PR #55 is merged, deploy Vercel `frontend`. Configure `VITE_API_URL`, add SPA rewrite, update CORS to the exact Vercel host, verify refresh at `/store/orders` and login with approved synthetic accounts. Verify hard-coded localhost endpoints are absent from production bundle and no secret is exposed in JS.
9. Disable real customer email; use synthetic recipient + Mailpit/staging allowlist only per `DEC-NOTIFY-001`. GPS demo is synthetic and consent/privacy warning is visible where needed. No production customer data.
10. Job scheduling: until D8 is approved and implemented, **manual operational run with evidence**; do not claim 5min sync/1min hold expiry works on a sleeping Free web process. A reliable cron or always-on worker requires an explicit cost and provider decision.
11. Capture exact HEAD SHA, URLs (public only), DB migration version (not secrets), seed version, smoke test outcomes, known limitations, backup/restore procedure and who has access. Do a staging restart and at least one clean redeploy with repeatable seed.
12. Provide read-only demo access to reviewers via **individual demo credentials**, not database administration or shared cloud-owner credentials.

## Acceptance / handoff checklist

- [ ] Owner created/chose Supabase, Render, Vercel projects and invited Dev 2/Dev 3, selected exact region, accepted any costs
- [ ] Secrets only in provider settings/secure migration runner, password rotation plan documented
- [ ] Supabase session pooler tested using `postgresql+asyncpg`; CFO/Source isolation and schema verified
- [ ] CFO Alembic head migrated; source `src_se` initialized; reference and approved demo seed repeatable
- [ ] Both Render services pass HTTPS health checks; source protected with X-API-Key
- [ ] Frontend Vite built and integrated with **real** CFO API, no localhost in bundle, SPA reload works
- [ ] CORS exact origin, RBAC, 401/403/422, secret redaction and synthetic-only GDPR staging gate confirmed
- [ ] Scheduler/hold expiry/ingestion verified **for the actual hosting tier** or explicitly marked NOT READY
- [ ] No real external email / real employee GPS; documented data lifecycle and clean test reset
- [ ] CI + Postgres integration tests + manual E2E POS→source→sync→CFO plan→approve→trip reviewed; known unfinished features are clearly marked
- [ ] DPA/subprocessor and transfer review recorded before any live-personal-data pilot

## Assignments

- **Owner:** choose provider projects, specific EU region, free-vs-paid boundaries; grant project access (no password sharing).
- **Dev 2 — D6 implementer:** create hosted services in authorized accounts, secret wiring and DB migrations, source schema+seed, CORS/API connections, test-safe SMTP, health/monitoring, safe scheduler proposal with D8 handoff, backup/restore evidence, README deployment guide and rollout PR. Cross-check GDPR D5.
- **Dev 1:** validate SQL migrations, advisory locks, source read ingestion and T14/T15/T16 behavior; no claim of full automated approval or scheduler completion from a green deploy.
- **Dev 3:** fix/merge #55, browser smoke/SPA fallback/PWA, production URLs and no raw PII in client log; integrate actual backend and review auth.
- **Legal/privacy owner:** approve retention and actual real-data purpose, DPA/transfer review, employee GPS DPIA if necessary.

## Current vendor documentation (2026-11-08)

- Supabase regions https://supabase.com/docs/guides/platform/regions
- Supabase connection modes https://supabase.com/docs/guides/database/connecting-to-postgres
- Supabase Free pause https://supabase.com/docs/guides/platform/free-project-pausing
- Supabase backups https://supabase.com/docs/guides/platform/backups
- Render web services https://render.com/docs/web-services
- Render regions https://render.com/docs/regions
- Render free tier https://render.com/docs/free
- Render Cron Jobs (paid, minimum fee) https://render.com/docs/cronjobs
- Vercel monorepos https://vercel.com/docs/monorepos
- Vercel Vite SPA rewrite https://vercel.com/docs/frameworks/frontend/vite
