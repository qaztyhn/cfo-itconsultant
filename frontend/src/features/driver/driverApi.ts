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

/** Turn on only after the BE-05 stop-scoped execution API (#188) is deployed.
 * Default OFF preserves the merged single-stop contract on main.
 */
export function stopScopedPodEnabled(): boolean {
  return import.meta.env.VITE_DRIVER_STOP_POD_ENABLED === "true";
}

export type DriverEventType = "DISPATCHED" | "DELIVERED" | "FAILED";
export type DriverEventPayload =
  | { trip_id: number }
  | { trip_id: number; trip_stop_id?: number; recipient_name: string; note?: string }
  | { trip_id: number; trip_stop_id?: number; failure_reason: string; note?: string };

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

/** No GPS POST here: current main registers a NotImplementedError endpoint,
 * and real-worker consent, qualified duty windows and privacy approval are not proven.
 * Never collect, persist or upload coordinates without that reviewed handoff.
 */
