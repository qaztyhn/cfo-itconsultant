/** Feature-local read model, based on docs/06 §6 and Appendix A.
 * Supplementary diagnostics are optional: the live API currently omits them.
 * Never infer passed gates, dates or stock from absent fields.
 */
import { apiGet, apiPost } from "../../api/client";
import type { PlanningRun } from "../../api/contracts/planning";

export type GateName = "stock" | "preparation" | "truck" | "site_date" | "safety";
export const GATES: readonly GateName[] = ["stock", "preparation", "truck", "site_date", "safety"];
export const GATE_LABELS: Record<GateName, string> = {
  stock: "Stock", preparation: "Preparation", truck: "Truck",
  site_date: "Site / date", safety: "Safety",
};
export type GateEvidence = {
  passed?: boolean;
  /** Older Appendix A examples use pass; never treat missing passed as true. */
  pass?: boolean;
  code?: string;
  detail?: { message?: string; inbound_available_on?: string; [key: string]: unknown };
} | null;
export type WarehouseChecks = {
  warehouse?: string | { id?: number; name?: string };
  warehouse_id?: number;
} & Partial<Record<GateName, GateEvidence>>;
export type DateSearch = { date: string; result: string; check?: string | null };
export type StockLine = {
  local_sku: string; name?: string; unit?: string; needed: number | string;
  usable?: Record<string, number | string | null>;
  inbound?: Record<string, { qty: number | string; eta: string }[]>;
};
export type StockMatrix = { date: string; lines: StockLine[] };
export type InfeasibleRun = PlanningRun & {
  dates_searched?: DateSearch[];
  per_warehouse_checks?: WarehouseChecks[];
  stock_matrix?: StockMatrix | null;
  /** Flat API-2 format: nested warehouse/vehicle names are NOT guaranteed. */
  rejected_candidates?: {
    warehouse_id?: number; vehicle_code?: string | null; failed_check?: string;
    code?: string; detail?: { message?: string; inbound_available_on?: string };
  }[];
};
export type NegotiationOutcome = "agreed" | "declined" | "unreachable";
export type NegotiationInput = {
  proposed_date: string; outcome: NegotiationOutcome;
  channel: "phone" | "email" | "in_person"; contacted_at: string; note: string;
};
export type NegotiationRecord = NegotiationInput & { id: number; remind_at?: string | null };

export function fetchInfeasibleRun(id: number, signal?: AbortSignal): Promise<InfeasibleRun> {
  return apiGet<InfeasibleRun>(`/planning-runs/${id}`, undefined, signal);
}
export function fetchNegotiations(orderId: number, signal?: AbortSignal) {
  return apiGet<{ items: NegotiationRecord[] }>(`/orders/${orderId}/date-negotiations`, undefined, signal);
}
export function recordNegotiation(orderId: number, body: NegotiationInput) {
  return apiPost<{ id: number }>(`/orders/${orderId}/date-negotiations`, body);
}
export function gateStatus(gate: GateEvidence | undefined): "passed" | "failed" | "unknown" {
  if (gate?.passed === true) return "passed";
  if (gate?.passed === false) return "failed";
  return "unknown";
}
export function validIsoDate(date: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return false;
  const d = new Date(`${date}T00:00:00Z`);
  return Number.isFinite(d.getTime()) && d.toISOString().slice(0, 10) === date;
}
export function readableNumber(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Unknown";
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? new Intl.NumberFormat("en").format(n) : "Unknown";
}
