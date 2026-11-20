/** T17 MSW-only synthetic pilot: not an authorization source in production.
 * Three on_road trips; two belong to one order. A handover mutates only one trip.
 */
import { http, HttpResponse } from "msw";
import { API_BASE_URL } from "../config";
import { accountFromRequest, errorResponse } from "./authHandlers";

const BASE = API_BASE_URL;
const eligible = [
  { employee_id: 101, display_name: "Anna Lindqvist" },
  { employee_id: 109, display_name: "Erik Holm" },
];
const liveTrips = [
  {
    trip_id: 930, order_id: 249, vehicle_code: "STO-12-04",
    last_position: { lat: 57.70, lon: 11.97 }, remaining_km: 12,
    updated_at: "2026-11-12T09:52:00Z", forecast_eta: "2026-11-12T10:20:00Z",
    risk: { status: "ON_TRACK", color: "green" }, open_incident: null,
  },
  {
    trip_id: 931, order_id: 249, vehicle_code: "STO-18-01",
    last_position: null, remaining_km: null, updated_at: null,
    forecast_eta: "2026-11-12T11:00:00Z",
    risk: { status: "AT_RISK", color: "yellow" }, open_incident: null,
  },
  {
    trip_id: 932, order_id: 250, vehicle_code: "STO-07-02",
    last_position: { lat: 59.33, lon: 18.06 }, remaining_km: null,
    updated_at: "2026-11-12T09:40:00Z", forecast_eta: null,
    risk: { status: "PREDICTED_LATE", color: "red" }, open_incident: "vehicle_breakdown",
  },
];

const assignments = new Map<number, number>([[930, 101], [931, 101], [932, 101]]);

function dispatcher(request: Request) {
  const account = accountFromRequest(request);
  if (!account) return { account: null, denied: errorResponse(request, 401, "AUTH_INVALID", "Sign in required.") };
  if (!account.user.roles.includes("dispatcher") || account.user.employee_id === null) {
    return { account: null, denied: errorResponse(request, 403, "FORBIDDEN", "Dispatcher access required.") };
  }
  return { account, denied: null };
}

export const trackingHandlers = [
  http.get(BASE + "/gps/live", ({ request }) => {
    const auth = dispatcher(request);
    if (auth.denied) return auth.denied;
    const employeeId = auth.account!.user.employee_id;
    return HttpResponse.json(liveTrips.filter((trip) => assignments.get(trip.trip_id) === employeeId));
  }),
  // Deliberately NOT in docs/06: mocked candidate discovery only.
  http.get(BASE + "/__mock/t17/trips/:id/eligible-dispatchers", ({ request, params }) => {
    const auth = dispatcher(request);
    if (auth.denied) return auth.denied;
    const tripId = Number(params.id);
    if (!liveTrips.some((trip) => trip.trip_id === tripId) ||
        !assignments.has(tripId)) {
      return errorResponse(request, 404, "NOT_FOUND", "Trip not found.");
    }
    return HttpResponse.json({ items: eligible });
  }),
  http.post(BASE + "/trips/:id/handover", async ({ request, params }) => {
    const auth = dispatcher(request);
    if (auth.denied) return auth.denied;
    const tripId = Number(params.id);
    if (!liveTrips.some((trip) => trip.trip_id === tripId) || !assignments.has(tripId)) {
      return errorResponse(request, 404, "NOT_FOUND", "Trip not found.");
    }
    const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
    if (typeof body?.reason_text !== "string" || !body.reason_text.trim()) {
      return errorResponse(request, 422, "REASON_REQUIRED", "Handover reason required.");
    }
    if (!eligible.some((candidate) => candidate.employee_id === body.to_employee_id) ||
        assignments.get(tripId) === body.to_employee_id) {
      return errorResponse(request, 422, "VALIDATION_ERROR", "Recipient is not eligible.");
    }
    assignments.set(tripId, Number(body.to_employee_id));
    return HttpResponse.json({ trip_id: tripId, assigned_dispatcher_employee_id: body.to_employee_id });
  }),
];
