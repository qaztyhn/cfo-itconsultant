/** Sales API boundary for DEC-R3-10: own-store ranked proposals and pre-approval decisions. */
import { apiGet, apiPost, newIdempotencyKey } from "../../api/client";
import type { PlanningRun, ApprovePlanInput, ApprovePlanResponse, DateNegotiation } from "../../api/contracts/planning";

export type RouteStatus = "cfo" | "legacy" | "unresolved";
export type SyncResult = {
  external_ref: string;
  order_id?: number | null;
  routing_status: RouteStatus;
  already_decided?: boolean;
  sync_status?: "synced" | "already_current" | string;
  source_version?: number;
  retry_after_s?: number;
  missing_confirmed_skus?: { local_sku: string; status?: string }[];
  unmapped_skus?: { local_sku: string; status?: string }[];
};
export type SalesRun = PlanningRun;
export type SalesPlan = PlanningRun["plans"][number];
export type SalesPlanningParams = {
  target_date?: string;
  exclude_warehouse_ids?: number[];
  exclude_vehicle_ids?: number[];
  weights?: { w_km: number; w_fill: number };
  reason_code?: string;
  reason_text?: string;
};
export type NegotiationInput = {
  proposed_date: string;
  outcome: "agreed" | "declined" | "unreachable";
  channel: "phone" | "email" | "in_person";
  contacted_at: string;
  note?: string;
};
export const GATES = ["stock", "preparation", "truck", "site_date", "safety"] as const;

export function isCfoRouting(result: SyncResult | null): result is SyncResult & { order_id: number } {
  return result?.routing_status === "cfo" &&
    Number.isSafeInteger(result.order_id) && (result.order_id ?? 0) > 0;
}
export function validReasonCode(code: string): boolean {
  return /^[a-z][a-z0-9_]{0,63}$/.test(code);
}
/** Displayed eligibility is advisory only: server rechecks all gates under resource locks. */
export function eligibleSalesPlan(run: SalesRun | null, planId: number, now: number): boolean {
  if (!run || run.result !== "feasible" || !["initial", "rerun"].includes(run.kind) ||
      run.sales_approvable !== true ||
      !run.hold_expires_at || !Number.isFinite(Date.parse(run.hold_expires_at)) ||
      Date.parse(run.hold_expires_at) <= now || run.plans.length < 1 || run.plans.length > 3) return false;
  const plan = run.plans.find(p => p.id === planId);
  return Boolean(plan && plan.approvable === true && plan.rank >= 1 && plan.rank <= 3 &&
    plan.status === "proposed" && plan.vehicle_count >= 1 &&
    plan.vehicles?.length === plan.vehicle_count &&
    plan.checks && GATES.every(g => plan.checks?.[g]?.passed === true));
}
/** Compatibility helper for the existing standard-plan tests; no rank-1 monopoly. */
export function eligibleStandardPlan(run: SalesRun | null, now: number): boolean {
  return Boolean(run?.plans[0] && eligibleSalesPlan(run, run.plans[0].id, now));
}
export function safeExternalRef(value: string): string | null {
  const ref = value.trim();
  return ref.length > 0 && ref.length <= 100 && /^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(ref) &&
    !ref.split("/").includes("..") ? ref : null;
}
export function newRetryKey(): string { return newIdempotencyKey(); }

export function syncAndCheck(externalRef: string, key: string): Promise<SyncResult> {
  return apiPost<SyncResult>("/integration/orders/sync-now", { external_ref: externalRef }, key);
}
export function acknowledgeRouting(externalRef: string, choice: "legacy_acknowledged" | "manual_started", reason?: string) {
  return apiPost<{ status?: string }>(
    `/integration/orders/${encodeURIComponent(externalRef)}/routing-ack`,
    { choice, ...(reason ? { reason_text: reason } : {}) },
  );
}
export function requestDefaultPlan(orderId: number, params: SalesPlanningParams = {}): Promise<SalesRun> {
  return apiPost<SalesRun>(`/orders/${orderId}/plan`, params);
}
export function confirmStandardPlan(
  planId: number, key: string, body: ApprovePlanInput = {},
): Promise<ApprovePlanResponse> {
  return apiPost<ApprovePlanResponse>(`/plans/${planId}/approve`, body, key);
}
export function recordDateAgreement(orderId: number, body: NegotiationInput): Promise<{ id: number }> {
  return apiPost<{ id: number }>(`/orders/${orderId}/date-negotiations`, body);
}
export function listDateAgreements(orderId: number): Promise<{ items: DateNegotiation[] }> {
  return apiGet<{ items: DateNegotiation[] }>(`/orders/${orderId}/date-negotiations`);
}
