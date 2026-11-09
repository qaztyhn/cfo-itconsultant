import { apiFetch, buildQuery } from "../../api/client";
import { USE_MOCKS } from "../../api/config";

// Shape verified against the current #129 execution service, not the older global MSW fixture.
export interface DriverStop {
  trip_stop_id: number;
  order_id: number;
  order_no: string;
  status: string;
  eta_planned_at: string;
  delivery_address: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  receiving_window: { start: string | null; end: string | null };
  special_requirements: string | null;
}
export interface DriverTrip {
  trip_id: number;
  warehouse_id: number;
  warehouse_code: string;
  vehicle_code: string;
  status: string;
  depart_planned_at: string;
  depart_actual_at: string | null;
  stops: DriverStop[];
}
export type DriverEventType = "DISPATCHED" | "DELIVERED" | "FAILED";
export interface DriverEvent {
  tripId: number;
  orderId: number;
  eventType: DriverEventType;
  occurredAt: string;
  idempotencyKey: string;
  payload: Record<string, string | number>;
}
export interface EventAck { event_id: number; order_status: string; risk: unknown }

export function isDriverTrip(value: unknown): value is DriverTrip {
  if (typeof value !== "object" || value === null) return false;
  const trip = value as Record<string, unknown>;
  return Number.isInteger(trip.trip_id) && typeof trip.status === "string" &&
    typeof trip.vehicle_code === "string" && typeof trip.warehouse_code === "string" &&
    typeof trip.depart_planned_at === "string" && Array.isArray(trip.stops) &&
    trip.stops.every((stop: unknown) => {
      if (typeof stop !== "object" || stop === null) return false;
      const row = stop as Record<string, unknown>;
      return Number.isInteger(row.trip_stop_id) && Number.isInteger(row.order_id) &&
        typeof row.order_no === "string" && typeof row.status === "string" &&
        typeof row.eta_planned_at === "string" &&
        typeof row.receiving_window === "object" && row.receiving_window !== null;
    });
}

const PREVIEW: DriverTrip = {
  trip_id: 930, warehouse_id: 3, warehouse_code: "MLM-DC", vehicle_code: "MLM-12-02",
  status: "loading", depart_planned_at: "2026-11-13T08:00:00+01:00", depart_actual_at: null,
  stops: [{ trip_stop_id: 931, order_id: 129, order_no: "SE-2026-000129", status: "pending",
    eta_planned_at: "2026-11-13T09:10:00+01:00", delivery_address: "Kvarnbyn 4, Mölndal",
    contact_name: null, contact_phone: null, receiving_window: { start: "09:00:00", end: "11:00:00" },
    special_requirements: "Report to the site office." }],
};

export async function listDriverTrips(day?: string, signal?: AbortSignal, mock = USE_MOCKS): Promise<DriverTrip[]> {
  if (mock) return [PREVIEW];
  const data = await apiFetch<{ items: DriverTrip[] }>(`/driver/trips${buildQuery({ date: day })}`, { signal });
  if (!Array.isArray(data.items) || !data.items.every(isDriverTrip)) throw new Error("Trip list response is incomplete.");
  return data.items;
}

export async function getDriverTrip(id: number, signal?: AbortSignal, mock = USE_MOCKS): Promise<DriverTrip> {
  if (mock) {
    if (id !== PREVIEW.trip_id) throw new Error("Trip not assigned.");
    return PREVIEW;
  }
  const trip = await apiFetch<DriverTrip>(`/driver/trips/${id}`, { signal });
  if (!isDriverTrip(trip) || trip.trip_id !== id) throw new Error("Trip detail response is incomplete.");
  return trip;
}

export async function sendDriverEvent(event: DriverEvent, mock = USE_MOCKS): Promise<EventAck> {
  if (mock) throw new Error("Synthetic preview cannot confirm a delivery event.");
  return apiFetch<EventAck>(`/orders/${event.orderId}/events`, {
    method: "POST", idempotencyKey: event.idempotencyKey,
    body: JSON.stringify({ event_type: event.eventType, occurred_at: event.occurredAt, payload: event.payload }),
  });
}

export function eventAllowed(trip: DriverTrip, event: DriverEvent): boolean {
  if (trip.trip_id !== event.tripId || !trip.stops.some(s => s.order_id === event.orderId && s.status === "pending")) return false;
  if (event.eventType === "DISPATCHED") return trip.status === "loading";
  return trip.status === "on_road";
}
