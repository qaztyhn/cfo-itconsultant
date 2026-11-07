# Dev 2 — stock adapter slice

Branch: `feat/m2-source-stock-adapter`, based on M1 source authentication with
main `527e26d` integrated. This includes the upstream Alembic ASCII fix and the
Sales sync-now specification; no Sales approval code is changed here.

## Implemented

`RestMarketAdapter.fetch_stock()` reads the exact stock snapshot shape in 06
section 16 and returns the existing `StockSnapshotDTO`. This supports the
transport portion of US-INT-03 AC1 / FR-INT-06, not its persistence acceptance.

- GET only, with per-instance API key and an injectable finite timeout.
- Reject redirects rather than forwarding credentials to another destination.
- Preserve fractional quantities as Decimal directly from JSON, and require
  an aware source timestamp; empty snapshots preserve their source timestamp.
- Reject malformed responses, nonfinite quantities and duplicate natural keys
  before returning any snapshot to the caller.
- HTTP/transport/validation errors are sanitized SourceReadError exceptions;
  no response bodies, URLs or credentials are included in error messages.
- Identical behavior for SE and DK. No network access from the engine.

No endpoint, database schema or DTO contract is changed. No dependency was added.
The adapter is still partial: other feeds and registration as a complete
MarketAdapter remain future work. Nothing writes source data or CFO reservations.

## Verification

Targeted command: pytest for `test_rest_stock_adapter.py`,
`test_alembic_ini_encoding.py` and the percent-encoded Alembic ConfigParser test:
33 passed. Targeted Ruff, Black and mypy passed.

`python tools/harness.py verify`: **HARNESS PASS** on Windows / Python 3.12,
after integrating main `527e26d` and the new adapter:
- Backend: 302 passed, no skipped tests; Ruff/Black/mypy/import-linter PASS.
- Source: 46 passed, including real PostgreSQL tests; Ruff/Black/mypy PASS.
- Frontend: lint, test (1 passed), build PASS.

Both TEST_DATABASE_URL and SOURCE_TEST_DATABASE_URL were set to a newly created
PostgreSQL 16 tmpfs instance; backend fixtures created their own temporary DBs.
The test container was stopped afterwards. Existing data/volumes were untouched.
External source transport tests use httpx.MockTransport; no live source /stock
or full five-service Docker smoke was claimed for this adapter slice.

## Remaining integration

Source /stock is still a stub pending the snapshot-batch decision (SRC-Q9).
The source-contract proposal remains pending; main's Sales decision does not
approve the separate source schema/response proposal.
Next steps: source snapshot implementation after approval, then ingestion upsert,
checkpoint/reject/run bookkeeping and stale-data handling. Full M1 and M2 remain
incomplete; sync-now depends on the orders feed and shared ingestion.
