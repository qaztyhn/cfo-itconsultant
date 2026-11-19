import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../../api/config";
import { fetchLocations } from "../../api/locations";
import { useScopeStore } from "../../app/scope";
import { currentPath, renderAt, signInAs, userByEmail } from "../../test/utils";
import { buildPrepQueueFixture, capacityVerified, orderApproved, orderMultiVehicle } from "./prep-queue/fixtures";
import { PREP_QUEUE_URL, prepQueueFailure, prepQueueSuccess } from "./prep-queue/mswHandlers";

vi.mock("../../api/locations", () => ({ fetchLocations: vi.fn() }));

// The Sidebar asks for order counts; switch that request off so it never reaches the network.
const countsOff = http.get(`${API_BASE_URL}/orders/counts`, () => HttpResponse.json({ error: { code: "SERVICE_UNAVAILABLE", message: "off", details: {}, correlation_id: "corr-counts" } }, { status: 503 }));
const server = setupServer(countsOff);

let mswFetch: typeof fetch;

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  // Test-only workaround (same as usePrepQueue.test.tsx): jsdom's AbortSignal is rejected by Node's fetch.
  mswFetch = globalThis.fetch;
  vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => mswFetch(input, { ...init, signal: undefined }));
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  vi.unstubAllGlobals();
  server.close();
});

const GBG = { id: 1, code: "GBG", name: "Göteborg DC", type: "warehouse", timezone: "Europe/Stockholm" };
const STO = { id: 2, code: "STO", name: "Stockholm DC", type: "warehouse", timezone: "Europe/Stockholm" };
const GBG_NO_TZ = { id: 1, code: "GBG", name: "Göteborg DC", type: "warehouse" };

const OVERLINE = (name: string) => new RegExp(`^${name} · [A-Z][a-z]+ \\d{1,2} [A-Z][a-z]+$`);

beforeEach(() => {
  useScopeStore.setState({ warehouseId: null });
  vi.mocked(fetchLocations).mockReset();
  vi.mocked(fetchLocations).mockResolvedValue([GBG, STO]);
});

function signInWarehouse() {
  signInAs(userByEmail("wm.got@cfo.demo"));
}

