/** Safe, conservative projections of exception API responses (OpenAPI DTO pending). */
export type Tab = "no-feasible" | "replan" | "blocked";
export type ExceptionOrder = {
  id: number; ref: string; status: string; risk: string; reason: string;
  latestRunId: number | null; requestedDate: string | null;
};
export type Suggestion = { id: number; orderId: number; runId: number | null; type: string; level: string };
export type Evidence = {
  failedCheck: string; earliest: string | null; checkedDates: { date: string; result: string; check: string | null }[];
  warehouseChecks: { warehouse: string; failed: string; code: string }[];
  candidateCodes: string[]; kind: string; result: string; hold: string | null;
};
export type SkuDetail = { code: string; status: string };

type Json = Record<string, unknown>;
function object(value: unknown): Json {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
}
function positive(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : null;
}
function code(value: unknown): string {
  return typeof value === "string" && /^[A-Z][A-Z0-9_]{0,63}$/.test(value) ? value : "UNVERIFIED";
}
function date(value: unknown): string | null {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value+"T00:00:00Z")) ? value : null;
}
function safeRef(value: unknown): string | null {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_-]{0,48}$/.test(value) ? value : null;
}
export function orders(input: unknown): ExceptionOrder[] {
  const list = object(input).items;
  if (!Array.isArray(list)) return [];
  return list.flatMap((value) => {
    const item = object(value), id = positive(item.id);
    if (!id || !["NO_FEASIBLE_DATE","BLOCKED_UNMAPPED_SKU"].includes(item.status as string)) return [];
    const request = object(item.date_request);
    const risk = object(item.risk);
    return [{
      id, ref: safeRef(item.order_no) ?? `Order #${id}`, status: String(item.status),
      risk: code(risk.status ?? item.risk_status),
      reason: code(item.block_reason ?? item.failed_check),
      latestRunId: positive(item.latest_run_id),
      requestedDate: date(request.date_to) ?? date(request.date_from),
    }];
  });
}
export function suggestions(input: unknown): Suggestion[] {
  const list = object(input).items;
  if (!Array.isArray(list)) return [];
  return list.flatMap((value) => {
    const item = object(value);
    const id = positive(item.id), orderId = positive(item.order_id);
    if (!id || !orderId || item.type !== "REPLAN_SUGGESTED" || item.resolved === true) return [];
    return [{ id, orderId, runId: positive(object(item.details).run_id), type: "REPLAN_SUGGESTED", level: code(item.level) }];
  });
}
export function evidence(input: unknown): Evidence {
  const raw = object(input);
  const check = raw.failed_check;
  const days = Array.isArray(raw.dates_searched) ? raw.dates_searched : [];
  const warehouses = Array.isArray(raw.per_warehouse_checks) ? raw.per_warehouse_checks : [];
  const candidates = Array.isArray(raw.rejected_candidates) ? raw.rejected_candidates : [];
  return {
    failedCheck: code(check), earliest: date(raw.earliest_feasible_date),
    checkedDates: days.slice(0,40).flatMap((item) => {
      const x=object(item), day=date(x.date);
      return day ? [{date:day,result:code(typeof x.result === "string" ? x.result.toUpperCase() : x.result),check:x.check == null ? null : code(typeof x.check === "string" ? x.check.toUpperCase() : x.check)}] : [];
    }),
    warehouseChecks: warehouses.slice(0,30).map((item)=>{
      const x=object(item);
      const found=["stock","preparation","truck","site_date","safety"].map(key=>object(x[key]))
        .find(v=>v.passed === false || v.pass === false);
      return { warehouse: safeRef(x.warehouse) ?? "Warehouse not reported",
        failed: found ? "Failed" : "Unverified",code:found ? code(found.code) : "UNVERIFIED" };
    }),
    candidateCodes: candidates.slice(0,30).map(item=>code(object(item).code)),
    kind: raw.kind === "replan_suggestion" ? "replan_suggestion" : "unverified",
    result: raw.result === "infeasible" ? "infeasible" : raw.result === "feasible" ? "feasible" : "unverified",
    hold: typeof raw.hold_expires_at === "string" ? "Reported (not authorised here)" : null,
  };
}
export function skuDetails(input: unknown): SkuDetail[] {
  const lines = object(input).lines;
  if (!Array.isArray(lines)) return [];
  return lines.slice(0,100).flatMap(item=>{
    const row=object(item), local=safeRef(row.local_sku);
    const status=code(typeof row.mapping_status === "string" ? row.mapping_status.toUpperCase() : row.mapping_status);
    return local && (status === "PENDING" || status === "REJECTED") ? [{code:local,status}] : [];
  });
}
