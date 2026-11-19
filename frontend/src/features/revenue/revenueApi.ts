/** Revenue-only HTTP boundary. Financial values are opaque server decimal strings. */
import { apiGet, ApiError, buildQuery } from "../../api/client";
import { API_BASE_URL } from "../../api/config";
import { useAuthStore } from "../../app/store";

export type RevenueView = "store" | "warehouse";
export type RevenueFilters = { view: RevenueView; from?: string; to?: string; location_id?: number };
export type CurrencyAmount = string;
/** US-REV-02 / API §19.11: stable group keys, never derived from translated labels. */
export const REVENUE_STATUS_GROUPS = [
  { key: "approved", label: "Đã duyệt" },
  { key: "in_transit", label: "Đang vận chuyển" },
  { key: "completed", label: "Đã hoàn thành" },
  { key: "failed", label: "Thất bại" },
  { key: "cancelled", label: "Đã hủy" },
] as const;
export type RevenueStatusGroup = (typeof REVENUE_STATUS_GROUPS)[number]["key"];
export interface RevenueOrderStatusGroup {
  key: RevenueStatusGroup; statuses: string[]; date_basis: "committed_date" | "cancelled_at";
  orders: number; amount: CurrencyAmount;
}
export interface RevenueOrderStatus {
  period: { from: string; to: string }; view: RevenueView; location_id: number | null;
  currency: string; total: { orders: number; amount: CurrencyAmount };
  groups: RevenueOrderStatusGroup[];
}
export interface RevenueSummary {
  period: { from: string; to: string }; view: RevenueView; location_id: number | null;
  currency: string; recognised: CurrencyAmount; booked_not_delivered: CurrencyAmount;
  orders_delivered: number; avg_order_value: CurrencyAmount | null; share_of_market_pct: number | null;
}
export interface RevenueDaily {
  currency: string; points: { day: string; recognised: CurrencyAmount; booked: CurrencyAmount }[];
}
export interface RevenueLocation {
  location_id: number | null; code: string | null; name: string; orders_delivered: number;
  recognised: CurrencyAmount; booked_not_delivered: CurrencyAmount; share_pct: number | null;
}
export interface RevenueLocations { view: RevenueView; currency: string; rows: RevenueLocation[] }
export interface RevenueOrder {
  order_no: string; delivered_at: string | null; amount: CurrencyAmount;
  currency: string; status: string; customer_name?: string | null;
}
export interface RevenueOrders { items: RevenueOrder[]; page: number; page_size: number; total: number }

function queryParams(filters: RevenueFilters) {
  return { view: filters.view, from: filters.from, to: filters.to, location_id: filters.location_id };
}
export const revenueQueryKeys = {
  summary: (f: RevenueFilters) => ["revenue", "summary", f] as const,
  daily: (f: RevenueFilters) => ["revenue", "daily", f] as const,
  locations: (f: RevenueFilters) => ["revenue", "locations", f] as const,
  orderStatus: (f: RevenueFilters) => ["revenue", "order-status", f] as const,
  orders: (f: RevenueFilters, page: number, group: RevenueStatusGroup | null = null) =>
    ["revenue", "orders", group, f, page] as const,
};
export function getRevenueSummary(filters: RevenueFilters, signal?: AbortSignal) {
  return apiGet<RevenueSummary>("/revenue/summary", queryParams(filters), signal);
}
export function getRevenueOrderStatus(filters: RevenueFilters, signal?: AbortSignal) {
  return apiGet<RevenueOrderStatus>("/revenue/order-status", queryParams(filters), signal);
}
export function getRevenueDaily(filters: RevenueFilters, signal?: AbortSignal) {
  return apiGet<RevenueDaily>("/revenue/daily", queryParams(filters), signal);
}
export function getRevenueLocations(filters: RevenueFilters, signal?: AbortSignal) {
  return apiGet<RevenueLocations>("/revenue/by-location", queryParams(filters), signal);
}
export function getRevenueOrders(
  filters: RevenueFilters & { location_id: number }, page: number,
  signal?: AbortSignal, statusGroup?: RevenueStatusGroup | null,
) {
  return apiGet<RevenueOrders>(
    "/revenue/orders",
    { ...queryParams(filters), ...(statusGroup ? { status_group: statusGroup } : {}), page, page_size: 25 },
    signal,
  );
}

/** CSV cannot go through apiFetch<T>: that helper decodes successful responses as JSON.
 * Keep its authentication and standard error-envelope semantics, without logging response data.
 * Caller triggers only from a user click, so every download is an audited export on the server.
 */
export async function downloadRevenueCsv(filters: RevenueFilters): Promise<Blob> {
  const token = useAuthStore.getState().token;
  const correlationId = crypto.randomUUID();
  const response = await fetch(`${API_BASE_URL}/revenue/export.csv${buildQuery(queryParams(filters))}`, {
    method: "GET",
    headers: {
      Accept: "text/csv",
      "X-Correlation-ID": correlationId,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  }).catch(() => { throw new ApiError("NETWORK_ERROR", "Cannot reach the server.", correlationId, undefined, 0); });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as {
      error?: { code?: string; message?: string; correlation_id?: string; details?: unknown };
    } | null;
    if (response.status === 401 && useAuthStore.getState().token === token) useAuthStore.getState().clearAuth();
    throw new ApiError(
      data?.error?.code ?? (response.status === 403 ? "FORBIDDEN" : "UNKNOWN_ERROR"),
      data?.error?.message ?? `HTTP ${response.status}`,
      data?.error?.correlation_id ?? response.headers.get("X-Correlation-ID") ?? correlationId,
      data?.error?.details, response.status,
    );
  }
  return response.blob();
}
export function money(value: string | null, currency: string): string {
  if (value === null || !/^-?\d+(?:\.\d+)?$/.test(value)) return "—";
  // Cosmetic grouping of an authoritative server decimal, not client-side financial arithmetic.
  const [integer, fraction] = value.split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f");
  return `${grouped}${fraction && Number(fraction) !== 0 ? "." + fraction : ""} ${currency}`;
}
export function validPeriod(from: string, to: string): boolean {
  if (!from && !to) return true; // API default: market-local last 30 days
  if (!from || !to || !/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return false;
  const start = Date.parse(from + "T00:00:00Z"), end = Date.parse(to + "T00:00:00Z");
  return Number.isFinite(start) && Number.isFinite(end) &&
    new Date(start).toISOString().slice(0, 10) === from &&
    new Date(end).toISOString().slice(0, 10) === to &&
    end >= start && (end - start) / 86_400_000 < 366;
}
export function noCustomerNames<T extends RevenueOrder>(orders: T[]): Omit<T, "customer_name">[] {
  return orders.map(({ customer_name: _privateName, ...safe }) => {
    void _privateName;
    return safe;
  });
}
