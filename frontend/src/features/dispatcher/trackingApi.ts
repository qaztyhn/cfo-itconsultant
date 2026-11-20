/** T17 API boundary: the backend is authoritative for trip visibility and handover.
 * Candidate discovery is MSW-only until T15 approves a read contract in docs/06.
 */
import { apiGet, apiPost } from "../../api/client";

export interface LiveTrip {
  trip_id: number;
  order_id: number;
  vehicle_code: string;
  last_position: { lat: number; lon: number } | null;
  remaining_km: number | null;
  updated_at: string | null;
  forecast_eta: string | null;
  risk: { status: string; color: string } | null;
  open_incident: string | null;
}

export interface EligibleDispatcher {
  employee_id: number;
  display_name: string;
}

/** Not a real endpoint: never request receiver candidates from production. */
export const candidatesAreMockOnly =
  import.meta.env.MODE === "test" ||
  (import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === "true");

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error("Invalid live trip response");
  return value;
}

/** T13 serializes PostgreSQL Numeric distance as a decimal string; accept both representations. */
function optionalDistance(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const parsed = typeof value === "number" ? value :
    (typeof value === "string" && /^\d+(?:\.\d+)?$/.test(value) ? Number(value) : NaN);
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error("Invalid live trip response");
  return parsed;
}

function optionalDate(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) {
    throw new Error("Invalid live trip response");
  }
  return value;
}

function parseTrip(value: unknown): LiveTrip {
  if (!object(value) || !Number.isSafeInteger(value.trip_id) || Number(value.trip_id) <= 0 ||
      !Number.isSafeInteger(value.order_id) || Number(value.order_id) <= 0 ||
      typeof value.vehicle_code !== "string" || !value.vehicle_code.trim()) {
    throw new Error("Invalid live trip response");
  }
  let position: LiveTrip["last_position"] = null;
  if (value.last_position !== null && value.last_position !== undefined) {
    if (!object(value.last_position)) throw new Error("Invalid live trip response");
    const lat = optionalNumber(value.last_position.lat);
    const lon = optionalNumber(value.last_position.lon);
    if (lat === null || lon === null || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      throw new Error("Invalid live trip response");
    }
    position = { lat, lon };
  }
  const risk = value.risk;
  if (risk !== null && risk !== undefined &&
      (!object(risk) || (risk.status !== null && typeof risk.status !== "string") ||
        (risk.color !== null && typeof risk.color !== "string"))) {
    throw new Error("Invalid live trip response");
  }
  if (value.open_incident !== null && value.open_incident !== undefined &&
      typeof value.open_incident !== "string") {
    throw new Error("Invalid live trip response");
  }
  return {
    trip_id: Number(value.trip_id), order_id: Number(value.order_id),
    vehicle_code: value.vehicle_code,
    last_position: position, remaining_km: optionalDistance(value.remaining_km),
    updated_at: optionalDate(value.updated_at), forecast_eta: optionalDate(value.forecast_eta),
    risk: risk == null || (risk as { status: string | null }).status === null ||
      (risk as { color: string | null }).color === null ? null : {
        status: (risk as { status: string }).status,
        color: (risk as { color: string }).color,
      },
    open_incident: (value.open_incident as string | null | undefined) ?? null,
  };
}

export async function getLiveTrips(signal?: AbortSignal): Promise<LiveTrip[]> {
  const response = await apiGet<unknown>("/gps/live", undefined, signal);
  // /gps/live is an array, NOT a market-wide object or a paginated positions list.
  if (!Array.isArray(response)) throw new Error("Invalid live trip response");
  const trips = response.map(parseTrip);
  if (new Set(trips.map((trip) => trip.trip_id)).size !== trips.length) {
    throw new Error("Duplicate trip in live response");
  }
  return trips;
}

export async function getMockEligibleDispatchers(tripId: number, signal?: AbortSignal): Promise<EligibleDispatcher[]> {
  if (!candidatesAreMockOnly) throw new Error("Eligible Dispatcher API contract pending T15");
  // Clearly namespaced MSW fixture, NOT a production API contract or fallback to /employees.
  const value = await apiGet<unknown>("/__mock/t17/trips/" + tripId + "/eligible-dispatchers", undefined, signal);
  if (!object(value) || !Array.isArray(value.items)) throw new Error("Invalid candidate list");
  const items: EligibleDispatcher[] = [];
  const seen = new Set<number>();
  for (const candidate of value.items) {
    if (!object(candidate) || !Number.isSafeInteger(candidate.employee_id) ||
        Number(candidate.employee_id) <= 0 || typeof candidate.display_name !== "string" ||
        !candidate.display_name.trim() || seen.has(Number(candidate.employee_id))) {
      throw new Error("Invalid candidate list");
    }
    seen.add(Number(candidate.employee_id));
    items.push({ employee_id: Number(candidate.employee_id), display_name: candidate.display_name });
  }
  return items;
}

export function handoverTrip(tripId: number, toEmployeeId: number, reasonText: string): Promise<unknown> {
  if (!candidatesAreMockOnly) {
    // Remove the block only after the real candidate-list read contract is approved and wired.
    throw new Error("Eligible Dispatcher API contract pending T15");
  }
  return apiPost<unknown>("/trips/" + tripId + "/handover", {
    to_employee_id: toEmployeeId, reason_text: reasonText.trim(),
  });
}
