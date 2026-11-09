import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../app/store";
import { userByEmail } from "../../test/utils";
import { TodaysTrips } from "./TodaysTrips";
import type { DriverTrip } from "./driverApi";
import { ApiError } from "../../api/client";

const listTrips = vi.fn(); const getTrip = vi.fn(); const sendEvent = vi.fn();
const queue = vi.fn(); const pending = vi.fn(); const replay = vi.fn();
vi.mock("./driverApi", async importOriginal => {
  const actual = await importOriginal<typeof import("./driverApi")>();
  return { ...actual, listDriverTrips: (...args: unknown[]) => listTrips(...args), getDriverTrip: (...args: unknown[]) => getTrip(...args),
    sendDriverEvent: (...args: unknown[]) => sendEvent(...args) };
});
vi.mock("./offlineQueue", () => ({ enqueue: (...args: unknown[]) => queue(...args), pendingFor: (...args: unknown[]) => pending(...args), flush: (...args: unknown[]) => replay(...args) }));

const trip: DriverTrip = { trip_id: 930, warehouse_id: 3, warehouse_code: "MLM", vehicle_code: "V-12", status: "loading",
  depart_planned_at: "2026-11-13T08:00:00Z", depart_actual_at: null,
  stops: [{ trip_stop_id: 931, order_id: 129, order_no: "ORDER-129", status: "pending", eta_planned_at: "2026-11-13T09:00:00Z",
    delivery_address: "Test Street 4", contact_name: null, contact_phone: null,
    receiving_window: { start: "09:00", end: "11:00" }, special_requirements: "Report to site office" }] };
function auth(role: "driver" | "sales") {
  const user = userByEmail(role === "driver" ? "driver1@cfo.demo" : "sales@cfo.demo");
  useAuthStore.getState().setAuth({ access_token: "test", token_type: "bearer", expires_in: 3600, user }, "test@cfo.demo");
}
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><TodaysTrips /></QueryClientProvider>);
}
beforeEach(() => {
  listTrips.mockReset().mockResolvedValue([trip]); getTrip.mockReset().mockResolvedValue(trip);
  sendEvent.mockReset().mockResolvedValue({ event_id: 12, order_status: "DISPATCHED", risk: null });
  queue.mockReset().mockResolvedValue(undefined); pending.mockReset().mockResolvedValue([]);
  replay.mockReset().mockResolvedValue({ sent: 0, pending: 0, conflict: null });
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
});
afterEach(() => { useAuthStore.getState().clearAuth(); vi.restoreAllMocks(); });

