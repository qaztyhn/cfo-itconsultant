/** Exact M6 execution POST contract (docs/06 §8; merged backend #129).
 * No automatic confirmation, schedule edit, or inferred capacity occurs here.
 */
import { apiPost, newIdempotencyKey } from "../../../api/client";
import type { PrepQueueOrder } from "./types";

export type PrepEventType =
  | "START_PREP" | "PREP_PAUSED" | "PREP_RESUMED" | "GOODS_READY" | "LOADED"
  | "SHORTAGE" | "BREAKAGE" | "VEHICLE_ISSUE" | "SHIFT_CHANGE";

export type EventPayload = Record<string, string | number>;
export interface EventRequest {
  orderId: number;
  event_type: PrepEventType;
  occurred_at: string;
  payload: EventPayload;
}
export interface PreparedEvent extends EventRequest { key: string }
export interface EventAck { event_id: number; order_status: string; risk?: unknown; actual_labour_hours?: string }

export const EXCEPTION_ACTIONS = ["SHORTAGE", "BREAKAGE", "VEHICLE_ISSUE", "SHIFT_CHANGE"] as const;
export const ACTION_NAMES: Record<PrepEventType, string> = {
  START_PREP: "Start preparation",
  PREP_PAUSED: "Pause preparation",
  PREP_RESUMED: "Resume preparation",
  GOODS_READY: "Goods ready",
  LOADED: "Mark loaded",
  SHORTAGE: "Report shortage",
  BREAKAGE: "Report breakage",
  VEHICLE_ISSUE: "Report vehicle issue",
  SHIFT_CHANGE: "Report shift change",
};

/** Read-only UI eligibility; server still verifies roles, warehouse, plan, time and transitions. */
export function canPerform(order: PrepQueueOrder, type: PrepEventType, tripId?: number): boolean {
  switch (type) {
    case "START_PREP": return order.status === "APPROVED";
    case "PREP_PAUSED": return order.status === "PREPARING" && order.prep_state === "running";
    case "PREP_RESUMED": return order.status === "PREPARING" && order.prep_state === "paused";
    case "GOODS_READY": return order.status === "PREPARING" && order.prep_state === "running";
    case "LOADED": return order.status === "GOODS_READY" && order.loading.some((v) => v.trip_id === tripId && !v.loaded);
    default: return !["DELIVERED", "FAILED", "CANCELLED"].includes(order.status);
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
    case "PREP_RESUMED":
      positive("crew_size"); break;
    case "LOADED":
      positive("trip_id"); break;
    case "SHORTAGE":
    case "BREAKAGE":
      if (typeof payload.sku !== "string" || !payload.sku.trim()) throw new Error("Local SKU is required.");
      positive(event_type === "SHORTAGE" ? "qty_missing" : "qty");
      break;
    case "VEHICLE_ISSUE":
      positive("vehicle_id"); break;
    case "SHIFT_CHANGE":
      if (typeof payload.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(payload.date)) throw new Error("Enter the shift date.");
      if (typeof payload.staff_present !== "number" || !Number.isSafeInteger(payload.staff_present) || payload.staff_present < 0) {
        throw new Error("Staff present must be a nonnegative whole number.");
      }
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
