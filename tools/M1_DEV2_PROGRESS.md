# Dev 2 — M1 progress (2026-11-07)

Branch: `feat/m1-source-auth`, based on the Dev 2 M0 branch (PR #41).
Skill: `.agents/skills/cfo-dev2-integration/SKILL.md`.

## Completed slice: source authentication

Implements the X-API-Key requirement of 06 section 16, supporting the shared
source contract in US-SRC-02 AC1 / BR-GEN-02. Business routes require the
instance's API_KEY; health remains public for Docker probes. Missing header
returns 400 VALIDATION_ERROR (06 section 1.1); wrong key returns 401 AUTH_INVALID.
An unconfigured or blank server key never authorizes a request. Comparison uses
constant-time comparison, credentials are excluded from configuration repr, and
auth errors contain no credential values. Errors return a valid correlation ID.

OpenAPI generated at runtime declares header security on every business route.
`source_system/openapi.yaml` is still a placeholder pending completion and review
of the full API contract; this slice does not claim US-SRC-02 is complete.
Authenticated business handlers still raise NotImplementedError until their
respective M1 implementation. No M2 ingestion or POS behavior is claimed.

Changed implementation/tests:
- source_system/app/auth.py
- source_system/app/api.py
- source_system/app/config.py
- source_system/app/main.py
- source_system/tests/unit/test_auth.py

## Verification

- Source Ruff, Black and mypy: PASS.
- `pytest tests/unit`: 41 passed.
- `python tools/harness.py verify`, with SOURCE_TEST_DATABASE_URL pointing to a
  new PostgreSQL 16 tmpfs container: source 46 passed, including five real DB
  tests; frontend lint/test/build PASS; backend static gates PASS.
- Overall Harness: FAIL on the existing Windows Alembic INI locale-decoding
  error. Backend pytest: 1 failed, 159 passed, 110 skipped. TEST_DATABASE_URL was
  not configured for CFO in this source-focused run; the 110 skipped tests are
  NOT VERIFIED, not counted as passes. No checks were removed or weakened.
- Only the new test container was stopped; existing data/volumes were untouched.
- Docker application-image rebuild and full five-service smoke for this M1
  slice: NOT VERIFIED. API authorization was exercised through FastAPI TestClient;
  source database/health regression tests used real PostgreSQL.

## Contract handoff and next tasks

The project owner requested a proposal before contract implementation:
`docs/proposals/M1_SOURCE_CONTRACT.md` lists the decisions awaiting approval.
It does not edit the approved specifications or authorize schema changes.

1. Dev 1 + Dev 3 review order snapshots, draft/write DTOs, validation errors,
   lifecycle/version behavior, receiving calendars and cancellation delivery.
2. After approval, Dev 2 updates specs/CHANGELOG and builds the source DTOs,
   PostgreSQL endpoints and OpenAPI contract tests for two instances.
3. Dev 2 adds the complete deterministic M1 seed (US-SRC-01), then add_market
   (US-INT-04), and M2 REST/CSV ingestion. Dev 3 owns POS UI.

Full M1/M2 are not complete. The Windows Alembic configuration failure recorded
above was resolved upstream and integrated from main `527e26d` on 2026-11-07.
The encoding regression and ConfigParser DSN test now pass on Windows.
See `tools/M2_DEV2_STOCK_ADAPTER.md` for the subsequent full verification.
No migration/auth/planning implementation in CFO was edited by this slice.
