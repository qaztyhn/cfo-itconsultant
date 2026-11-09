/**
 * Read-only adapter for the canonical `GET /warehouses/{id}/prep-queue?date=YYYY-MM-DD` (docs/06 §8.2, Appendix A.1,
 * owner-approved PROPOSAL-M6-PREP-QUEUE-001). The legacy `/prep-queue?warehouse_id=` is only a backend alias.
 * Owner: Dev 3 (stream C) — M6.
 */
import { ApiError, apiGet } from "../../../api/client";
import type { PrepQueueParams, PrepQueueResponse } from "./types";

export const prepQueuePath = (warehouseId: number): string => `/warehouses/${warehouseId}/prep-queue`;

export const prepQueueKey = (warehouseId: number | null, date: string | null) => ["prep-queue", warehouseId, date] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Minimal shape check so a broken payload becomes an error state instead of a crash. */
export function parsePrepQueueResponse(payload: unknown): PrepQueueResponse {
  // `schedule_verified` is a required boolean (A.1): a missing/non-boolean value is a broken contract, never "verified".
  if (
    isRecord(payload) &&
    isRecord(payload.capacity) &&
    typeof payload.capacity.schedule_verified === "boolean" &&
    Array.isArray(payload.capacity.shifts) &&
    Array.isArray(payload.orders)
  ) {
    return payload as unknown as PrepQueueResponse;
  }
  throw new ApiError("INVALID_RESPONSE", "The server returned an unexpected prep queue response.");
}

export async function fetchPrepQueue(params: PrepQueueParams, signal?: AbortSignal): Promise<PrepQueueResponse> {
  const payload = await apiGet<unknown>(prepQueuePath(params.warehouse_id), { date: params.date }, signal);
  return parsePrepQueueResponse(payload);
}