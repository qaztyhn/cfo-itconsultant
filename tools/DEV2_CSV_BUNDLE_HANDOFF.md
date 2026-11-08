# D2 offline CSV boundary

DEC-DEV2-D2-001 authorizes the CSV encoding/schema/hash/retry policy. This task supplies
the private offline reader in `app.adapters.csv_bundle`, not a public upload contract or
database importer. It supports the fallback part of US-INT-01/03 (BR-ORD-01) only.

The reviewable local manifest uses `schema_version: "1"`, `market`, `entity`, ISO-aware
`captured_at` and `files: [{role, path, sha256}]`. Paths are relative to the manifest;
each exact file byte stream is bounded, hash-verified and decoded as UTF-8 (optional BOM).
Headers are supplied by the trusted versioned entity decoder; the upload cannot define its
own columns. RFC4180 quoted commas/newlines are preserved. Malformed record lengths emit
only role, record number and machine code; file-level structure/hash/scope failures abort.
No filenames, cells, contacts, secrets or source error bodies appear in exceptions.

The reader has configurable technical size/row limits, rejects escaped paths/duplicate roles,
and returns source records plus explicit rejects. It does not silently discard rejects or
declare a partial batch complete. Manifest/column candidates require Dev 1/3 review before
an upload API is enabled; no routes, permissions or CFO schemas change here.

`retry_action` implements the approved decision table only: prior ok skips; failed starts
a new recorded run; partial requires IT review; running conflicts. The future caller must
scope file hashes by market/entity/schema version and enforce this under transaction locks.
It must preserve previous runs and record audit. This helper is not a dedupe/run repository.

## Integration dependencies

Dev 1 must hand off a migration/index supporting schema version and repeated failed/partial
file runs in `stg.sync_run`. The existing unique hash storage is insufficient. Dev 2 can then
connect typed entity decoding, natural-key/source-version upserts, line referential rejects,
stock completeness/pool normalization and durable checkpoint rules. IT-only upload/RBAC,
transactional audit and concurrent retry integration tests must precede an API acceptance claim.
Never route orders or approve plans merely because a CSV has been read successfully.

Validation: focused unit cases for BOM, quoted newline, malformed UTF-8/CSV/header, hash,
scope/version/timezone, traversal, duplicate roles, size/row limits and every retry outcome;
Ruff, Black and strict adapter mypy. Full test/CI results are in the PR.

Assumptions: reviewed; DEC-DEV2-D2-001; none new. No source writeback or scheduler activation.
