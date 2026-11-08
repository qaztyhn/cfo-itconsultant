/**
 * Danh sách đơn theo docs/06 mục 5.4 (v1.4): lọc, sắp xếp, phân trang. Hàm thuần để test với fixture.
 * Chưa áp phạm vi theo vai trò (mục 5.2): handler mock chưa biết vai trò người gọi.
 * Owner: Dev 3 (luồng C).
 */

export interface RefCode {
  id: number;
  code: string;
}

/** Bản ghi đơn đã chuẩn hóa. `external_ref` chỉ dùng để tìm kiếm `q`, không có trong phần tử trả về. */
export interface OrderRecord {
  id: number;
  order_no: string;
  external_ref: string | null;
  status: string;
  customer_name: string;
  site: string;
  warehouse: RefCode | null;
  origin_store: RefCode | null;
  date_request: { mode: string; date_from: string | null; date_to: string | null };
  committed_date: string | null;
  promise_end: string | null;
  risk_color: string | null;
  block_reason: string | null;
  total_amount: string;
  currency: string;
  submitted_at: string;
}

export type OrderListItem = Omit<OrderRecord, "external_ref">;

export interface OrderListPage {
  items: OrderListItem[];
  page: number;
  page_size: number;
  total: number;
}

export type OrderListResult = { ok: true; body: OrderListPage } | { ok: false; message: string };

const SORT_FIELDS = ["submitted_at", "date_to", "promise_end", "committed_date", "order_no", "status"] as const;
type SortField = (typeof SORT_FIELDS)[number];
interface SortKey {
  field: SortField;
  desc: boolean;
}

const fail = (message: string): OrderListResult => ({ ok: false, message });

/** null = giá trị không hợp lệ; thiếu tham số → mặc định. */
function parseIntParam(raw: string | null, fallback: number): number | null {
  if (raw === null) return fallback;
  return /^\d+$/.test(raw.trim()) ? Number(raw) : null;
}

function parseSort(raw: string | null): SortKey[] | string {
  const parts = (raw ?? "").split(",").map((p) => p.trim()).filter(Boolean);
  if (parts.length === 0) return [{ field: "submitted_at", desc: false }]; // mặc định: thứ tự đặt hàng
  const keys: SortKey[] = [];
  for (const part of parts) {
    const desc = part.startsWith("-");
    const field = desc ? part.slice(1) : part;
    if (!(SORT_FIELDS as readonly string[]).includes(field)) return `Unknown sort field: ${field}.`;
    keys.push({ field: field as SortField, desc });
  }
  return keys;
}

function sortValue(o: OrderRecord, field: SortField): number | string | null {
  switch (field) {
    case "submitted_at":
      return Date.parse(o.submitted_at); // so theo thời điểm, không so chuỗi (offset khác nhau)
    case "promise_end":
      return o.promise_end ? Date.parse(o.promise_end) : null;
    case "date_to":
      return o.date_request.date_to;
    case "committed_date":
      return o.committed_date;
    case "order_no":
      return o.order_no;
    case "status":
      return o.status;
  }
}

function compareValues(a: number | string, b: number | string): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  const x = String(a);
  const y = String(b);
  return x < y ? -1 : x > y ? 1 : 0;
}

function compareOrders(a: OrderRecord, b: OrderRecord, keys: SortKey[]): number {
  for (const { field, desc } of keys) {
    const x = sortValue(a, field);
    const y = sortValue(b, field);
    if (x === null && y === null) continue;
    if (x === null) return 1; // NULL xếp cuối, kể cả khi giảm dần
    if (y === null) return -1;
    const c = compareValues(x, y);
    if (c !== 0) return desc ? -c : c;
  }
  return a.id - b.id; // tie-breaker ổn định: id ASC
}

function toListItem(r: OrderRecord): OrderListItem {
  return {
    id: r.id,
    order_no: r.order_no,
    status: r.status,
    customer_name: r.customer_name,
    site: r.site,
    warehouse: r.warehouse,
    origin_store: r.origin_store,
    date_request: r.date_request,
    committed_date: r.committed_date,
    promise_end: r.promise_end,
    risk_color: r.risk_color,
    block_reason: r.block_reason,
    total_amount: r.total_amount,
    currency: r.currency,
    submitted_at: r.submitted_at,
  };
}

export function listOrders(records: OrderRecord[], params: URLSearchParams): OrderListResult {
  const page = parseIntParam(params.get("page"), 1);
  const pageSize = parseIntParam(params.get("page_size"), 50);
  if (page === null || page < 1) return fail("page must be an integer ≥ 1.");
  if (pageSize === null || pageSize < 1 || pageSize > 200) return fail("page_size must be an integer between 1 and 200.");

  const sortKeys = parseSort(params.get("sort"));
  if (typeof sortKeys === "string") return fail(sortKeys);

  const warehouseId = parseIntParam(params.get("warehouse_id"), -1);
  const storeId = parseIntParam(params.get("store_id"), -1);
  if (warehouseId === null) return fail("warehouse_id must be an integer.");
  if (storeId === null) return fail("store_id must be an integer.");

  const status = params.get("status");
  const risk = params.get("risk_color");
  const from = params.get("committed_date_from");
  const to = params.get("committed_date_to");
  const mode = params.get("date_mode");
  const blocked = params.get("blocked");
  const q = params.get("q")?.trim().toLowerCase();

  const filtered = records.filter((o) => {
    if (status && o.status !== status) return false;
    if (risk && o.risk_color !== risk) return false;
    if (from && !(o.committed_date !== null && o.committed_date >= from)) return false;
    if (to && !(o.committed_date !== null && o.committed_date <= to)) return false;
    if (warehouseId !== -1 && o.warehouse?.id !== warehouseId) return false;
    if (storeId !== -1 && o.origin_store?.id !== storeId) return false;
    if (mode && o.date_request.mode !== mode) return false;
    if (blocked === "true" && o.status !== "BLOCKED_UNMAPPED_SKU") return false;
    if (blocked === "false" && o.status === "BLOCKED_UNMAPPED_SKU") return false;
    if (q) {
      const hit = [o.order_no, o.external_ref ?? "", o.customer_name].some((v) => v.toLowerCase().includes(q));
      if (!hit) return false;
    }
    return true;
  });

  const sorted = [...filtered].sort((a, b) => compareOrders(a, b, sortKeys));
  const start = (page - 1) * pageSize;
  return {
    ok: true,
    body: { items: sorted.slice(start, start + pageSize).map(toListItem), page, page_size: pageSize, total: sorted.length },
  };
}