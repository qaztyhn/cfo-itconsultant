/**
 * Read-only adapter for `GET /prep-queue?warehouse_id=&date=` (docs/06 Appendix A).
 * DEPENDENCY: docs/06 §8.2 and docs/03 §5.6 list `/warehouses/{id}/prep-queue` instead; Appendix A is followed because it
 * defines the payload. Confirm the final path with Dev 1 before integration.
 * Owner: Dev 3 (stream C) — M6.
 */
import { ApiError, apiGet } from "../../../api/client";
import type { PrepQueueParams, PrepQueueResponse } from "./types";

export const PREP_QUEUE_PATH = "/prep-queue";

export const prepQueueKey = (warehouseId: number | null, date: string | null) => ["prep-queue", warehouseId, date] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Minimal shape check so a broken payload becomes an error state instead of a crash. */
export function parsePrepQueueResponse(payload: unknown): PrepQueueResponse {
  if (isRecord(payload) && isRecord(payload.capacity) && Array.isArray(payload.capacity.shifts) && Array.isArray(payload.orders)) {
    return payload as unknown as PrepQueueResponse;
  }
  throw new ApiError("INVALID_RESPONSE", "The server returned an unexpected prep queue response.");
}

export async function fetchPrepQueue(params: PrepQueueParams, signal?: AbortSignal): Promise<PrepQueueResponse> {
  const payload = await apiGet<unknown>(PREP_QUEUE_PATH, { warehouse_id: params.warehouse_id, date: params.date }, signal);
  return parsePrepQueueResponse(payload);
}