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

export type DriverEventType = "DISPATCHED" | "DELIVERED" | "FAILED";
export type DriverEventPayload =
  | { trip_id: number }
  | { trip_id: number; recipient_name: string; note?: string }
  | { trip_id: number; failure_reason: string; note?: string };

export type DriverEvent = {
  event_type: DriverEventType;
  occurred_at: string;
  payload: DriverEventPayload;
};

export type EventAck = { event_id: number; order_status: string };

export function assignedTrips(): Promise<DriverTrip[]> {
  return apiGet<TripList>("/driver/trips").then((response) => response.items);
}

export function assignedTrip(tripId: number): Promise<DriverTrip> {
  return apiGet<DriverTrip>(`/driver/trips/${tripId}`);
}

export function submitDriverEvent(orderId: number, event: DriverEvent, key: string): Promise<EventAck> {
  return apiPost<EventAck>(`/orders/${orderId}/events`, event, key);
}

/** No GPS POST here: current main registers a NotImplementedError endpoint,
 * and real-worker consent, qualified duty windows and privacy approval are not proven.
 * Never collect, persist or upload coordinates without that reviewed handoff.
 */
