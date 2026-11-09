/**
 * API CS Order Lookup (docs/06 §5.3–5.5, §10). Mọi response đi qua allowlist trước khi ra khỏi file này.
 * KHÔNG có POST contact-logs: form contact-log là demo cục bộ (docs/proposals/CS_ORDER_LOOKUP_ASSUMPTIONS_20261109.md).
 * DEPENDENCY: GET /orders?q= chưa tìm theo phone (DEC-CS-SEARCH-20261109 chưa có ở backend);
 * /eta-forecasts, /notifications là stub phía backend; /timeline chưa xác minh. Lỗi của chúng được ném nguyên vẹn để UI hiện trạng thái lỗi.
 * Owner: Dev 3 (luồng C).
 */
import { ApiError, apiGet } from "../../api/client";
import {
  projectCsEtaForecasts,
  projectCsNotifications,
  projectCsOrderDetail,
  projectCsOrderPage,
  type CsEtaForecast,
  type CsNotification,
  type CsOrderDetail,
  type CsOrderPage,
} from "./allowlist";
import { projectCsTimeline, type CsTimelineItem } from "./timeline";

export const SEARCH_PAGE_SIZE = 20;

/** Query key chứa từ khoá / order id: kết quả của truy vấn cũ không thể ghi đè truy vấn mới. */
export const csKeys = {
  search: (q: string, page = 1) => ["cs", "orders", "search", q, page] as const,
  detail: (orderId: number) => ["cs", "orders", orderId, "detail"] as const,
  eta: (orderId: number) => ["cs", "orders", orderId, "eta-forecasts"] as const,
  notifications: (orderId: number) => ["cs", "orders", orderId, "notifications"] as const,
  timeline: (orderId: number) => ["cs", "orders", orderId, "timeline"] as const,
};

function unreadable(what: string): ApiError {
  return new ApiError("INVALID_RESPONSE", `The ${what} response could not be read.`);
}

export async function searchOrders(query: string, signal?: AbortSignal, page = 1): Promise<CsOrderPage> {
  const q = query.trim();
  if (!q) {
    return { items: [], page: 1, pageSize: SEARCH_PAGE_SIZE, total: 0 };
  }
  const raw = await apiGet<unknown>("/orders", { q, page, page_size: SEARCH_PAGE_SIZE }, signal);
  const projected = projectCsOrderPage(raw);
  if (!projected) throw unreadable("order list");
  return projected;
}

export async function fetchOrderDetail(orderId: number, signal?: AbortSignal): Promise<CsOrderDetail> {
  const raw = await apiGet<unknown>(`/orders/${orderId}`, undefined, signal);
  const detail = projectCsOrderDetail(raw);
  if (!detail) throw unreadable("order");
  return detail;
}

export async function fetchEtaForecasts(orderId: number, signal?: AbortSignal): Promise<CsEtaForecast[]> {
  return projectCsEtaForecasts(await apiGet<unknown>(`/orders/${orderId}/eta-forecasts`, undefined, signal));
}

export async function fetchNotifications(orderId: number, signal?: AbortSignal): Promise<CsNotification[]> {
  return projectCsNotifications(await apiGet<unknown>(`/orders/${orderId}/notifications`, undefined, signal));
}

export async function fetchTimeline(orderId: number, signal?: AbortSignal): Promise<CsTimelineItem[]> {
  return projectCsTimeline(await apiGet<unknown>(`/orders/${orderId}/timeline`, undefined, signal));
}