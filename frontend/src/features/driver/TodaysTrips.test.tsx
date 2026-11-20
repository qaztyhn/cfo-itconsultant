/** T16 contract tests use MSW interceptors, not a mocked driver API. */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../../api/config";
import { handlers } from "../../api/mocks/handlers";
import { renderAt, signInAs, userByEmail } from "../../test/utils";
import type { DriverTrip } from "./driverApi";

const base: DriverTrip = {
  trip_id: 12, warehouse_id: 3, warehouse_code: "GBG", vehicle_code: "V-12",
  status: "on_road", depart_planned_at: "2026-11-09T08:00:00Z",
  depart_actual_at: "2026-11-09T08:03:00Z",
  stops: [{
    trip_stop_id: 30, order_id: 44, order_no: "SE-44", status: "pending",
    eta_planned_at: "2026-11-09T12:00:00Z", delivery_address: "Synthetic site",
    contact_name: "Test contact", contact_phone: null,
    receiving_window: { start: "09:00", end: "13:00" }, special_requirements: null,
  }],
};
const other: DriverTrip = {
  ...base, trip_id: 13, vehicle_code: "V-13", stops: [{
    ...base.stops[0], trip_stop_id: 31, order_id: 45, order_no: "SE-45",
  }],
};
const server = setupServer(...handlers);
const FIX_AT = new Date("2026-11-09T09:05:00+01:00").getTime();
const fix = { coords: { latitude: 57.7, longitude: 11.97, accuracy: 12 }, timestamp: FIX_AT };
let geo: ReturnType<typeof vi.fn>;
let calls: Array<{ path: string; key: string | null; body: unknown }>;
const gpsRoute = `${API_BASE_URL}/trips/:id/positions`;
const eventRoute = `${API_BASE_URL}/orders/:id/events`;

function intercept(trips: DriverTrip[] = [base]) {
  server.use(
    http.get(`${API_BASE_URL}/driver/trips`, () => HttpResponse.json({ items: trips })),
    http.post(gpsRoute, async ({ request, params }) => {
      const body = await request.json() as { recorded_at: string };
      calls.push({ path: `/trips/${params.id}/positions`, key: request.headers.get("Idempotency-Key"), body });
      return HttpResponse.json({
        accepted: 1, trip_id: Number(params.id), recorded_at: body.recorded_at,
        remaining_km: "5.200", remaining_min: 9, provider: "fallback",
      }, { status: 202 });
    }),
    http.post(eventRoute, async ({ request, params }) => {
      calls.push({ path: `/orders/${params.id}/events`, key: request.headers.get("Idempotency-Key"), body: await request.json() });
      return HttpResponse.json({ event_id: 1001, order_status: "DISPATCHED" });
    }),
  );
}

async function openTrip(index = 0) {
  renderAt("/driver");
  await screen.findAllByText("SE-44 · Synthetic site");
  const buttons = screen.getAllByRole("button", { name: "Record delivery outcome" });
  await userEvent.click(buttons[index]);
}

async function consent() {
  await userEvent.click(screen.getByRole("checkbox", { name: /I have read the location privacy notice/ }));
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  calls = [];
  signInAs(userByEmail("driver1@cfo.demo"));
  geo = vi.fn((success: (value: GeolocationPosition) => void) => success(fix as GeolocationPosition));
  Object.defineProperty(navigator, "geolocation", {
    configurable: true, value: { getCurrentPosition: geo },
  });
  intercept();
});
afterEach(() => { server.resetHandlers(); vi.restoreAllMocks(); });
afterAll(() => server.close());

