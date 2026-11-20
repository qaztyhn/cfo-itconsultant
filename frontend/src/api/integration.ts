/**
 * Nguồn "Data as of" cho Plan Review (docs/03 mục 3.1, 5.2). Owner: Dev 3 (luồng C).
 * Dispatcher nhận mốc tồn kho của market mình từ API.
 */
import { apiGet } from "./client";

export interface IntegrationOverview {
  sources?: { name: string; data_as_of?: string | null }[] | { stock?: { data_as_of?: string | null } };
  next_sync_at?: string | null;
  stale?: boolean;
}

export function fetchIntegrationOverview(signal?: AbortSignal): Promise<IntegrationOverview> {
  return apiGet<IntegrationOverview>("/integration/overview", undefined, signal);
}

export interface Freshness {
  asOf: string | null;
  nextSyncAt: string | null;
  stale: boolean;
}

/** asOf = mốc cũ nhất trong các nguồn. Cờ `stale` của server được ưu tiên; không có thì so với ngưỡng stale_stock_min (15). */
export function summariseFreshness(overview: IntegrationOverview, nowMs = Date.now(), staleAfterMin = 15): Freshness {
  const sources = overview.sources;
  const feeds = Array.isArray(sources) ? sources : sources?.stock ? [sources.stock] : [];
  const times = feeds
    .map((s) => (s.data_as_of ? new Date(s.data_as_of).getTime() : NaN))
    .filter((t) => Number.isFinite(t));
  const oldest = times.length > 0 ? Math.min(...times) : null;
  const stale = overview.stale ?? (oldest === null ? true : nowMs - oldest > staleAfterMin * 60_000);
  return {
    asOf: oldest === null ? null : new Date(oldest).toISOString(),
    nextSyncAt: overview.next_sync_at ?? null,
    stale,
  };
}