/**
 * Local MSW handlers for tests of the Prep Queue. Deliberately NOT added to the shared `api/mocks/handlers.ts`.
 * Owner: Dev 3 (stream C) — M6.
 */
import { http, HttpResponse } from "msw";
import { API_BASE_URL } from "../../../api/config";
import { buildPrepQueueFixture } from "./fixtures";
import type { PrepQueueResponse } from "./types";

export const PREP_QUEUE_URL = `${API_BASE_URL}/warehouses/:id/prep-queue`;

export interface PrepQueueRequest {
  warehouse_id: number | null;
  date: string | null;
}

export function errorBody(code: string, message: string, correlationId: string) {
  return { error: { code, message, details: {}, correlation_id: correlationId } };
}

/** Returns `response` for a valid query; 422 when `warehouse_id` or `date` is missing or malformed (docs/06 §1.1). */
export function prepQueueSuccess(response: PrepQueueResponse = buildPrepQueueFixture("verified"), onRequest?: (request: PrepQueueRequest) => void) {
  return http.get(PREP_QUEUE_URL, ({ request, params }) => {
    const url = new URL(request.url);
    const rawId = typeof params.id === "string" ? params.id : null;
    const date = url.searchParams.get("date");
    const warehouseId = rawId !== null && /^\d+$/.test(rawId) ? Number(rawId) : null;
    onRequest?.({ warehouse_id: warehouseId, date });
    if (warehouseId === null || !date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return HttpResponse.json(errorBody("VALIDATION_ERROR", "warehouse id and date (YYYY-MM-DD) are required", "corr-prep-422"), { status: 422 });
    }
    return HttpResponse.json(response);
  });
}

export function prepQueueFailure(status: number, code: string, message: string, correlationId = "corr-prep-test") {
  return http.get(PREP_QUEUE_URL, () => HttpResponse.json(errorBody(code, message, correlationId), { status }));
}