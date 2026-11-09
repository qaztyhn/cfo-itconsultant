import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { DriverTrip } from "./driverApi";
import { enqueue, flush, pendingFor, type QueueStore, type QueuedEvent } from "./offlineQueue";

const getTrip = vi.fn();
const sendEvent = vi.fn();
vi.mock("./driverApi", async importOriginal => {
  const actual = await importOriginal<typeof import("./driverApi")>();
  return { ...actual, getDriverTrip: (...args: unknown[]) => getTrip(...args), sendDriverEvent: (...args: unknown[]) => sendEvent(...args) };
});
const trip: DriverTrip = { trip_id: 1, warehouse_id: 1, warehouse_code: "WH", vehicle_code: "V1", status: "on_road",
  depart_planned_at: "2026-11-09T08:00:00Z", depart_actual_at: "2026-11-09T08:02:00Z",
  stops: [{ trip_stop_id: 2, order_id: 3, order_no: "O3", status: "pending", eta_planned_at: "2026-11-09T09:00:00Z",
    delivery_address: "Test address", contact_name: null, contact_phone: null,
    receiving_window: { start: null, end: null }, special_requirements: null }] };
const event: QueuedEvent = { driverUserId: 8, tripId: 1, orderId: 3, eventType: "DELIVERED", occurredAt: "2026-11-09T09:00:00Z",
  idempotencyKey: "fixed-key", payload: { trip_id: 1, recipient_name: "Test recipient" } };
function memoryStore(): QueueStore {
  const rows = new Map<string, QueuedEvent>();
  return { put: async item => { rows.set(item.idempotencyKey, item); }, list: async () => [...rows.values()], remove: async key => { rows.delete(key); } };
}
beforeEach(() => { getTrip.mockReset().mockResolvedValue(trip); sendEvent.mockReset().mockResolvedValue({ event_id: 11, order_status: "DELIVERED", risk: null }); });

describe("driver offline event replay", () => {
  it("persists one key and replays only the signed-in driver's pending event", async () => {
    const store = memoryStore();
    await enqueue(event, store); await enqueue(event, store);
    await enqueue({ ...event, driverUserId: 9, idempotencyKey: "other-driver" }, store);
    expect(await pendingFor(8, store)).toHaveLength(1);
    expect(await flush(8, store)).toEqual({ sent: 1, pending: 0, conflict: null });
    expect(sendEvent).toHaveBeenCalledTimes(1);
    expect(sendEvent.mock.calls[0][0].idempotencyKey).toBe("fixed-key");
    expect(await pendingFor(9, store)).toHaveLength(1);
  });
  it("keeps the original key and payload through a network failure", async () => {
    const store = memoryStore(); await enqueue(event, store);
    sendEvent.mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", undefined, undefined, 0));
    expect(await flush(8, store)).toEqual({ sent: 0, pending: 1, conflict: null });
    expect((await pendingFor(8, store))[0]).toEqual(event);
    expect(await flush(8, store)).toEqual({ sent: 1, pending: 0, conflict: null });
  });
  it("does not replay after trip completion or lost assignment", async () => {
    const store = memoryStore(); await enqueue(event, store);
    getTrip.mockResolvedValueOnce({ ...trip, status: "completed" });
    expect((await flush(8, store)).conflict).toMatch(/Trip state changed/);
    expect(sendEvent).not.toHaveBeenCalled();
    getTrip.mockRejectedValueOnce(new ApiError("FORBIDDEN", "Denied", undefined, undefined, 403));
    expect((await flush(8, store)).conflict).toMatch(/FORBIDDEN/);
    expect(await pendingFor(8, store)).toHaveLength(1);
  });
  it("stops on 409 and never claims an unacknowledged event", async () => {
    const store = memoryStore(); await enqueue(event, store);
    sendEvent.mockRejectedValueOnce(new ApiError("ILLEGAL_TRANSITION", "Changed", undefined, undefined, 409));
    expect((await flush(8, store)).conflict).toMatch(/ILLEGAL_TRANSITION/);
    expect(await pendingFor(8, store)).toHaveLength(1);
    sendEvent.mockResolvedValueOnce({ event_id: 0 });
    expect((await flush(8, store)).conflict).toMatch(/acknowledgment/);
  });
});