describe("R3 Driver one-fix request and event contract", () => {
  it("test_US_GPS_01_AC4_uses_one_fix_only_after_consent_and_202_ACK", async () => {
    await openTrip();
    expect(screen.getByRole("button", { name: "Update location" })).toBeDisabled();
    expect(geo).not.toHaveBeenCalled();
    await consent();
    await userEvent.click(screen.getByRole("button", { name: "Update location" }));
    expect(await screen.findByText(/Position sent/)).toBeInTheDocument();
    expect(geo).toHaveBeenCalledTimes(1);
    expect(calls).toHaveLength(1);
    expect(calls[0].path).toBe("/trips/12/positions");
    expect(calls[0].key).toMatch(/^[0-9a-f-]{36}$/i);
    expect(calls[0].body).toEqual({
      lat: 57.7, lon: 11.97, accuracy_m: 12, recorded_at: "2026-11-09T08:05:00.000Z",
    });
    expect(screen.queryByRole("button", { name: "Retry same request" })).toBeNull();
  });

  it("test_US_EXE_02_AC8_DELIVERED_requires_fresh_position_on_correct_order_and_trip", async () => {
    intercept([base, other]);
    await openTrip(1);
    await consent();
    await userEvent.type(screen.getByRole("textbox", { name: "Received by" }), "Test recipient");
    await userEvent.click(screen.getByRole("button", { name: "Confirm delivered" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].path).toBe("/orders/45/events");
    expect(calls[0].body).toEqual({
      event_type: "DELIVERED", occurred_at: expect.any(String),
      payload: { trip_id: 13, recipient_name: "Test recipient",
        position: { lat: 57.7, lon: 11.97, accuracy_m: 12, recorded_at: "2026-11-09T08:05:00.000Z" },
      },
    });
  });

  it("test_US_EXE_02_AC8_two_vehicles_same_order_target_only_the_selected_trip", async () => {
    const sibling = { ...other, stops: [{ ...other.stops[0], order_id: 44, order_no: "SE-44" }] };
    intercept([base, sibling]);
    await openTrip(1);
    await consent();
    await userEvent.type(screen.getByRole("textbox", { name: "Received by" }), "Synthetic recipient");
    await userEvent.click(screen.getByRole("button", { name: "Confirm delivered" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].path).toBe("/orders/44/events");
    expect(calls[0].body).toMatchObject({
      event_type: "DELIVERED",
      payload: { trip_id: 13, recipient_name: "Synthetic recipient", position: {
        lat: 57.7, lon: 11.97, accuracy_m: 12, recorded_at: "2026-11-09T08:05:00.000Z",
      } },
    });
    expect(geo).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Back to trips" }));
    expect(screen.getByText("Trip 12 · V-12")).toBeInTheDocument();
    expect(screen.getByText("Trip 13 · V-13")).toBeInTheDocument();
  });

  it("test_US_EXE_02_AC8_FAILED_includes_position_and_reason", async () => {
    await openTrip();
    await consent();
    await userEvent.click(screen.getByRole("radio", { name: "Failed" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Failure reason" }), "customer_absent");
    await userEvent.click(screen.getByRole("button", { name: "Confirm failed" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].path).toBe("/orders/44/events");
    expect(calls[0].body).toEqual({
      event_type: "FAILED", occurred_at: expect.any(String),
      payload: { trip_id: 12, failure_reason: "customer_absent",
        position: { lat: 57.7, lon: 11.97, accuracy_m: 12, recorded_at: "2026-11-09T08:05:00.000Z" },
      },
    });
  });

  it("test_US_EXE_02_AC8_location_denied_blocks_completion_but_allows_incident_without_point", async () => {
    geo.mockImplementation((_success: unknown, failure: (error: unknown) => void) => failure({ code: 1 }));
    await openTrip();
    await consent();
    await userEvent.type(screen.getByRole("textbox", { name: "Received by" }), "Test recipient");
    await userEvent.click(screen.getByRole("button", { name: "Confirm delivered" }));
    expect(await screen.findByText(/Location denied or timed out/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Report incident" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({
      event_type: "DRIVER_INCIDENT", occurred_at: expect.any(String),
      payload: { trip_id: 12, reason: "traffic_or_accident" },
    });
  });

  it("test_US_EXE_02_AC8_timeout_blocks_failed_but_not_incident", async () => {
    geo.mockImplementation((_success: unknown, failure: (error: unknown) => void) => failure({ code: 3 }));
    await openTrip();
    await consent();
    await userEvent.click(screen.getByRole("radio", { name: "Failed" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Failure reason" }), "customer_absent");
    await userEvent.click(screen.getByRole("button", { name: "Confirm failed" }));
    expect(await screen.findByText(/Location denied or timed out/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Report incident" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({
      event_type: "DRIVER_INCIDENT", payload: { trip_id: 12, reason: "traffic_or_accident" },
    });
    expect((calls[0].body as { payload: Record<string, unknown> }).payload).not.toHaveProperty("position");
  });

  it("test_US_EXE_05_AC1_other_without_note_never_posts_and_breakdown_uses_incident_reason", async () => {
    await openTrip();
    await consent();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Incident reason" }), "other");
    expect(screen.getByRole("button", { name: "Report incident" })).toBeDisabled();
    expect(calls).toHaveLength(0);
    await userEvent.type(screen.getByRole("textbox", { name: /Incident note/ }), "Cannot reach the site");
    await userEvent.click(screen.getByRole("button", { name: "Report incident" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({
      event_type: "DRIVER_INCIDENT", occurred_at: expect.any(String),
      payload: { trip_id: 12, reason: "other", note: "Cannot reach the site",
        position: { lat: 57.7, lon: 11.97, accuracy_m: 12, recorded_at: "2026-11-09T08:05:00.000Z" },
      },
    });
  });

  it("test_US_GPS_01_AC4_does_not_show_position_sent_until_real_202_ACK", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    server.use(http.post(gpsRoute, async ({ request, params }) => {
      const body = await request.json() as { recorded_at: string };
      calls.push({ path: `/trips/${params.id}/positions`, key: request.headers.get("Idempotency-Key"), body });
      await gate;
      return HttpResponse.json({
        accepted: 1, trip_id: Number(params.id), recorded_at: body.recorded_at,
        remaining_km: "5.200", remaining_min: 9, provider: "fallback",
      }, { status: 202 });
    }));
    await openTrip();
    await consent();
    await userEvent.click(screen.getByRole("button", { name: "Update location" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(screen.queryByText(/Position sent/)).toBeNull();
    expect(screen.getByRole("button", { name: "Update location" })).toBeDisabled();
    release();
    expect(await screen.findByText(/Position sent/)).toBeInTheDocument();
  });

  it("test_US_GPS_01_AC4_hanging_post_times_out_and_retry_reuses_original_point_and_key", async () => {
    const received: Array<{ key: string | null; body: unknown }> = [];
    let releaseFirst!: (response: HttpResponse) => void;
    const stalled = new Promise<HttpResponse>((resolve) => { releaseFirst = resolve; });
    server.use(http.post(gpsRoute, async ({ request, params }) => {
      const body = await request.json() as { recorded_at: string };
      received.push({ key: request.headers.get("Idempotency-Key"), body });
      return received.length === 1 ? stalled : HttpResponse.json({
        accepted: 1, trip_id: Number(params.id), recorded_at: body.recorded_at,
        remaining_km: "5.200", remaining_min: 9, provider: "fallback",
      }, { status: 202 });
    }));
    await openTrip();
    await consent();
    // Accelerate only the component's 15s HTTP ACK deadline; MSW still stalls the first POST.
    const rawSetTimeout = window.setTimeout.bind(window);
    vi.spyOn(window, "setTimeout").mockImplementation(
      (handler: TimerHandler, timeout?: number, ...args: unknown[]) =>
        rawSetTimeout(handler, timeout === 15_000 ? 60 : timeout, ...args),
    );
    await userEvent.click(screen.getByRole("button", { name: "Update location" }));
    expect(await screen.findByRole("button", { name: "Retry same request" })).toBeEnabled();
    expect(screen.queryByText(/Position sent/)).toBeNull();
    expect(received).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Retry same request" }));
    expect(await screen.findByText(/Position sent/)).toBeInTheDocument();
    expect(received).toHaveLength(2);
    expect(received[1]).toEqual(received[0]);
    expect(geo).toHaveBeenCalledTimes(1);
    // The timed-out original can finish later without a second UI success.
    releaseFirst(HttpResponse.json({ accepted: 1 }));
  });

  it("test_US_GPS_01_AC4_network_unknown_retry_keeps_same_key_and_body_and_does_not_resample", async () => {
    let number = 0;
    const received: Array<{ key: string | null; body: unknown }> = [];
    server.use(http.post(gpsRoute, async ({ request, params }) => {
      received.push({ key: request.headers.get("Idempotency-Key"), body: await request.json() });
      number += 1;
      return number === 1 ? HttpResponse.error() : HttpResponse.json({
        accepted: 1, trip_id: Number(params.id),
        recorded_at: "2026-11-09T08:05:00.000Z",
        remaining_km: 1, remaining_min: 2, provider: "ors",
      }, { status: 202 });
    }));
    await openTrip();
    await consent();
    await userEvent.click(screen.getByRole("button", { name: "Update location" }));
    expect(await screen.findByRole("button", { name: "Retry same request" })).toBeEnabled();
    expect(screen.queryByText(/Position sent/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry same request" }));
    expect(await screen.findByText(/Position sent/)).toBeInTheDocument();
    expect(received).toHaveLength(2);
    expect(received[0]).toEqual(received[1]);
    expect(geo).toHaveBeenCalledTimes(1);
  });

  it("test_US_EXE_05_AC1_network_unknown_retry_preserves_event_occurred_at_and_position", async () => {
    const posts: Array<{ key: string | null; body: unknown }> = [];
    server.use(http.post(eventRoute, async ({ request }) => {
      posts.push({ key: request.headers.get("Idempotency-Key"), body: await request.json() });
      return posts.length === 1 ? HttpResponse.error() : HttpResponse.json({ event_id: 10, order_status: "DISPATCHED" });
    }));
    await openTrip();
    await consent();
    await userEvent.click(screen.getByRole("button", { name: "Report incident" }));
    expect(await screen.findByRole("button", { name: "Retry same request" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Retry same request" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[0]).toEqual(posts[1]);
    expect(geo).toHaveBeenCalledTimes(1);
  });

  it("test_US_EXE_02_AC8_uncertain_DELIVERED_retry_keeps_endpoint_key_timestamps_and_point", async () => {
    const posts: Array<{ path: string; key: string | null; body: unknown }> = [];
    server.use(http.post(eventRoute, async ({ request, params }) => {
      posts.push({
        path: `/orders/${params.id}/events`, key: request.headers.get("Idempotency-Key"),
        body: await request.json(),
      });
      return posts.length === 1 ? HttpResponse.error()
        : HttpResponse.json({ event_id: 1001, order_status: "DELIVERED" });
    }));
    await openTrip();
    await consent();
    await userEvent.type(screen.getByRole("textbox", { name: "Received by" }), "Test recipient");
    await userEvent.click(screen.getByRole("button", { name: "Confirm delivered" }));
    expect(await screen.findByRole("button", { name: "Retry same request" })).toBeEnabled();
    expect(screen.queryByText(/DELIVERED acknowledged/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry same request" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[0].path).toBe("/orders/44/events");
    expect(posts[1]).toEqual(posts[0]);
    expect(posts[0].body).toMatchObject({
      event_type: "DELIVERED", occurred_at: expect.any(String),
      payload: { trip_id: 12, position: { recorded_at: "2026-11-09T08:05:00.000Z" } },
    });
    expect(geo).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/DELIVERED acknowledged/)).toBeInTheDocument();
  });

  it("test_US_GPS_01_AC4_position_ack_is_scoped_to_the_selected_trip", async () => {
    intercept([base, other]);
    await openTrip(0);
    await consent();
    await userEvent.click(screen.getByRole("button", { name: "Update location" }));
    expect(await screen.findByText(/Last position sent/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Back to trips" }));
    await userEvent.click(screen.getAllByRole("button", { name: "Record delivery outcome" })[1]);
    expect(screen.queryByText(/Last position sent/)).toBeNull();
    expect(screen.getByRole("button", { name: "Update location" })).toBeEnabled();
  });

  it("test_US_GPS_01_AC4_terminal_trip_has_no_location_or_completion_action", async () => {
    intercept([{ ...base, status: "completed" }]);
    renderAt("/driver");
    await screen.findByText("SE-44 · Synthetic site");
    await userEvent.click(screen.getByRole("button", { name: "View trip" }));
    expect(screen.getByText(/Trip ended. No further updates/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Update location" })).toBeNull();
    expect(geo).not.toHaveBeenCalled();
  });
});
