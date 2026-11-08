/** Contract-only preview records. Never used in a production build or for operational decisions. */
import type { OverviewResponse, RejectsResponse, SyncRunsResponse } from "./contracts";

export const CONTRACT_OVERVIEW: OverviewResponse = {
  sources: {
    orders: { status: "ok", rows: 12, rejected: 0, last_run_at: "2026-11-04T09:05:00Z", data_as_of: "2026-11-04T09:00:00Z" },
    stock: { status: "ok", rows: 321, rejected: 0, last_run_at: "2026-11-04T09:05:00Z" },
    inbound: { status: "partial", rows: 8, rejected: 2, last_run_at: "2026-11-04T08:55:00Z", data_as_of: "2026-11-04T08:50:00Z" },
    products: { status: "ok", rows: 96, rejected: 0, unmapped: 3, last_run_at: "2026-11-04T09:00:00Z", data_as_of: "2026-11-04T08:57:00Z" },
    fleet: { status: "failed", rows: null, rejected: null, last_run_at: "2026-11-04T08:54:00Z" },
  },
  route_matrix: { pairs: 25, fallback_pairs: 2, provider: "ors", fetched_at: "2026-11-04T08:40:00Z" },
  // Deliberately no scheduler: D8 job/heartbeat contract is unapproved.
};

export const CONTRACT_RUNS: SyncRunsResponse = {
  items: [
    { id: 304, entity: "orders", status: "ok", kind: "api", started_at: "2026-11-04T09:05:00Z",
      finished_at: "2026-11-04T09:05:20Z", checkpoint_from: "2026-11-04T09:00:00Z",
      checkpoint_to: "2026-11-04T09:05:00Z", rows_in: 12, rows_ok: 12, rows_rejected: 0 },
    { id: 303, entity: "products", status: "ok", kind: "api", started_at: "2026-11-04T09:00:00Z",
      finished_at: "2026-11-04T09:00:10Z", rows_in: 96, rows_ok: 96, rows_rejected: 0 },
    { id: 302, entity: "inbound", status: "partial", kind: "api", started_at: "2026-11-04T08:55:00Z",
      finished_at: "2026-11-04T08:55:15Z", rows_in: 10, rows_ok: 8, rows_rejected: 2 },
    { id: 301, entity: "fleet", status: "failed", kind: "api", started_at: "2026-11-04T08:54:00Z",
      finished_at: "2026-11-04T08:54:08Z", rows_in: 0, rows_ok: 0, rows_rejected: 0 },
    { id: 300, entity: "fleet", status: "ok", kind: "api", started_at: "2026-11-04T08:00:00Z",
      finished_at: "2026-11-04T08:00:07Z", rows_in: 3, rows_ok: 3, rows_rejected: 0 },
  ],
};
export const CONTRACT_REJECTS: RejectsResponse = {
  items: [
    { id: 51, run_id: 302, reason_code: "BAD_DATE",
      reason: "SENSITIVE: phone and address", raw: { customer_name: "PRIVATE" } },
    { id: 52, run_id: 302, reason_code: "UNKNOWN_SKU",
      external_key: "PRIVATE-ORDER-REFERENCE", raw: { contact_email: "redacted@example.test" } },
  ],
};
