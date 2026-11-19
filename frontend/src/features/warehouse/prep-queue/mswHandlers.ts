/**
 * Local MSW handlers for tests of the Prep Queue. Deliberately NOT added to the shared `api/mocks/handlers.ts`.
 * Owner: Dev 3 (stream C) — M6.
 */
import { http, HttpResponse } from "msw";
import { API_BASE_URL } from "../../../api/config";
import { buildPrepQueueFixture } from "./fixtures";
import type { PrepQueueResponse } from "./types";

/** `GET /warehouses/{id}/prep-queue?date=` (contract agreed with Dev 1). */
export const PREP_QUEUE_URL = `${API_BASE_URL}/warehouses/:warehouseId/prep-queue`;

export interface PrepQueueRequest {
  warehouse_id: number | null;
  date: string | null;
}

export function errorBody(code: string, message: string, correlationId: string) {
  return { error: { code, message, details: {}, correlation_id: correlationId } };
}

/** Returns `response` for a valid query; `date` is optional (docs/06 Appendix A.1). */
export function prepQueueSuccess(response: PrepQueueResponse = buildPrepQueueFixture("verified"), onRequest?: (request: PrepQueueRequest) => void) {
  return http.get(PREP_QUEUE_URL, ({ request, params }) => {
    const rawId = typeof params.warehouseId === "string" ? params.warehouseId : null;
    const date = new URL(request.url).searchParams.get("date");
    const warehouseId = rawId !== null && /^\d+$/.test(rawId) ? Number(rawId) : null;
    onRequest?.({ warehouse_id: warehouseId, date });
    if (warehouseId === null || (date !== null && !/^\d{4}-\d{2}-\d{2}$/.test(date))) {
      return HttpResponse.json(errorBody("VALIDATION_ERROR", "Use a numeric warehouse id and YYYY-MM-DD when supplying a date", "corr-prep-422"), { status: 422 });
    }
    return HttpResponse.json(response);
  });
}

export function prepQueueFailure(status: number, code: string, message: string, correlationId = "corr-prep-test") {
  return http.get(PREP_QUEUE_URL, () => HttpResponse.json(errorBody(code, message, correlationId), { status }));
}
