# D1 reference/calendar read transport handoff

Implements DEC-SRC-D1-001 reference reads for the transport portion of US-INT-01/03/04
(BR-ORD-01, BR-GEN-02). No claim of the database synchronization ACs being complete.

- Addresses preserve customer identity, optional coordinates and explicit receiving slots.
  Missing schedule stays unknown; an empty schedule stays closed. Never infer 24/7.
- Inbound preserves composite identity, exact Decimal quantity, confirmation, received flag
  and source update time. Already received deliveries must not be counted as future inbound.
- Fleet preserves full overlapping busy intervals and stable composite ordering. The existing
  date-based adapter method uses `[date_from, date_to)` market-local midnight boundaries;
  `date_to` is exclusive. Caller must configure the actual `ref.market.timezone` through
  `AdapterRegistry.configure(market_timezone=...)`; absent/invalid timezone fails closed.
  UTC durations across DST differ from nominal calendar-day durations.
- All feeds use shared count/header/page/duplicate/checkpoint guards. Optional inbound/fleet
  checkpoints are sent only when supplied; no timestamp is invented by this transport.

Dev 1/2 integration still needs scoped warehouse/vehicle mapping, durable per-feed checkpoints
with overlap, row upserts/rejects and transactional run status. Source holidays/receiving-calendar
coverage are distinct from CFO warehouse/driver rosters; address slots alone do not provide
calendar completeness or a five-gate planning proof. No source writes, routing/approval decision,
database migration, external service call or scheduler activation is introduced.

Validation: backend adapter strict mypy, Ruff, Black and full unit tests; focused cases cover
unknown receiving data, malformed slots, multi-page inbound, composite ordering/duplicates,
aware intervals and the Stockholm DST boundary. Hosted CI is tracked in the PR.

Assumptions: reviewed; DEC-SRC-D1-001; none new. Stacked after the order/pool transport PRs.
