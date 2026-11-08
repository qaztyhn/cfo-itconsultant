/** M2 hook: independent source/runs/reject queries, with per-section retry. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, ApiError } from "../../../api/client";
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

export function useIntegrationDashboard(runId: number | null) {
  const user = useAuthStore((state) => state.user);
  const allowed = Boolean(user && isAdmin(user));
  const identity = [user?.id ?? null, user?.market ?? null];
  const queryClient = useQueryClient();

  const overviewQuery = useQuery({
    queryKey: ["it-integration", "overview", ...identity],
    enabled: allowed,
    retry: false,
    queryFn: ({ signal }) => USE_MOCKS
      ? Promise.resolve(CONTRACT_OVERVIEW)
      : apiGet<OverviewResponse>("/integration/overview", undefined, signal),
  });
  const runsQuery = useQuery({
    queryKey: ["it-integration", "runs", ...identity],
    enabled: allowed,
    retry: false,
    queryFn: ({ signal }) => USE_MOCKS
      ? Promise.resolve(CONTRACT_RUNS)
      : apiGet<SyncRunsResponse>("/sync-runs", undefined, signal),
  });
  const rejectsQuery = useQuery({
    queryKey: ["it-integration", "rejects", ...identity, runId],
    enabled: allowed && runId !== null,
    retry: false,
    queryFn: ({ signal }) => USE_MOCKS
      ? Promise.resolve(runId === 302 ? CONTRACT_REJECTS : { items: [] })
      : apiGet<RejectsResponse>(`/sync-runs/${runId}/rejects`, undefined, signal),
  });
  const manualSync = useMutation({
    mutationFn: () => {
      if (!allowed) return Promise.reject(new ApiError("FORBIDDEN", "Admin access required.", undefined, undefined, 403));
      if (USE_MOCKS) return Promise.reject(new ApiError("CONTRACT_PREVIEW", "Preview cannot start a sync."));
      // The documented admin contract is a single-entity POST. Do not
      // call unsupported "run all", CSV upload, stock or routing write paths.
      return apiPost<unknown>("/sync/orders/run");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["it-integration"] });
    },
  });

  const overview = overviewQuery.data ?? null;
  const runs = normalizeRuns(runsQuery.data);
  return {
    allowed,
    isPreview: USE_MOCKS,
    overviewQuery,
    runsQuery,
    rejectsQuery,
    manualSync,
    sources: normalizeSources(overview, runs),
    runs,
    rejects: normalizeRejects(rejectsQuery.data),
    matrix: normalizeMatrix(overview),
    scheduler: normalizeScheduler(overview),
  };
}
