import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { DriverTrip } from "./driverApi";
import { assignedTrip } from "./driverApi";
import { eligibleForReplay, replayBatch, type PendingEvent } from "./offlineEvents";

vi.mock("./driverApi", () => ({ assignedTrip: vi.fn(), submitDriverEvent: vi.fn() }));

const event: PendingEvent = {
  key: "stable-event-key",
  userId: 71,
  tripId: 21,
  stopId: 41,
  orderId: 15,
  event: {
    event_type: "DELIVERED",
    occurred_at: "2026-11-09T10:01:00Z",
    payload: { trip_id: 21, trip_stop_id: 41, recipient_name: "Signed by recipient" },
  },
  state: "pending",
};

const trip: DriverTrip = {
  trip_id: 21,
  warehouse_id: 5,
  warehouse_code: "GBG",
  vehicle_code: "V-41",
  status: "on_road",
  depart_planned_at: "2026-11-09T08:00:00Z",
  depart_actual_at: "2026-11-09T08:05:00Z",
  stops: [{
    trip_stop_id: 41,
    order_id: 15,
    order_no: "SE-15",
    status: "pending",
    eta_planned_at: "2026-11-09T12:00:00Z",
    delivery_address: "Example, Gothenburg",
    contact_name: "Demo",
    contact_phone: null,
    receiving_window: { start: "08:00", end: "16:00" },
    special_requirements: null,
  }],
};

beforeEach(() => { vi.mocked(assignedTrip).mockReset(); });

describe("Driver assigned-trip revalidation", () => {
  it("allows only matching trip and stop identities", async () => {
    vi.mocked(assignedTrip).mockResolvedValue(trip);
    expect(await eligibleForReplay(event)).toBe(true);
    expect(await eligibleForReplay({ ...event, stopId: 99 })).toBe(false);
    expect(await eligibleForReplay({ ...event, orderId: 99 })).toBe(false);
  });

  it("rejects cancelled and not-yet-dispatched trips (duty/trip expiry)", async () => {
    vi.mocked(assignedTrip).mockResolvedValue({ ...trip, status: "cancelled" });
    expect(await eligibleForReplay(event)).toBe(false);
    vi.mocked(assignedTrip).mockResolvedValue({ ...trip, status: "loading" });
    expect(await eligibleForReplay(event)).toBe(false);
  });

  it("allows exact same-key replay after completion to recover a lost acknowledgment", async () => {
    vi.mocked(assignedTrip).mockResolvedValue({ ...trip, status: "completed", stops: [{ ...trip.stops[0], status: "delivered" }] });
    expect(await eligibleForReplay(event)).toBe(true);
  });
});

describe("Idempotent outbox replay", () => {
  function dependencies() {
    return {
      eligible: vi.fn().mockResolvedValue(true),
      send: vi.fn<(_event: PendingEvent) => Promise<{ event_id: number }>>(),
      acknowledge: vi.fn().mockResolvedValue(undefined),
      reject: vi.fn().mockResolvedValue(undefined),
    };
  }

  it("retries an uncertain network failure with exactly the same key, payload and tap timestamp", async () => {
    const deps = dependencies();
    deps.send.mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", "corr", undefined, 0));
    deps.send.mockResolvedValueOnce({ event_id: 211 });
    expect(await replayBatch([event], deps)).toEqual({ sent: 0, conflict: 0 });
    expect(deps.acknowledge).not.toHaveBeenCalled();
    expect(await replayBatch([event], deps)).toEqual({ sent: 1, conflict: 0 });
    expect(deps.send).toHaveBeenNthCalledWith(1, event);
    expect(deps.send).toHaveBeenNthCalledWith(2, event);
    expect(deps.acknowledge).toHaveBeenCalledTimes(1);
    expect(deps.acknowledge).toHaveBeenCalledWith(event.key);
  });

  it("requires a verified event id, not merely HTTP success", async () => {
    const deps = dependencies();
    deps.send.mockResolvedValue({ event_id: 0 });
    expect(await replayBatch([event], deps)).toEqual({ sent: 0, conflict: 0 });
    expect(deps.acknowledge).not.toHaveBeenCalled();
  });

  it("blocks on server RBAC and stale transition conflicts without sending later events", async () => {
    for (const status of [403, 404, 409, 422]) {
      const deps = dependencies();
      deps.send.mockRejectedValue(new ApiError("NOT_ON_TRIP", "Denied", "ref", undefined, status));
      expect(await replayBatch([event, { ...event, key: "next-event" }], deps)).toEqual({ sent: 0, conflict: 1 });
      expect(deps.reject).toHaveBeenCalledWith(event, "NOT_ON_TRIP");
      expect(deps.send).toHaveBeenCalledTimes(1);
      expect(deps.acknowledge).not.toHaveBeenCalled();
    }
  });

  it("blocks on revoked assignment and keeps the event pending for review", async () => {
    const deps = dependencies();
    deps.eligible.mockResolvedValue(false);
    expect(await replayBatch([event], deps)).toEqual({ sent: 0, conflict: 1 });
    expect(deps.reject).toHaveBeenCalledWith(event, "NOT_ON_TRIP");
    expect(deps.send).not.toHaveBeenCalled();
  });

  it("never advances through a previously conflicted event", async () => {
    const deps = dependencies();
    expect(await replayBatch([{ ...event, state: "conflict" }, { ...event, key: "next" }], deps))
      .toEqual({ sent: 0, conflict: 1 });
    expect(deps.send).not.toHaveBeenCalled();
  });
});
