/**
 * Lời gọi Planning (docs/06 mục 6). Owner: Dev 3 (luồng C) — M4–M5.
 * Approve luôn gửi Idempotency-Key do nơi gọi tạo (một khoá cho mỗi lần người dùng bấm duyệt).
 */
import { apiGet, apiPost } from "./client";
import type {
  ApprovePlanInput,
  ApprovePlanResponse,
  DateNegotiation,
  PlanAgainInput,
  PlanningRun,
} from "./contracts/planning";

export const planningKeys = {
  run: (runId: number) => ["planning-run", runId] as const,
  runs: (orderId: number) => ["planning-runs", orderId] as const,
};

export function fetchPlanningRun(runId: number, signal?: AbortSignal): Promise<PlanningRun> {
  return apiGet<PlanningRun>(`/planning-runs/${runId}`, undefined, signal);
}

export function fetchPlanningRuns(
  orderId: number,
  signal?: AbortSignal,
): Promise<{ items: Pick<PlanningRun, "id" | "order_id" | "run_no" | "result" | "hold_expires_at">[] }> {
  return apiGet(`/orders/${orderId}/planning-runs`, undefined, signal);
}

export function fetchOrderRequestedDate(orderId: number, signal?: AbortSignal): Promise<{ date_request: { date_to: string | null } }> {
  return apiGet(`/orders/${orderId}`, undefined, signal);
}

export function fetchDateNegotiations(orderId: number, signal?: AbortSignal): Promise<{ items: DateNegotiation[] }> {
  return apiGet(`/orders/${orderId}/date-negotiations`, undefined, signal);
}

/** Gia hạn hold +15 phút; tối đa 2 lần do server quyết định (409 HOLD_EXTENSION_LIMIT / HOLD_EXPIRED). */
export function extendHold(runId: number): Promise<PlanningRun> {
  return apiPost<PlanningRun>(`/planning-runs/${runId}/extend`);
}

/** Plan Again: tạo planning_run mới cho cùng order (DEC-HOLD-001), không tạo order mới. */
export function planAgain(orderId: number, input: PlanAgainInput): Promise<PlanningRun> {
  return apiPost<PlanningRun>(`/orders/${orderId}/plan`, input);
}

export function approvePlan(
  planId: number,
  input: ApprovePlanInput,
  idempotencyKey: string,
): Promise<ApprovePlanResponse> {
  return apiPost<ApprovePlanResponse>(`/plans/${planId}/approve`, input, idempotencyKey);
}