describe("US-EXE-03 driver mobile workflow", () => {
  it("blocks a non-driver before any trip request", () => {
    auth("sales"); mount();
    expect(screen.getByText(/Permission denied/)).toBeInTheDocument();
    expect(listTrips).not.toHaveBeenCalled();
  });
  it("shows assigned trips, stop address and receiving details without GPS history", async () => {
    auth("driver"); mount();
    expect(await screen.findByText("ORDER-129")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View trip details" }));
    expect(await screen.findByText("Test Street 4")).toBeInTheDocument();
    expect(screen.getByText(/Report to site office/)).toBeInTheDocument();
    expect(screen.getByText(/POD for this stop is created by the server/)).toBeInTheDocument();
    expect(screen.queryByText(/GPS history|investigation controls/i)).not.toBeInTheDocument();
  });
  it("keeps two vehicle trips for the same order separate", async () => {
    listTrips.mockResolvedValue([trip, { ...trip, trip_id: 940, vehicle_code: "V-13", stops: [{ ...trip.stops[0], trip_stop_id: 941 }] }]);
    auth("driver"); mount();
    expect(await screen.findAllByText("ORDER-129")).toHaveLength(2);
    expect(screen.getByText("V-12")).toBeInTheDocument();
    expect(screen.getByText("V-13")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "View trip details" })).toHaveLength(2);
  });
  it("shows a scoped trip-read denial without exposing details", async () => {
    getTrip.mockRejectedValue(new ApiError("FORBIDDEN", "Denied", undefined, undefined, 403));
    auth("driver"); mount(); await screen.findByText("ORDER-129");
    fireEvent.click(screen.getByRole("button", { name: "View trip details" }));
    expect(await screen.findByText(/Trip unavailable or not assigned/)).toBeInTheDocument();
    expect(screen.queryByText("Test Street 4")).not.toBeInTheDocument();
  });
  it("requires server acknowledgment before reporting dispatch", async () => {
    auth("driver"); mount();
    await screen.findByText("ORDER-129"); fireEvent.click(screen.getByRole("button", { name: "View trip details" }));
    fireEvent.click(await screen.findByRole("button", { name: "Mark dispatched" }));
    await waitFor(() => expect(sendEvent).toHaveBeenCalledTimes(1));
    expect(sendEvent.mock.calls[0][0]).toMatchObject({ orderId: 129, eventType: "DISPATCHED", payload: { trip_id: 930 } });
    expect(await screen.findByText(/Server confirmed dispatched event #12/)).toBeInTheDocument();
  });
  it("requires a failed reason and a delivered recipient", async () => {
    const onRoad = { ...trip, status: "on_road" };
    listTrips.mockResolvedValue([onRoad]); getTrip.mockResolvedValue(onRoad);
    auth("driver"); mount(); await screen.findByText("ORDER-129");
    fireEvent.click(screen.getByRole("button", { name: "View trip details" }));
    expect(await screen.findByRole("button", { name: "Confirm delivered" })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Received by" }), { target: { value: "Site agent" } });
    expect(screen.getByRole("button", { name: "Confirm delivered" })).toBeEnabled();
    fireEvent.click(screen.getByRole("radio", { name: "Failed" }));
    expect(screen.getByRole("button", { name: "Confirm failed" })).toBeDisabled();
    fireEvent.change(screen.getByRole("combobox", { name: "Failure reason" }), { target: { value: "customer_absent" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm failed" }));
    await waitFor(() => expect(sendEvent).toHaveBeenCalledTimes(1));
    expect(sendEvent.mock.calls[0][0].payload.failure_reason).toBe("customer_absent");
  });
  it("disables ambiguous multi-stop outcomes without a trip_stop_id contract", async () => {
    const two = { ...trip, status: "on_road", stops: [trip.stops[0], { ...trip.stops[0], trip_stop_id: 932, order_id: 130, order_no: "ORDER-130" }] };
    listTrips.mockResolvedValue([two]); getTrip.mockResolvedValue(two);
    auth("driver"); mount(); await screen.findByText(/ORDER-129/);
    fireEvent.click(screen.getByRole("button", { name: "View trip details" }));
    expect(await screen.findByText(/current event contract cannot identify a stop/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Confirm delivered|Confirm failed/ })).not.toBeInTheDocument();
  });
  it("reports a saved offline event only after persistence resolves", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    auth("driver"); mount(); await screen.findByText("ORDER-129");
    fireEvent.click(screen.getByRole("button", { name: "View trip details" }));
    fireEvent.click(await screen.findByRole("button", { name: "Mark dispatched" }));
    await waitFor(() => expect(queue).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Saved on this device; not confirmed/)).toBeInTheDocument();
    expect(sendEvent).not.toHaveBeenCalled();
  });
  it("shows an error rather than fake offline persistence when storage fails", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    queue.mockRejectedValue(new Error("storage unavailable"));
    auth("driver"); mount(); await screen.findByText("ORDER-129");
    fireEvent.click(screen.getByRole("button", { name: "View trip details" }));
    fireEvent.click(await screen.findByRole("button", { name: "Mark dispatched" }));
    expect(await screen.findByText(/update not confirmed/)).toBeInTheDocument();
    expect(screen.queryByText(/Saved on this device/)).not.toBeInTheDocument();
  });
  it("retains the idempotency key across a network retry and does not claim success early", async () => {
    sendEvent.mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "Offline", undefined, undefined, 0));
    auth("driver"); mount(); await screen.findByText("ORDER-129");
    fireEvent.click(screen.getByRole("button", { name: "View trip details" }));
    const button = await screen.findByRole("button", { name: "Mark dispatched" });
    fireEvent.click(button);
    expect(await screen.findByText(/update not confirmed/)).toBeInTheDocument();
    expect(screen.queryByText(/Server confirmed/)).not.toBeInTheDocument();
    fireEvent.click(button);
    await waitFor(() => expect(sendEvent).toHaveBeenCalledTimes(2));
    expect(sendEvent.mock.calls[1][0].idempotencyKey).toBe(sendEvent.mock.calls[0][0].idempotencyKey);
  });
  it("does not bypass a server conflict after reconnect", async () => {
    replay.mockResolvedValue({ sent: 0, pending: 1, conflict: "ILLEGAL_TRANSITION: review this update with dispatch." });
    pending.mockResolvedValue([{ idempotencyKey: "stored" }]);
    auth("driver"); mount(); await screen.findByText("ORDER-129");
    fireEvent(window, new Event("online"));
    expect(await screen.findByText(/ILLEGAL_TRANSITION/)).toBeInTheDocument();
    expect(sendEvent).not.toHaveBeenCalled();
  });
  it("keeps GPS collection off without individual evidence or duty proof", async () => {
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: { getCurrentPosition } });
    auth("driver"); mount(); await screen.findByText("ORDER-129");
    expect(screen.getByText(/Individual notice, acknowledgment, approved duty/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Location permission unavailable" })).toBeDisabled();
    expect(getCurrentPosition).not.toHaveBeenCalled();
    expect(screen.getByText(/No offline updates pending/)).toBeInTheDocument();
  });
});
