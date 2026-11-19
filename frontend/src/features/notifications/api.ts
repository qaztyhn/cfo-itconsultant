/** Narrow runtime projection until the generated OpenAPI schema is available. */
import { apiGet, apiPost } from "../../api/client";

export interface NoticeSummary {
  id: number;
  orderId: number;
  orderNo: string;
  template: string;
  status: string;
  recipientMasked: string | null;
  scheduledFor: string;
}

export interface NoticeDetail extends NoticeSummary {
  marketTimezone: string;
  subject: string | null;
  bodyText: string;
  etaWindow: { start: string; end: string; version: number | null } | null;
}

export interface SendPayload {
  eta_window: { start: string; end: string };
  version: number;
  reason_code: "PREDICTED_LATE";
  date_negotiation_id?: number;
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Notification response is unavailable.");
  return value as Record<string, unknown>;
}

function summary(value: unknown): NoticeSummary {
  const row = object(value);
  if (typeof row.id !== "number" || typeof row.order_id !== "number" ||
      typeof row.order_no !== "string" || typeof row.template !== "string" ||
      typeof row.status !== "string" || typeof row.scheduled_for !== "string") {
    throw new Error("Notification response is incomplete.");
  }
  return {
    id: row.id, orderId: row.order_id, orderNo: row.order_no,
    template: row.template, status: row.status, scheduledFor: row.scheduled_for,
    recipientMasked: typeof row.recipient_masked === "string" ? row.recipient_masked : null,
  };
}

export async function fetchDrafts(orderId?: number, signal?: AbortSignal): Promise<NoticeSummary[]> {
  const page = object(await apiGet<unknown>("/notifications", {
    template: "DELAY", status: "draft", order_id: orderId,
  }, signal));
  if (!Array.isArray(page.items)) throw new Error("Notification list is unavailable.");
  return page.items.map(summary);
}

export async function fetchNotice(id: number, signal?: AbortSignal): Promise<NoticeDetail> {
  const raw = object(await apiGet<unknown>(`/notifications/${id}`, undefined, signal));
  const base = summary(raw);
  const window = raw.eta_window === null ? null : object(raw.eta_window);
  if (typeof raw.market_timezone !== "string" || typeof raw.body_text !== "string" ||
      (window && (typeof window.start !== "string" || typeof window.end !== "string"))) {
    throw new Error("Notification detail is incomplete.");
  }
  return {
    ...base, marketTimezone: raw.market_timezone,
    subject: typeof raw.subject === "string" ? raw.subject : null,
    bodyText: raw.body_text,
    etaWindow: window ? {
      start: window.start as string, end: window.end as string,
      version: typeof window.version === "number" && Number.isInteger(window.version) && window.version > 0
        ? window.version : null,
    } : null,
  };
}

export async function sendNotice(id: number, payload: SendPayload, key: string): Promise<string> {
  const response = object(await apiPost<unknown>(`/notifications/${id}/send`, payload, key));
  if (typeof response.status !== "string") throw new Error("Send status is unavailable.");
  return response.status;
}

export async function discardNotice(id: number, reason: string): Promise<string> {
  const response = object(await apiPost<unknown>(`/notifications/${id}/discard`, { reason_text: reason }));
  if (typeof response.status !== "string") throw new Error("Discard status is unavailable.");
  return response.status;
}
