/** Read-only allowlisted Sales projections. Backend enforces market/store scope. */
export interface StoreOrder {
  id: number;
  reference: string;
  status: string;
  customer: string | null;
  site: string | null;
  storeId: number;
  storeCode: string | null;
  requestedDate: string | null;
  committedDate: string | null;
  promisedEnd: string | null;
  forecastEta: string | null;
  risk: string | null;
}
export interface OrderPage { items: StoreOrder[]; total: number | null; page: number; pageSize: number; invalid: boolean }
export interface StoreOrderDetail {
  id: number; reference: string; storeId: number; status: string;
  requestedDate: string | null; committedDate: string | null;
  promisedStart: string | null; promisedEnd: string | null; forecastEta: string | null;
  lines: { number: number; product: string; quantity: string; unit: string }[];
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function id(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : null;
}
function nonnegative(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}
function clean(value: unknown, max = 100): string | null {
  return typeof value === "string" && value.length > 0 && value.length <= max && Array.from(value).every(char => char.charCodeAt(0) >= 32 && char.charCodeAt(0) !== 127)
    ? value : null;
}
function date(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = Date.parse(value + "T00:00:00Z");
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value ? value : null;
}
function datetime(value: unknown): string | null {
  return typeof value === "string" && /(?:Z|[+-]\d\d:\d\d)$/.test(value) &&
    Number.isFinite(Date.parse(value)) ? value : null;
}
const STATUSES = new Set(["SUBMITTED","PLANNED","NO_FEASIBLE_DATE","APPROVED","PREPARING",
  "GOODS_READY","LOADED","DISPATCHED","DELIVERED","FAILED","CANCELLED","BLOCKED_UNMAPPED_SKU"]);
function status(value: unknown): string {
  return typeof value === "string" && STATUSES.has(value) ? value : "UNKNOWN";
}
export function projectPage(raw: unknown, authorizedStores: readonly number[], requestedPage: number, pageSize: number): OrderPage {
  const data = record(raw);
  if (!Array.isArray(data.items)) return { items: [], total: null, page: requestedPage, pageSize, invalid: true };
  const allowed = new Set(authorizedStores);
  const items: StoreOrder[] = data.items.flatMap(value => {
    const entry = record(value), store = record(entry.origin_store);
    const orderId = id(entry.id), storeId = id(store.id);
    // Extra fail-closed check, NOT the permission boundary. Server must enforce store scope.
    if (!orderId || !storeId || !allowed.has(storeId)) return [];
    const request = record(entry.date_request), risk = record(entry.risk);
    return [{
      id: orderId, reference: clean(entry.order_no, 80) ?? `Order #${orderId}`,
      status: status(entry.status), customer: clean(entry.customer_name),
      site: clean(entry.site), storeId, storeCode: clean(store.code, 40),
      requestedDate: date(request.date_to) ?? date(request.date_from),
      committedDate: date(entry.committed_date), promisedEnd: datetime(entry.promise_end),
      forecastEta: datetime(risk.forecast_eta), risk: clean(entry.risk_color, 20),
    }];
  });
  return { items, total: nonnegative(data.total), page: requestedPage, pageSize, invalid: false };
}
export function projectDetail(raw: unknown, authorizedStores: readonly number[], expectedOrderId: number): StoreOrderDetail | null {
  const entry = record(raw), store = record(entry.origin_store);
  const orderId = id(entry.id), storeId = id(store.id);
  if (orderId !== expectedOrderId || !storeId || !authorizedStores.includes(storeId)) return null;
  const request = record(entry.date_request), committed = record(entry.committed), risk = record(entry.risk);
  const rows = Array.isArray(entry.lines) ? entry.lines : [];
  return {
    id: orderId, reference: clean(entry.order_no, 80) ?? `Order #${orderId}`, storeId,
    status: status(entry.status),
    requestedDate: date(request.date_to) ?? date(request.date_from),
    committedDate: date(committed.date), promisedStart: datetime(committed.promise_start),
    promisedEnd: datetime(committed.promise_end), forecastEta: datetime(risk.forecast_eta),
    lines: rows.slice(0, 100).flatMap(row => {
      const item = record(row), lineNo = id(item.line_no);
      if (!lineNo) return [];
      return [{ number: lineNo, product: clean(item.name) ?? "Product unavailable",
        quantity: typeof item.qty_sale === "number" && Number.isFinite(item.qty_sale) && item.qty_sale >= 0
          ? String(item.qty_sale) : "Not reported", unit: clean(item.sale_unit, 24) ?? "" }];
    }),
  };
}
export function validPage(value: string | null): number {
  const number = Number(value);
  return value !== null && /^\d+$/.test(value) && Number.isSafeInteger(number) && number >= 1 ? number : 1;
}
export const PAGE_SIZE = 20;
export const SORT_OPTIONS = [
  { value: "submitted_at", label: "Submitted (oldest first)" },
  { value: "date_to", label: "Requested delivery" },
  { value: "promise_end", label: "Promised delivery" },
  { value: "committed_date", label: "Committed date" },
  { value: "order_no", label: "Order reference" },
  { value: "status", label: "Status" },
] as const;
export const FILTER_STATUSES = [
  "ALL", "SUBMITTED", "PLANNED", "NO_FEASIBLE_DATE", "APPROVED",
  "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED", "DELIVERED", "FAILED", "CANCELLED",
] as const;
