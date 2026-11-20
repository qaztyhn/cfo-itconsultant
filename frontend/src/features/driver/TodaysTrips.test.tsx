import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { currentPath, renderAt, signInAs, userByEmail } from "../../test/utils";
import { assignedTrips, stopScopedPodEnabled, type DriverTrip } from "./driverApi";
import { enqueueEvent, pendingForUser, replayEvents } from "./offlineEvents";

vi.mock("./driverApi", () => ({ assignedTrips: vi.fn(), assignedTrip: vi.fn(), submitDriverEvent: vi.fn(), stopScopedPodEnabled: vi.fn() }));
vi.mock("./offlineEvents", () => ({
  pendingForUser: vi.fn(), enqueueEvent: vi.fn(), replayEvents: vi.fn(),
  discardEvent: vi.fn(),
}));

const loaded: DriverTrip = {
  trip_id: 12,
  warehouse_id: 3,
  warehouse_code: "GBG",
  vehicle_code: "V-12",
  status: "loading",
  depart_planned_at: "2026-11-09T08:00:00Z",
  depart_actual_at: null,
  stops: [{
    trip_stop_id: 30,
    order_id: 44,
    order_no: "SE-44",
    status: "pending",
    eta_planned_at: "2026-11-09T12:00:00Z",
    delivery_address: "Gothenburg demo site",
    contact_name: "Demo contact",
    contact_phone: null,
    receiving_window: { start: "09:00", end: "13:00" },
    special_requirements: null,
  }],
};

beforeEach(() => {
  vi.mocked(assignedTrips).mockReset().mockResolvedValue([loaded]);
  vi.mocked(stopScopedPodEnabled).mockReset().mockReturnValue(false);
  vi.mocked(pendingForUser).mockReset().mockResolvedValue([]);
  vi.mocked(enqueueEvent).mockReset().mockResolvedValue(undefined);
  vi.mocked(replayEvents).mockReset().mockResolvedValue({ sent: 0, conflict: 0, waiting: 0 });
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
});

