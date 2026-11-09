/**
 * Polling hook for the Prep Queue (docs/09 §9: 15–30 s, no WebSocket). Read-only.
 * - Same warehouse/date: TanStack Query keeps `data` during a refetch, so open dialogs and forms are not reset.
 * - Different warehouse/date: new query key and NO placeholder data, so another warehouse's queue is never shown.
 * - `retry: false`: the 20 s poll is the retry; 401/403/404 stop polling so the permission/not-found state is stable.
 * Owner: Dev 3 (stream C) — M6.
 */
import { useQuery } from "@tanstack/react-query";
import { isApiError } from "../../../api/client";
import { fetchPrepQueue, prepQueueKey } from "./api";

export const PREP_QUEUE_POLL_MS = 20_000;
const FINAL_STATUSES = [401, 403, 404];

export function pollInterval(error: unknown): number | false {
  return isApiError(error) && error.status !== undefined && FINAL_STATUSES.includes(error.status) ? false : PREP_QUEUE_POLL_MS;
}

export function usePrepQueue(warehouseId: number | null, date: string | null) {
  return useQuery({
    queryKey: prepQueueKey(warehouseId, date),
    queryFn: ({ signal }) => {
      if (warehouseId === null || !date) {
        throw new Error("Prep queue query is disabled");
      }
      return fetchPrepQueue({ warehouse_id: warehouseId, date }, signal);
    },
    enabled: warehouseId !== null && !!date,
    retry: false,
    refetchInterval: (query) => pollInterval(query.state.error),
  });
}