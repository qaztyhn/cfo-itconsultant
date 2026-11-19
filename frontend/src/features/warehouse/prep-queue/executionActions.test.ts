import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiPost, newIdempotencyKey } from "../../../api/client";
import { orderApproved, orderMultiVehicle, orderRunning } from "./fixtures";
import {
  canPerform, eventDraft, localOccurredAt, prepareEvent, safeActionError, submitPrepEvent,
  type EventPayload, type PrepEventType,
} from "./executionActions";

vi.mock("../../../api/client", async (original) => ({
  ...(await original<typeof import("../../../api/client")>()),
  apiPost: vi.fn(),
  newIdempotencyKey: vi.fn()
    .mockReturnValueOnce("11111111-2222-4333-8444-555555555555")
    .mockReturnValueOnce("22222222-2222-4333-8444-555555555555"),
}));

const at = "2025-11-09T07:30:00Z";
beforeEach(() => {
  vi.mocked(apiPost).mockReset();
  vi.mocked(newIdempotencyKey).mockReset();
  vi.mocked(newIdempotencyKey).mockReturnValue("11111111-2222-4333-8444-555555555555");
});

describe("Round 3 authoritative action eligibility", () => {
  it("test_US_WH_04_AC1_requires_backend next_action as well as legal status", () => {
    expect(canPerform(orderApproved(), "START_PREP")).toBe(true);
    expect(canPerform(orderRunning(), "GOODS_READY")).toBe(true);
    expect(canPerform({ ...orderApproved(), next_action: null }, "START_PREP")).toBe(false);
    expect(canPerform({ ...orderApproved(), next_action: "GOODS_READY" }, "START_PREP")).toBe(false);
    expect(canPerform({ ...orderRunning(), next_action: null }, "GOODS_READY")).toBe(false);
    expect(canPerform({ ...orderApproved(), status: "PREPARING" }, "START_PREP")).toBe(false);
  });

  it("test_US_WH_04_AC2_requires one un-loaded matching trip per vehicle", () => {
    const order = orderMultiVehicle();
    expect(canPerform(order, "LOADED", 941)).toBe(false);
    expect(canPerform(order, "LOADED", 942)).toBe(true);
    expect(canPerform(order, "LOADED", 9999)).toBe(false);
    expect(canPerform({ ...order, next_action: null }, "LOADED", 942)).toBe(false);
    expect(canPerform(orderApproved(), "LOADED", 930)).toBe(false);
  });

  it("test_US_WH_05_AC1_allows shortage and breakage only during warehouse execution", () => {
    expect(canPerform(orderRunning(), "SHORTAGE")).toBe(true);
    expect(canPerform(orderRunning(), "BREAKAGE")).toBe(true);
    expect(canPerform({ ...orderRunning(), status: "DELIVERED" }, "SHORTAGE")).toBe(false);
  });
});

describe("POST /orders/{id}/events Round 3 payload and key", () => {
  const cases: [PrepEventType, EventPayload][] = [
    ["START_PREP", { crew_size: 3 }],
    ["GOODS_READY", {}],
    ["LOADED", { trip_id: 942 }],
    ["SHORTAGE", { sku: "SE-CEM", qty_missing: 5 }],
    ["BREAKAGE", { sku: "SE-CEM", qty: 2 }],
  ];

  it.each(cases)("test_US_WH_04_AC3_sends %s exactly as documented", async (eventType, payload) => {
    vi.mocked(apiPost).mockResolvedValue({ event_id: 28, order_status: "GOODS_READY" });
    const event = prepareEvent(eventDraft(137, eventType, at, payload));
    await expect(submitPrepEvent(event)).resolves.toMatchObject({ event_id: 28 });
    expect(apiPost).toHaveBeenCalledWith("/orders/137/events", {
      event_type: eventType,
      occurred_at: "2025-11-09T07:30:00.000Z",
      payload,
    }, event.key);
  });

  it("test_US_WH_04_AC4_replays uncertain retries with unchanged key and body", async () => {
    const original = prepareEvent(eventDraft(137, "START_PREP", at, { crew_size: 4 }));
    expect(prepareEvent(eventDraft(137, "START_PREP", at, { crew_size: 4 }), original)).toBe(original);
    vi.mocked(apiPost).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "unavailable", undefined, undefined, 0));
    vi.mocked(apiPost).mockResolvedValueOnce({ event_id: 29, order_status: "PREPARING" });
    await expect(submitPrepEvent(original)).rejects.toBeInstanceOf(ApiError);
    await expect(submitPrepEvent(original)).resolves.toMatchObject({ event_id: 29 });
    expect(vi.mocked(apiPost).mock.calls[0]).toEqual(vi.mocked(apiPost).mock.calls[1]);
    expect(newIdempotencyKey).toHaveBeenCalledTimes(1);
  });

  it("allocates independent keys to separate vehicle loading events", async () => {
    vi.mocked(newIdempotencyKey).mockReturnValueOnce("11111111-2222-4333-8444-555555555555")
      .mockReturnValueOnce("22222222-2222-4333-8444-555555555555");
    const first = prepareEvent(eventDraft(158, "LOADED", at, { trip_id: 941 }));
    const second = prepareEvent(eventDraft(158, "LOADED", at, { trip_id: 942 }));
    expect(first.key).not.toEqual(second.key);
    expect(first.payload).toEqual({ trip_id: 941 });
    expect(second.payload).toEqual({ trip_id: 942 });
  });

  it("fails closed when server does not return an event_id", async () => {
    vi.mocked(apiPost).mockResolvedValueOnce({});
    await expect(submitPrepEvent(prepareEvent(eventDraft(137, "GOODS_READY", at, {}))))
      .rejects.toThrow(/verified event acknowledgment/);
  });

  it("rejects invalid crew, trip, SKU, quantities and ambiguous time", () => {
    expect(() => eventDraft(137, "START_PREP", at, { crew_size: 0 })).toThrow(/positive/);
    expect(() => eventDraft(137, "LOADED", at, { trip_id: -1 })).toThrow(/positive/);
    expect(() => eventDraft(137, "SHORTAGE", at, { sku: "", qty_missing: 3 })).toThrow(/SKU/);
    expect(() => eventDraft(137, "BREAKAGE", at, { sku: "A", qty: 1.5 })).toThrow(/positive/);
    expect(() => eventDraft(137, "START_PREP", "2025-11-09T07:30:00", { crew_size: 1 })).toThrow(/offset/);
    expect(() => localOccurredAt("")).toThrow(/Select when/);
  });

  it("test_US_WH_04_AC4 explains a plan verification conflict", () => {
    const error = new ApiError("PLAN_NOT_APPROVABLE", "sensitive server text", "test-cid", undefined, 409);
    expect(safeActionError(error)).toMatch(/could not verify the approved plan or calculate ETA/);
    expect(safeActionError(error)).not.toContain("sensitive");
  });

  it("explains 409 without exposing upstream error text", () => {
    const error = new ApiError("ILLEGAL_TRANSITION", "sensitive server text", "test-cid", undefined, 409);
    expect(safeActionError(error)).toMatch(/Refresh the queue/);
    expect(safeActionError(error)).not.toContain("sensitive");
  });
});
