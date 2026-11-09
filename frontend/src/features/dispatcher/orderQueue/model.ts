/**
 * Order Queue model: chiếu dữ liệu GET /orders và GET /orders/counts (docs/06 mục 5.4) theo kiểu fail-closed.
 * Đây KHÔNG phải ranh giới phân quyền; server mới là nơi kiểm phạm vi (docs/09 mục 7).
 * Không suy diễn routing, ngày khả thi hay kết quả duyệt: thiếu dữ liệu thì để null.
 */
export type RiskColor = "green" | "yellow" | "orange" | "red";
export interface Ref { id: number; code: string | null }
export interface QueueOrder {
  id: number;
  orderNo: string;
  status: string;
  customer: string | null;
  site: string | null;
  warehouse: Ref | null;
  originStore: Ref | null;
  dateMode: string | null;
  dateFrom: string | null;
  dateTo: string | null;
  committedDate: string | null;
  promiseEnd: string | null;
  riskColor: RiskColor | null;
  blockReason: string | null;
  totalAmount: string | null;
  currency: string | null;
  submittedAt: string;
}
export interface QueuePage {
  items: QueueOrder[];
  total: number | null;
  page: number;
  pageSize: number;
  invalid: boolean;
  /** Số đơn legacy BLOCKED_UNMAPPED_SKU bị ẩn (ASM-005). */
  hiddenLegacy: number;
  /** Số phần tử hỏng bị bỏ qua. */
  skipped: number;
}
export interface QueueCounts {
  all: number;
  needsPlan: number;
  awaitingApproval: number;
  noFeasibleDate: number;
  inExecution: number;
  replanSuggested: number;
  deliveredToday: number;
  nav: { orderQueue: number; exceptions: number; trackingRisk: number };
}

export const LEGACY_STATUS = "BLOCKED_UNMAPPED_SKU";
const STATUSES = new Set(["SUBMITTED", "PLANNED", "NO_FEASIBLE_DATE", "APPROVED", "PREPARING",
  "GOODS_READY", "LOADED", "DISPATCHED", "DELIVERED", "FAILED", "CANCELLED"]);
const RISKS = new Set<string>(["green", "yellow", "orange", "red"]);

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function id(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : null;
}
function nonnegative(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}
function clean(value: unknown, max = 120): string | null {
  return typeof value === "string" && value.length > 0 && value.length <= max &&
    Array.from(value).every(char => char.charCodeAt(0) >= 32 && char.charCodeAt(0) !== 127) ? value : null;
}
function date(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = Date.parse(value + "T00:00:00Z");
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value ? value : null;
}
function datetime(value: unknown): string | null {
  return typeof value === "string" && /(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value)) ? value : null;
}
function ref(value: unknown): Ref | null {
  const entry = record(value), refId = id(entry.id);
  return refId ? { id: refId, code: clean(entry.code, 20) } : null;
}

export function projectPage(raw: unknown, requestedPage: number, pageSize: number): QueuePage {
  const data = record(raw);
  if (!Array.isArray(data.items)) {
    return { items: [], total: null, page: requestedPage, pageSize, invalid: true, hiddenLegacy: 0, skipped: 0 };
  }
  const items: QueueOrder[] = [];
  let hiddenLegacy = 0;
  let skipped = 0;
  for (const value of data.items) {
    const entry = record(value);
    if (entry.status === LEGACY_STATUS || entry.blocked === true) { hiddenLegacy += 1; continue; }
    const orderId = id(entry.id), orderNo = clean(entry.order_no, 40), submittedAt = datetime(entry.submitted_at);
    if (!orderId || !orderNo || !submittedAt) { skipped += 1; continue; }
    const request = record(entry.date_request);
    const color = typeof entry.risk_color === "string" && RISKS.has(entry.risk_color) ? entry.risk_color as RiskColor : null;
    items.push({
      id: orderId,
      orderNo,
      status: typeof entry.status === "string" && STATUSES.has(entry.status) ? entry.status : "UNKNOWN",
      customer: clean(entry.customer_name),
      site: clean(entry.site),
      warehouse: ref(entry.warehouse),
      originStore: ref(entry.origin_store),
      dateMode: clean(request.mode, 20),
      dateFrom: date(request.date_from),
      dateTo: date(request.date_to),
      committedDate: date(entry.committed_date),
      promiseEnd: datetime(entry.promise_end),
      riskColor: color,
      blockReason: clean(entry.block_reason, 200),
      totalAmount: typeof entry.total_amount === "string" && /^\d+(\.\d{1,2})?$/.test(entry.total_amount) ? entry.total_amount : null,
      currency: typeof entry.currency === "string" && /^[A-Z]{3}$/.test(entry.currency) ? entry.currency : null,
      submittedAt,
    });
  }
  const total = nonnegative(data.total);
  return { items, total, page: id(data.page) ?? requestedPage, pageSize, invalid: total === null, hiddenLegacy, skipped };
}

export function projectCounts(raw: unknown): QueueCounts | null {
  const data = record(raw), nav = record(data.nav);
  const all = nonnegative(data.all), needsPlan = nonnegative(data.needs_plan);
  const awaitingApproval = nonnegative(data.awaiting_approval), noFeasibleDate = nonnegative(data.no_feasible_date);
  const inExecution = nonnegative(data.in_execution), replanSuggested = nonnegative(data.replan_suggested);
  const deliveredToday = nonnegative(data.delivered_today);
  const orderQueue = nonnegative(nav.order_queue), exceptions = nonnegative(nav.exceptions), trackingRisk = nonnegative(nav.tracking_risk);
  if ([all, needsPlan, awaitingApproval, noFeasibleDate, inExecution, replanSuggested, deliveredToday,
    orderQueue, exceptions, trackingRisk].some(value => value === null)) return null;
  return {
    all: all!, needsPlan: needsPlan!, awaitingApproval: awaitingApproval!, noFeasibleDate: noFeasibleDate!,
    inExecution: inExecution!, replanSuggested: replanSuggested!, deliveredToday: deliveredToday!,
    nav: { orderQueue: orderQueue!, exceptions: exceptions!, trackingRisk: trackingRisk! },
  };
}