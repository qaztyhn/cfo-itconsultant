/** Sales-only API boundary: docs/06 §5.0.2, §6.2–6.3a.
 * Agent 26 sync-now contract is not yet verified on main. DTOs remain local/defensive.
 */
import { apiPost, newIdempotencyKey } from "../../api/client";
import type { PlanningRun, ApprovePlanResponse } from "../../api/contracts/planning";

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
export type SalesRun = Omit<PlanningRun, "plans"> & {
  /** Owner-approved API-1: passed; missing gates MUST be UNKNOWN. */
  plans: (Omit<PlanningRun["plans"][number], "checks"> & {
    checks?: Partial<Record<"stock" | "preparation" | "truck" | "site_date" | "safety", {
      passed?: boolean; code?: string;
    }>>;
  })[];
};

export const GATES = ["stock", "preparation", "truck", "site_date", "safety"] as const;

export function isCfoRouting(result: SyncResult | null): result is SyncResult & { order_id: number } {
  return result?.routing_status === "cfo" &&
    Number.isSafeInteger(result.order_id) && (result.order_id ?? 0) > 0;
}

/** UI is an additional fail-closed layer. Server remains the approval authority. */
export function eligibleStandardPlan(run: SalesRun | null, now: number): boolean {
  if (!run || run.result !== "feasible" || run.kind !== "initial" ||
      run.reserve_class !== "safe" || run.sales_approvable !== true ||
      !run.hold_expires_at || !Number.isFinite(Date.parse(run.hold_expires_at)) ||
      Date.parse(run.hold_expires_at) <= now || run.plans.length !== 1) return false;
  const plan = run.plans[0];
  if (!plan || plan.rank !== 1 || plan.status !== "proposed" || plan.vehicle_count !== 1 ||
      plan.vehicles?.length !== 1 || !plan.checks ||
      !GATES.every(g => plan.checks?.[g]?.passed === true)) return false;
  return true;
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
export function requestDefaultPlan(orderId: number): Promise<SalesRun> {
  return apiPost<SalesRun>(`/orders/${orderId}/plan`, {});
}
export function confirmStandardPlan(planId: number, key: string): Promise<ApprovePlanResponse> {
  // No rank override, criteria, driver assignment, date mutation or manual approval.
  return apiPost<ApprovePlanResponse>(`/plans/${planId}/approve`, {}, key);
}
