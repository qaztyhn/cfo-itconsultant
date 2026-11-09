/** M2 hook: independent source/runs/reject queries, with per-section retry. */
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../../../api/client";
import { USE_MOCKS } from "../../../api/config";
import { isAdmin } from "../../../app/access";
import { useAuthStore } from "../../../app/store";
import type { OverviewResponse, RejectsResponse, SyncRunsResponse } from "./contracts";
import { CONTRACT_OVERVIEW, CONTRACT_REJECTS, CONTRACT_RUNS } from "./contractPreview";
import {
  normalizeMatrix,
  normalizeRejects,
  normalizeRuns,
  normalizeScheduler,
  normalizeSources,
} from "./model";

export function useIntegrationDashboard(runId: number | null, selectedMarket: string | null) {
  const user = useAuthStore((state) => state.user);
  const allowed = Boolean(user && isAdmin(user));
  const identity = [user?.id ?? null, user?.market ?? null];
  const market = user?.market ?? selectedMarket;

  const overviewQuery = useQuery({
    queryKey: ["it-integration", "overview", ...identity],
    enabled: allowed,
    retry: false,
    queryFn: ({ signal }) => USE_MOCKS
      ? Promise.resolve(CONTRACT_OVERVIEW)
      : apiGet<OverviewResponse>("/integration/overview", undefined, signal),
  });
  const runsQuery = useQuery({
    queryKey: ["it-integration", "runs", ...identity, market],
    enabled: allowed && Boolean(market),
    retry: false,
    queryFn: ({ signal }) => USE_MOCKS
      ? Promise.resolve(CONTRACT_RUNS)
      : apiGet<SyncRunsResponse>("/sync-runs", { market }, signal),
  });
  const rejectsQuery = useQuery({
    queryKey: ["it-integration", "rejects", ...identity, market, runId],
    enabled: allowed && Boolean(market) && runId !== null,
    retry: false,
    queryFn: ({ signal }) => USE_MOCKS
      ? Promise.resolve(runId === 302 ? CONTRACT_REJECTS : { items: [] })
      : apiGet<RejectsResponse>(`/sync-runs/${runId}/rejects`, { market }, signal),
  });

  const overviewResponse = overviewQuery.data ?? null;
  const markets = Array.isArray(overviewResponse?.markets) ? overviewResponse.markets
    .filter((entry): entry is OverviewResponse => typeof entry?.market === "string") : [];
  const overview = markets.length ? markets.find((entry) => entry.market === market) ?? null : overviewResponse;
  const runs = normalizeRuns(runsQuery.data);
  return {
    allowed,
    isPreview: USE_MOCKS,
    overviewQuery,
    runsQuery,
    rejectsQuery,
    markets: markets.map((entry) => entry.market as string),
    sources: normalizeSources(overview, runs),
    runs,
    rejects: normalizeRejects(rejectsQuery.data),
    matrix: normalizeMatrix(overview),
    scheduler: normalizeScheduler(overview),
  };
}
