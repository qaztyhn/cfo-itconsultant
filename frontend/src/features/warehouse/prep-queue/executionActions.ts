/** Round 3 E3 execution events (docs/06 §§8.1, 19.3).
 * No automatic confirmation, schedule edit, or inferred capacity occurs here.
 */
import { apiPost, isApiError, newIdempotencyKey } from "../../../api/client";
import type { PrepQueueOrder } from "./types";

export type PrepEventType = "START_PREP" | "GOODS_READY" | "LOADED" | "SHORTAGE" | "BREAKAGE";

export type EventPayload = Record<string, string | number>;
export interface EventRequest {
  orderId: number;
  event_type: PrepEventType;
  occurred_at: string;
  payload: EventPayload;
}
export interface PreparedEvent extends EventRequest { key: string }
export interface EventAck { event_id: number; order_status: string; risk?: unknown; actual_labour_hours?: string }

export const EXCEPTION_ACTIONS = ["SHORTAGE", "BREAKAGE"] as const;
export const ACTION_NAMES: Record<PrepEventType, string> = {
  START_PREP: "Start preparation",
  GOODS_READY: "Goods ready",
  LOADED: "Mark loaded",
  SHORTAGE: "Report shortage",
  BREAKAGE: "Report breakage",
};

/** Read-only UI eligibility; server still verifies roles, warehouse, plan, time and transitions. */
export function canPerform(order: PrepQueueOrder, type: PrepEventType, tripId?: number): boolean {
  // next_action is the backend's permission/state decision, not a decorative label.
  // Status checks here are fail-closed safeguards; the API revalidates every event.
  switch (type) {
    case "START_PREP": return order.next_action === type && order.status === "APPROVED";
    case "GOODS_READY": return order.next_action === type && order.status === "PREPARING";
    case "LOADED": return order.next_action === type &&
      (order.status === "GOODS_READY" || order.status === "LOADED") &&
      order.loading.some((entry) => entry.trip_id === tripId && !entry.loaded);
    case "SHORTAGE":
    case "BREAKAGE": return ["APPROVED", "PREPARING", "GOODS_READY"].includes(order.status);
  }
}

export function eventDraft(orderId: number, event_type: PrepEventType, occurred_at: string, payload: EventPayload): EventRequest {
  if (!Number.isSafeInteger(orderId) || orderId <= 0) throw new Error("A valid order is required.");
  const instant = new Date(occurred_at);
  if (!/^(?:.+)(?:Z|[+-]\d\d:\d\d)$/.test(occurred_at) || Number.isNaN(instant.getTime())) {
    throw new Error("Use a valid date/time with an explicit UTC offset.");
  }
  if (instant.getTime() > Date.now() + 5 * 60_000) throw new Error("The event cannot be more than five minutes in the future.");
  const positive = (field: string) => {
    const n = payload[field];
    if (typeof n !== "number" || !Number.isSafeInteger(n) || n <= 0) throw new Error(`Enter a positive whole number for ${field}.`);
  };
  switch (event_type) {
    case "START_PREP":
      positive("crew_size"); break;
    case "LOADED":
      positive("trip_id"); break;
    case "SHORTAGE":
    case "BREAKAGE":
      if (typeof payload.sku !== "string" || !payload.sku.trim()) throw new Error("Local SKU is required.");
      positive(event_type === "SHORTAGE" ? "qty_missing" : "qty");
      break;
  }
  return { orderId, event_type, occurred_at: instant.toISOString(), payload };
}

/** Identical retry uses the SAME key, timestamp and body. A changed request is a new operation. */
export function prepareEvent(draft: EventRequest, previous?: PreparedEvent | null): PreparedEvent {
  const identical = previous &&
    previous.orderId === draft.orderId &&
    previous.event_type === draft.event_type &&
    previous.occurred_at === draft.occurred_at &&
    JSON.stringify(previous.payload) === JSON.stringify(draft.payload);
  return identical ? previous : { ...draft, key: newIdempotencyKey() };
}

export async function submitPrepEvent(event: PreparedEvent): Promise<EventAck> {
  const response = await apiPost<unknown>(`/orders/${event.orderId}/events`, {
    event_type: event.event_type,
    occurred_at: event.occurred_at,
    payload: event.payload,
  }, event.key);
  if (!response || typeof response !== "object" || typeof (response as EventAck).event_id !== "number" ||
      !Number.isSafeInteger((response as EventAck).event_id) || (response as EventAck).event_id <= 0) {
    throw new Error("The server did not return a verified event acknowledgment. Retry the same operation.");
  }
  return response as EventAck;
}

/** Convert an explicitly entered device-local clock instant to the API's offset-aware UTC instant. */
export function localOccurredAt(value: string): string {
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(value)) throw new Error("Select when this event happened.");
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) throw new Error("Invalid device-local timestamp.");
  // Reject nonexistent DST times instead of silently shifting the requested wall time.
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const date = String(parsed.getDate()).padStart(2, "0");
  const hours = String(parsed.getHours()).padStart(2, "0");
  const mins = String(parsed.getMinutes()).padStart(2, "0");
  if (`${year}-${month}-${date}T${hours}:${mins}` !== value) throw new Error("The selected local time does not exist.");
  return parsed.toISOString();
}

export function nowLocal(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

/** No raw upstream message or PII is reflected to warehouse staff. */
export function safeActionError(cause: unknown): string {
  if (!isApiError(cause)) return "Confirmation could not be verified. The server may already have recorded it; retry the exact same event.";
  if (cause.status === 401) return "Session expired. Sign in again; the event is not confirmed.";
  if (cause.status === 403) return "Not authorized for this warehouse or event. No completion was confirmed.";
  if (cause.status === 404) return "Order, trip or warehouse not available in your scope. Refresh the queue.";
  if (cause.status === 409) return "Event rejected: invalid order or loading sequence, or data changed. Refresh the queue before deciding what to do.";
  if (cause.status === 422) return "The server rejected the event. Review the crew, time and report fields.";
  if (cause.status === 503 || cause.status === 0) return "Connection or mandatory service unavailable. Completion is unconfirmed; retry the same operation.";
  return "Event not confirmed. Check the queue and retry the same operation if needed.";
}
