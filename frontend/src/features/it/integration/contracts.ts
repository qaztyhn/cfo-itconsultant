/**
 * M2 Data Integration read DTOs.
 *
 * Structural types mirror docs/05 §5 and docs/06 §15/Appendix A until an
 * approved generated OpenAPI schema replaces the admin NotImplemented stubs.
 * Fields from backend are UNTRUSTED; project only allowlisted data in model.ts.
 */
export const FEEDS = [
  { entity: "orders", title: "POS orders", source: "POS" },
  { entity: "stock", title: "WMS stock", source: "WMS" },
  { entity: "inbound", title: "WMS inbound", source: "WMS" },
  { entity: "products", title: "ERP products", source: "ERP" },
  { entity: "fleet", title: "Fleet calendar", source: "Fleet" },
] as const;

export type FeedEntity = (typeof FEEDS)[number]["entity"];
export type RunStatus = "ok" | "partial" | "failed" | "running";
export interface OverviewSource {
  availability?: unknown;
  status?: unknown;
  last_run_status?: unknown;
  last_successful_at?: unknown;
  rows?: unknown;
  rejected?: unknown;
  unmapped?: unknown;
  last_run_at?: unknown;
  data_as_of?: unknown;
  interval_min?: unknown;
}
export interface OverviewResponse {
  market?: unknown;
  markets?: OverviewResponse[];
  sources?: Record<string, OverviewSource>;
  entities?: Record<string, OverviewSource>;
  route_matrix?: {
    pairs?: unknown;
    fallback_pairs?: unknown;
    fetched_at?: unknown;
    provider?: unknown;
  };
  scheduler?: {
    tick_interval_min?: unknown;
    last_tick_at?: unknown;
    last_tick_status?: unknown;
    jobs?: unknown;
  };
}
export interface SyncRunResponse {
  id: unknown;
  entity: unknown;
  kind?: unknown;
  status?: unknown;
  started_at?: unknown;
  finished_at?: unknown;
  data_as_of?: unknown;
  checkpoint_from?: unknown;
  checkpoint_to?: unknown;
  file_name?: unknown;
  rows_in?: unknown;
  rows_ok?: unknown;
  rows_rejected?: unknown;
  error?: unknown;
}
export interface SyncRunsResponse {
  items?: SyncRunResponse[];
  total?: unknown;
}
export interface RejectResponse {
  id?: unknown;
  run_id?: unknown;
  external_key?: unknown; // NEVER render: may contain an order/customer identifier
  reason_code?: unknown;
  reason?: unknown; // NEVER render: free text may contain PII
  raw?: unknown; // NEVER render: raw source record may contain customer PII
}
export interface RejectsResponse {
  items?: RejectResponse[];
}