describe("PrepQueue screen (Round 3)", () => {
  it("shows the header, capacity card and orders table for the warehouse manager's warehouse", async () => {
    const seen = vi.fn();
    server.use(prepQueueSuccess(buildPrepQueueFixture("verified"), seen));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByRole("table", { name: "Orders to prepare" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Preparation queue" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Capacity today" })).toBeInTheDocument();
    expect(screen.getByText(OVERLINE("Göteborg DC"))).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(1 + 5);
    expect(screen.getByText(/Live · refreshes every 20 s/)).toBeInTheDocument();
    expect(seen).toHaveBeenCalledWith({ warehouse_id: 1, date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/) });
  });

  it("test_US_WH_04_AC1_offers_backend-authorized milestones only", async () => {
    server.use(prepQueueSuccess());
    signInWarehouse();
    renderAt("/warehouse/prep");
    await screen.findByRole("table", { name: "Orders to prepare" });
    expect(screen.getByRole("button", { name: "Start preparation" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Goods ready" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Mark loaded · GBG-18-05" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Mark loaded · GBG-18-04" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Pause preparation|Resume preparation|Report shift change/i })).toBeNull();
  });

  it("test_US_WH_03_AC1_shows_no_equipment_row", async () => {
    server.use(prepQueueSuccess());
    signInWarehouse();
    renderAt("/warehouse/prep");

    await screen.findByRole("table", { name: "Orders to prepare" });
    expect(screen.queryByText(/equipment/i)).toBeNull();
  });

  it("shows a loading state first, then the queue", async () => {
    server.use(
      http.get(PREP_QUEUE_URL, async () => {
        await delay(50);
        return HttpResponse.json(buildPrepQueueFixture("verified"));
      }),
    );
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect((await screen.findAllByText("Loading…")).length).toBeGreaterThan(0);
    await screen.findByRole("table", { name: "Orders to prepare" });
    expect(screen.queryByText("Loading…")).toBeNull();
  });

  it("shows an empty message when there are no approved orders", async () => {
    server.use(prepQueueSuccess(buildPrepQueueFixture("empty")));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText(/No approved orders to prepare for/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it.each([
    [403, "FORBIDDEN"],
    [404, "NOT_FOUND"],
  ])("shows a permission-denied state, not data, for HTTP %i", async (status, code) => {
    server.use(prepQueueFailure(status, code, "Denied", "corr-denied"));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText("No access to this queue")).toBeInTheDocument();
    expect(screen.getByText("corr-denied")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Capacity today" })).toBeNull();
  });

  it("shows an error with correlation_id and Retry for a 500, then recovers on Retry", async () => {
    server.use(prepQueueFailure(500, "INTERNAL_ERROR", "Boom", "corr-500"));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText("The preparation queue could not be loaded")).toBeInTheDocument();
    expect(screen.getByText("corr-500")).toBeInTheDocument();

    server.use(prepQueueSuccess());
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("table", { name: "Orders to prepare" })).toBeInTheDocument();
    expect(screen.queryByText("The preparation queue could not be loaded")).toBeNull();
  });

  it("ASM-007: capacity without schedule_verified is shown as not verified", async () => {
    server.use(prepQueueSuccess(buildPrepQueueFixture("unverified")));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText("Capacity not verified.")).toBeInTheDocument();
    // The warning does not hide the orders (it records what happened; it is not an approval gate).
    expect(screen.getByRole("table", { name: "Orders to prepare" })).toBeInTheDocument();
  });

  it("test_US_WH_02_AC3_no_official_schedule_shows_no_shifts_and_no_capacity_numbers", async () => {
    server.use(prepQueueSuccess(buildPrepQueueFixture("noSchedule")));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText("No official shift schedule is entered for today.")).toBeInTheDocument();
    expect(screen.queryByText(/min booked ·/)).toBeNull();
  });

  it("stops with a clear message when the warehouse time zone is unavailable, without calling the API", async () => {
    const seen = vi.fn();
    vi.mocked(fetchLocations).mockResolvedValue([GBG_NO_TZ]);
    server.use(prepQueueSuccess(buildPrepQueueFixture("verified"), seen));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText(/The time zone of Göteborg DC is not available/)).toBeInTheDocument();
    expect(seen).not.toHaveBeenCalled();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("asks a multi-warehouse manager to pick a warehouse, then loads the picked one", async () => {
    const seen = vi.fn();
    server.use(prepQueueSuccess(buildPrepQueueFixture("verified"), seen));
    signInAs({ ...userByEmail("wm.got@cfo.demo"), location_ids: [1, 2] });
    renderAt("/warehouse/prep");

    expect(await screen.findByText("Select a warehouse in the sidebar to see its preparation queue.")).toBeInTheDocument();
    expect(seen).not.toHaveBeenCalled();

    await userEvent.setup().selectOptions(await screen.findByRole("combobox", { name: "Warehouse" }), "Stockholm DC");

    expect(await screen.findByRole("table", { name: "Orders to prepare" })).toBeInTheDocument();
    expect(seen).toHaveBeenCalledWith(expect.objectContaining({ warehouse_id: 2 }));
    expect(screen.getByText(OVERLINE("Stockholm DC"))).toBeInTheDocument();
  });

  it.each(["dispatcher@cfo.demo", "sales@cfo.demo"])("%s cannot open the screen and no queue is requested", async (email) => {
    const seen = vi.fn();
    server.use(prepQueueSuccess(buildPrepQueueFixture("verified"), seen));
    signInAs(userByEmail(email));
    renderAt("/warehouse/prep");

    await waitFor(() => expect(currentPath()).not.toBe("/warehouse/prep"));
    expect(document.querySelector('[data-screen="PrepQueue"]')).toBeNull();
    expect(seen).not.toHaveBeenCalled();
  });

  it("does not link to the removed Round 2 attendance screen", async () => {
    server.use(prepQueueSuccess());
    signInWarehouse();
    renderAt("/warehouse/prep");
    await screen.findByRole("table", { name: "Orders to prepare" });
    expect(screen.queryByRole("link", { name: "Edit shifts & staff" })).toBeNull();
  });

  it("test_US_WH_04_AC1_E3_one_order_progresses_start_ready_loaded_through_refreshed_backend_state", async () => {
    const order = orderApproved();
    let step = 0;
    const recorded: { type: string; payload: Record<string, unknown>; key: string }[] = [];
    const eventTypes = ["START_PREP", "GOODS_READY", "LOADED"];
    server.use(
      http.get(PREP_QUEUE_URL, () => HttpResponse.json({
        capacity: capacityVerified(),
        orders: [{
          ...order,
          status: (["APPROVED", "PREPARING", "GOODS_READY", "LOADED"] as const)[step],
          next_action: (["START_PREP", "GOODS_READY", "LOADED", null] as const)[step],
          prep_window: { ...order.prep_window, start: step > 0 ? "2026-11-12T06:00:00Z" : null },
          loading: [{ ...order.loading[0], loaded: step === 3 }],
        }],
      })),
      http.post(API_BASE_URL + "/orders/:orderId/events", async ({ request, params }) => {
        const body = (await request.json()) as { event_type: string; payload: Record<string, unknown> };
        const key = request.headers.get("Idempotency-Key") ?? "";
        expect(params.orderId).toBe("137");
        expect(key).toMatch(/^[\da-f-]{36}$/i);
        if (body.event_type !== eventTypes[step]) {
          return HttpResponse.json({ error: { code: "ILLEGAL_TRANSITION", message: "stale", correlation_id: "e3-conflict" } }, { status: 409 });
        }
        recorded.push({ type: body.event_type, payload: body.payload, key });
        step += 1;
        return HttpResponse.json({ event_id: step, order_status: (["PREPARING", "GOODS_READY", "LOADED"] as const)[step - 1] });
      }),
    );
    signInWarehouse();
    renderAt("/warehouse/prep");
    const user = userEvent.setup();
    const actions = () => within(screen.getByText(order.order_no).closest("tr") as HTMLElement);
    await screen.findByRole("table", { name: "Orders to prepare" });
    await user.click(actions().getByRole("button", { name: "Start preparation" }));
    await user.clear(screen.getByRole("spinbutton", { name: /Crew size/ }));
    await user.type(screen.getByRole("spinbutton", { name: /Crew size/ }), "3");
    await user.click(screen.getByRole("button", { name: "Confirm Start preparation" }));
    await waitFor(() => expect(actions().getByRole("button", { name: "Goods ready" })).toBeEnabled());

    await user.click(actions().getByRole("button", { name: "Goods ready" }));
    await user.click(screen.getByRole("button", { name: "Confirm Goods ready" }));
    await waitFor(() => expect(actions().getByRole("button", { name: "Mark loaded · GBG-12-03" })).toBeEnabled());

    await user.click(actions().getByRole("button", { name: "Mark loaded · GBG-12-03" }));
    await user.click(screen.getByRole("button", { name: "Confirm Mark loaded" }));
    await waitFor(() => expect(actions().getByText("LOADED")).toBeInTheDocument());
    expect(actions().queryByRole("button", { name: /Mark loaded/ })).toBeNull();
    expect(recorded.map((e) => e.type)).toEqual(eventTypes);
    expect(recorded.map((e) => e.payload)).toEqual([{ crew_size: 3 }, {}, { trip_id: 930 }]);
    expect(new Set(recorded.map((e) => e.key)).size).toBe(3);
  });

  it("test_US_WH_04_AC2_two_vehicle_loads_send_distinct_trip_ids_and_keys", async () => {
    const original = orderMultiVehicle();
    const loaded = new Set<number>();
    const calls: { trip: number; key: string }[] = [];
    server.use(
      http.get(PREP_QUEUE_URL, () => HttpResponse.json({
        capacity: capacityVerified(),
        orders: [{
          ...original,
          status: loaded.size === 2 ? "LOADED" : "GOODS_READY",
          next_action: loaded.size === 2 ? null : "LOADED",
          loading: original.loading.map((trip) => ({ ...trip, loaded: loaded.has(trip.trip_id) })),
        }],
      })),
      http.post(API_BASE_URL + "/orders/:orderId/events", async ({ request }) => {
        const body = (await request.json()) as { event_type: string; payload: { trip_id: number } };
        expect(body.event_type).toBe("LOADED");
        calls.push({ trip: body.payload.trip_id, key: request.headers.get("Idempotency-Key") ?? "" });
        loaded.add(body.payload.trip_id);
        return HttpResponse.json({ event_id: calls.length, order_status: loaded.size === 2 ? "LOADED" : "GOODS_READY" });
      }),
    );
    signInWarehouse();
    renderAt("/warehouse/prep");
    const user = userEvent.setup();
    await screen.findByRole("table", { name: "Orders to prepare" });
    await user.click(screen.getByRole("button", { name: "Mark loaded · GBG-18-04" }));
    await user.click(screen.getByRole("button", { name: "Confirm Mark loaded" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Mark loaded · GBG-18-04" })).toBeNull());
    await user.click(screen.getByRole("button", { name: "Mark loaded · GBG-18-05" }));
    await user.click(screen.getByRole("button", { name: "Confirm Mark loaded" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Mark loaded · GBG-18-05" })).toBeNull());
    expect(calls.map((call) => call.trip)).toEqual([941, 942]);
    expect(calls[0].key).not.toBe(calls[1].key);
  });

  it("test_US_WH_04_AC4_after_409_shows_conflict_and_requires_backend_reload", async () => {
    const order = orderApproved();
    let stale = false;
    let sent = 0;
    server.use(
      http.get(PREP_QUEUE_URL, () => HttpResponse.json({
        capacity: capacityVerified(),
        orders: [{ ...order, status: stale ? "PREPARING" : "APPROVED",
          next_action: stale ? "GOODS_READY" : "START_PREP",
          prep_window: { ...order.prep_window, start: stale ? "2026-11-12T06:00:00Z" : null } }],
      })),
      http.post(API_BASE_URL + "/orders/:orderId/events", () => {
        sent++;
        stale = true;
        return HttpResponse.json({ error: { code: "ILLEGAL_TRANSITION", message: "out of order", correlation_id: "c" } }, { status: 409 });
      }),
    );
    signInWarehouse();
    renderAt("/warehouse/prep");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start preparation" }));
    await user.click(screen.getByRole("button", { name: "Confirm Start preparation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Refresh the queue/);
    expect(screen.queryByText("out of order")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Reload queue" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Goods ready" })).toBeEnabled());
    expect(sent).toBe(1);
  });

  it("test_US_WH_04_AC4_retries_an_uncertain_event_with_the_same_key_and_body", async () => {
    const requests: { body: unknown; key: string | null }[] = [];
    let success = false;
    server.use(
      http.get(PREP_QUEUE_URL, () => HttpResponse.json({
        capacity: capacityVerified(),
        orders: [{ ...orderApproved(), status: success ? "PREPARING" : "APPROVED",
          next_action: success ? "GOODS_READY" : "START_PREP",
          prep_window: { ...orderApproved().prep_window, start: success ? "2026-11-12T06:00:00Z" : null } }],
      })),
      http.post(API_BASE_URL + "/orders/:orderId/events", async ({ request }) => {
        requests.push({ body: await request.json(), key: request.headers.get("Idempotency-Key") });
        if (requests.length === 1) return HttpResponse.json({ error: { code: "SERVICE_UNAVAILABLE", message: "down" } }, { status: 503 });
        success = true;
        return HttpResponse.json({ event_id: 98, order_status: "PREPARING" });
      }),
    );
    signInWarehouse();
    renderAt("/warehouse/prep");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start preparation" }));
    await user.click(screen.getByRole("button", { name: "Confirm Start preparation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/unconfirmed/);
    await user.click(screen.getByRole("button", { name: "Retry same event" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Goods ready" })).toBeEnabled());
    expect(requests).toHaveLength(2);
    expect(requests[0]).toEqual(requests[1]);
  });

  it("test_US_WH_04_AC5_fails_closed_for_a_warehouse_worker_without_location_scope", async () => {
    const seen = vi.fn();
    server.use(prepQueueSuccess(buildPrepQueueFixture("verified"), seen));
    signInAs({ ...userByEmail("wm.got@cfo.demo"), location_ids: [] });
    renderAt("/warehouse/prep");
    await screen.findByText("No warehouse is assigned to your account.");
    expect(seen).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Start preparation" })).toBeNull();
  });

});