describe("Driver PWA assigned-trip and privacy boundaries", () => {
  it("only loads the authenticated driver's assigned trips", async () => {
    signInAs(userByEmail("driver1@cfo.demo"));
    renderAt("/driver");
    expect(await screen.findByText("SE-44 · Gothenburg demo site")).toBeInTheDocument();
    expect(screen.getByText(/Only trips assigned to your driver account/)).toBeInTheDocument();
    expect(assignedTrips).toHaveBeenCalled();
    expect(screen.queryByText("SE-999")).toBeNull();
  });

  it("does not fetch trips for an unauthorized role", async () => {
    signInAs(userByEmail("sales@cfo.demo"));
    renderAt("/driver");
    await waitFor(() => expect(currentPath()).not.toBe("/driver"));
    expect(assignedTrips).not.toHaveBeenCalled();
  });

  it("keeps stable idempotency key, server payload and exact occurred_at at offline tap", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    signInAs(userByEmail("driver1@cfo.demo"));
    renderAt("/driver");
    await screen.findByText("SE-44 · Gothenburg demo site");
    await userEvent.click(screen.getByRole("button", { name: "Review and dispatch" }));
    await userEvent.click(screen.getByRole("button", { name: "Mark dispatched" }));
    await waitFor(() => expect(enqueueEvent).toHaveBeenCalledTimes(1));
    const item = vi.mocked(enqueueEvent).mock.calls[0][0];
    expect(item.userId).toBe(4);
    expect(item.tripId).toBe(12);
    expect(item.stopId).toBe(30);
    expect(item.event.event_type).toBe("DISPATCHED");
    expect(item.event.payload).toEqual({ trip_id: 12 });
    expect(item.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(new Date(item.event.occurred_at).getTime()).not.toBeNaN();
    expect(replayEvents).not.toHaveBeenCalled();
    expect(screen.getByText(/Not yet confirmed by CFO/)).toBeInTheDocument();
  });

  it("requires recipient for a delivered POD, keeps GPS disabled even when browser is permitted", async () => {
    vi.mocked(assignedTrips).mockResolvedValue([{ ...loaded, status: "on_road" }]);
    const geolocation = { getCurrentPosition: vi.fn(), watchPosition: vi.fn() };
    vi.stubGlobal("geolocation", geolocation);
    signInAs(userByEmail("driver1@cfo.demo"));
    renderAt("/driver");
    await screen.findByText("SE-44 · Gothenburg demo site");
    await userEvent.click(screen.getByRole("button", { name: "Record delivery outcome" }));
    await userEvent.click(screen.getByRole("button", { name: /Select stop 30/ }));
    const confirm = screen.getByRole("button", { name: "Confirm delivered" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Received by" }), "Demo recipient");
    await userEvent.click(confirm);
    await waitFor(() => expect(enqueueEvent).toHaveBeenCalledTimes(1));
    expect(vi.mocked(enqueueEvent).mock.calls[0][0].event).toEqual({
      event_type: "DELIVERED",
      occurred_at: expect.any(String),
      payload: { trip_id: 12, recipient_name: "Demo recipient" },
    });
    expect(geolocation.getCurrentPosition).not.toHaveBeenCalled();
    expect(geolocation.watchPosition).not.toHaveBeenCalled();
    expect(screen.queryByText(/historical GPS investigations/i)).toBeNull();
    vi.unstubAllGlobals();
  });

  it("requires an enumerated failed-POD reason", async () => {
    vi.mocked(assignedTrips).mockResolvedValue([{ ...loaded, status: "on_road" }]);
    signInAs(userByEmail("driver1@cfo.demo"));
    renderAt("/driver");
    await screen.findByText("SE-44 · Gothenburg demo site");
    await userEvent.click(screen.getByRole("button", { name: "Record delivery outcome" }));
    await userEvent.click(screen.getByRole("button", { name: /Select stop 30/ }));
    await userEvent.click(screen.getByRole("radio", { name: "Failed" }));
    expect(screen.getByRole("button", { name: "Confirm failed" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Failure reason" }), "customer_absent");
    await userEvent.click(screen.getByRole("button", { name: "Confirm failed" }));
    await waitFor(() => expect(enqueueEvent).toHaveBeenCalledTimes(1));
    expect(vi.mocked(enqueueEvent).mock.calls[0][0].event.payload)
      .toEqual({ trip_id: 12, failure_reason: "customer_absent" });
  });

  it("disables terminal-trip actions and does not start GPS at trip expiry", async () => {
    vi.mocked(assignedTrips).mockResolvedValue([{ ...loaded, status: "completed", stops: [{ ...loaded.stops[0], status: "delivered" }] }]);
    signInAs(userByEmail("driver1@cfo.demo"));
    renderAt("/driver");
    await screen.findByText("SE-44 · Gothenburg demo site");
    await userEvent.click(screen.getByRole("button", { name: "View trip" }));
    expect(screen.getByText(/Trip ended. No further updates or location sharing/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark dispatched" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Confirm delivered" })).toBeNull();
  });

  it("records the selected stop ID on a multi-stop POD and never auto-confirms", async () => {
    vi.mocked(stopScopedPodEnabled).mockReturnValue(true);
    vi.mocked(assignedTrips).mockResolvedValue([{
      ...loaded, status: "on_road", stops: [
        loaded.stops[0],
        { ...loaded.stops[0], trip_stop_id: 31, order_no: "SE-44", status: "pending" },
      ],
    }]);
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    signInAs(userByEmail("driver1@cfo.demo"));
    renderAt("/driver");
    await screen.findAllByText("SE-44 · Gothenburg demo site");
    await userEvent.click(screen.getByRole("button", { name: "Record delivery outcome" }));
    expect(screen.queryByRole("button", { name: "Confirm delivered" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Select stop 31/ }));
    await userEvent.type(screen.getByRole("textbox", { name: "Received by" }), "Sample recipient");
    await userEvent.click(screen.getByRole("button", { name: "Confirm delivered" }));
    await waitFor(() => expect(enqueueEvent).toHaveBeenCalledTimes(1));
    const item = vi.mocked(enqueueEvent).mock.calls[0][0];
    expect(item.stopId).toBe(31);
    expect(item.event.payload).toEqual({ trip_id: 12, trip_stop_id: 31, recipient_name: "Sample recipient" });
    expect(replayEvents).not.toHaveBeenCalled();
    expect(screen.getByText(/Not yet confirmed by CFO/)).toBeInTheDocument();
  });

  it("keeps multi-stop POD disabled before the stop-scoped backend is deployed", async () => {
    vi.mocked(assignedTrips).mockResolvedValue([{
      ...loaded, status: "on_road", stops: [loaded.stops[0], { ...loaded.stops[0], trip_stop_id: 31 }],
    }]);
    signInAs(userByEmail("driver1@cfo.demo"));
    renderAt("/driver");
    await screen.findAllByText("SE-44 · Gothenburg demo site");
    await userEvent.click(screen.getByRole("button", { name: "Record delivery outcome" }));
    expect(screen.getByText(/Multi-stop POD requires the verified stop-scoped execution API/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm delivered" })).toBeNull();
    expect(enqueueEvent).not.toHaveBeenCalled();
  });

  it("blocks ambiguous cross-order trips without guessing which order to dispatch", async () => {
    vi.mocked(assignedTrips).mockResolvedValue([{
      ...loaded, status: "loading", stops: [
        loaded.stops[0],
        { ...loaded.stops[0], order_id: 45, trip_stop_id: 31 },
      ],
    }]);
    signInAs(userByEmail("driver1@cfo.demo"));
    renderAt("/driver");
    await screen.findAllByText("SE-44 · Gothenburg demo site");
    await userEvent.click(screen.getByRole("button", { name: "Review and dispatch" }));
    expect(screen.getByText(/references multiple orders/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark dispatched" })).toBeNull();
    expect(enqueueEvent).not.toHaveBeenCalled();
  });

  it("allows explicit dispatch of the sole order on a multi-stop trip", async () => {
    vi.mocked(assignedTrips).mockResolvedValue([{
      ...loaded, stops: [loaded.stops[0], { ...loaded.stops[0], trip_stop_id: 31 }],
    }]);
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    signInAs(userByEmail("driver1@cfo.demo"));
    renderAt("/driver");
    await screen.findAllByText("SE-44 · Gothenburg demo site");
    await userEvent.click(screen.getByRole("button", { name: "Review and dispatch" }));
    await userEvent.click(screen.getByRole("button", { name: "Mark dispatched" }));
    await waitFor(() => expect(enqueueEvent).toHaveBeenCalledTimes(1));
    expect(vi.mocked(enqueueEvent).mock.calls[0][0].event.payload).toEqual({ trip_id: 12 });
  });
});
