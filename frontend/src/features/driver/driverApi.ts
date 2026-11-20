/** Driver-only API contracts from docs/06 §8 and the current execution router.
 * The OpenAPI generated schema is not yet checked in. These types describe only
 * fields actually returned by execution_service.driver_trips; no speculative GPS data.
 */
import { apiGet, apiPost } from "../../api/client";

export type DriverStop = {
  trip_stop_id: number;
  order_id: number;
  order_no: string;
  status: string;
  eta_planned_at: string;
  delivery_address: string;
  contact_name: string;
  contact_phone: string | null;
  receiving_window: { start: string | null; end: string | null };
  special_requirements: string | null;
};

export type DriverTrip = {
  trip_id: number;
  warehouse_id: number;
  warehouse_code: string;
  vehicle_code: string;
  status: string;
  depart_planned_at: string;
  depart_actual_at: string | null;
  stops: DriverStop[];
};

type TripList = { items: DriverTrip[] };

export type DriverPosition = {
  lat: number;
  lon: number;
  accuracy_m: number;
  recorded_at: string;
};

export type DriverEventType = "DISPATCHED" | "DELIVERED" | "FAILED" | "DRIVER_INCIDENT";
export type DriverEventPayload =
  | { trip_id: number }
  | { trip_id: number; recipient_name: string; position: DriverPosition }
  | { trip_id: number; failure_reason: string; position: DriverPosition; note?: string }
  | { trip_id: number; reason: "vehicle_breakdown" | "traffic_or_accident" | "site_inaccessible" | "other"; note?: string; position?: DriverPosition };

export type DriverEvent = {
  event_type: DriverEventType;
  occurred_at: string;
  payload: DriverEventPayload;
};

export type EventAck = { event_id: number; order_status: string };

function isAssignedTrip(value: unknown): value is DriverTrip {
  if (!value || typeof value !== "object") return false;
  const trip = value as Partial<DriverTrip>;
  return typeof trip.trip_id === "number" && typeof trip.vehicle_code === "string" &&
    typeof trip.status === "string" && Array.isArray(trip.stops) &&
    trip.stops.every((stop) => stop && typeof stop.order_id === "number" &&
      typeof stop.trip_stop_id === "number" && typeof stop.order_no === "string");
}

export function assignedTrips(): Promise<DriverTrip[]> {
  return apiGet<TripList>("/driver/trips").then((response) =>
    Array.isArray(response?.items) ? response.items.filter(isAssignedTrip) : [],
  );
}

export async function assignedTrip(tripId: number): Promise<DriverTrip> {
  const trip = await apiGet<DriverTrip>(`/driver/trips/${tripId}`);
  if (!isAssignedTrip(trip)) throw new Error("Unverified trip contract.");
  return trip;
}

export function submitDriverEvent(orderId: number, event: DriverEvent, key: string): Promise<EventAck> {
  return apiPost<EventAck>(`/orders/${orderId}/events`, event, key);
}

/**
 * T13 receives one driver-initiated position per POST. A retry reuses the
 * exact point and key; the browser does not batch, persist, or poll GPS.
 */
export type PositionAck = {
  accepted: number;
  trip_id: number;
  recorded_at: string;
  remaining_km: string | number;
  remaining_min: number;
  provider: "ors" | "fallback";
};

export function submitPosition(tripId: number, point: DriverPosition, key: string): Promise<PositionAck> {
  return apiPost<PositionAck>(`/trips/${tripId}/positions`, point, key);
}
