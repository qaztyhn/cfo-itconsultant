import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiPost, newIdempotencyKey } from "../../../api/client";
import { orderApproved, orderMultiVehicle, orderPaused, orderRunning } from "./fixtures";
import {
  ACTION_NAMES, canPerform, eventDraft, localOccurredAt, prepareEvent, submitPrepEvent,
  type PrepEventType, type EventPayload,
} from "./executionActions";

vi.mock("../../../api/client", async (original) => ({
  ...(await original<typeof import("../../../api/client")>()),
  apiPost: vi.fn(),
  newIdempotencyKey: vi.fn(() => "11111111-2222-4333-8444-555555555555"),
}));

const at = "2025-11-09T07:30:00Z";
beforeEach(() => {
  vi.mocked(apiPost).mockReset();
  vi.mocked(newIdempotencyKey).mockClear();
});

describe("M6 approved milestone eligibility", () => {
  it.each([
    ["START_PREP", orderApproved(), true],
    ["PREP_PAUSED", orderRunning(), true],
    ["PREP_RESUMED", orderPaused(), true],
    ["GOODS_READY", orderRunning(), true],
    ["START_PREP", orderRunning(), false],
    ["PREP_PAUSED", orderPaused(), false],
    ["PREP_RESUMED", orderRunning(), false],
    ["GOODS_READY", orderPaused(), false],
  ] as const)("%s accepts only its legal state", (type, order, allowed) => {
    expect(canPerform(order, type)).toBe(allowed);
  });

  it("marks each vehicle individually and never enables the loaded vehicle", () => {
    const order = orderMultiVehicle();
    expect(canPerform(order, "LOADED", 941)).toBe(false);
    expect(canPerform(order, "LOADED", 942)).toBe(true);
    expect(canPerform(order, "LOADED", 9999)).toBe(false);
    expect(canPerform(orderApproved(), "LOADED", 930)).toBe(false);
  });

  it("does not enable exceptions for terminal orders", () => {
    const order = { ...orderApproved(), status: "DELIVERED" as const };
    for (const type of ["SHORTAGE", "BREAKAGE", "VEHICLE_ISSUE", "SHIFT_CHANGE"] as PrepEventType[]) {
      expect(canPerform(order, type)).toBe(false);
    }
  });
});

describe("Exact execution API contract", () => {
  const cases: [PrepEventType, EventPayload][] = [
    ["START_PREP", { crew_size: 3 }],
    ["PREP_PAUSED", { note: "Loading delay" }],
    ["PREP_RESUMED", { crew_size: 2 }],
    ["GOODS_READY", {}],
    ["LOADED", { trip_id: 942 }],
    ["SHORTAGE", { sku: "SE-CEM", qty_missing: 5 }],
    ["BREAKAGE", { sku: "SE-CEM", qty: 2 }],
    ["VEHICLE_ISSUE", { vehicle_id: 17 }],
    ["SHIFT_CHANGE", { date: "2025-11-09", staff_present: 0 }],
  ];
  it.each(cases)("sends approved %s payload and idempotency header", async (type, payload) => {
    vi.mocked(apiPost).mockResolvedValue({ event_id: 28, order_status: "PREPARING" });
    const event = prepareEvent(eventDraft(137, type, at, payload));
    expect(event.event_type).toBe(type);
    expect(ACTION_NAMES[type]).toBeTruthy();
    expect(await submitPrepEvent(event)).toMatchObject({ event_id: 28 });
    expect(apiPost).toHaveBeenCalledWith("/orders/137/events", {
      event_type: type,
      occurred_at: "2025-11-09T07:30:00.000Z",
      payload,
    }, "11111111-2222-4333-8444-555555555555");
  });

  it("keeps the same key, timestamp and payload for identical uncertain retries", () => {
    const first = prepareEvent(eventDraft(137, "START_PREP", at, { crew_size: 4 }));
    const replay = prepareEvent(eventDraft(137, "START_PREP", at, { crew_size: 4 }), first);
    expect(replay).toBe(first);
    expect(newIdempotencyKey).toHaveBeenCalledTimes(1);
    const changed = prepareEvent(eventDraft(137, "START_PREP", at, { crew_size: 5 }), first);
    expect(changed).not.toBe(first);
    expect(newIdempotencyKey).toHaveBeenCalledTimes(2);
  });

  it("does not claim success when the API returns an unverified event id", async () => {
    const event = prepareEvent(eventDraft(137, "GOODS_READY", at, {}));
    vi.mocked(apiPost).mockResolvedValueOnce({});
    await expect(submitPrepEvent(event)).rejects.toThrow(/verified event acknowledgment/);
    vi.mocked(apiPost).mockRejectedValueOnce(new Error("network"));
    await expect(submitPrepEvent(event)).rejects.toThrow("network");
    expect(vi.mocked(apiPost).mock.calls[0][2]).toBe(vi.mocked(apiPost).mock.calls[1][2]);
  });

  it("rejects missing or ambiguous timestamps, future events, invalid crew and invalid reports", () => {
    expect(() => eventDraft(137, "START_PREP", "2025-11-09T07:30:00", { crew_size: 2 })).toThrow(/offset/);
    expect(() => eventDraft(137, "START_PREP", "2099-11-09T07:30:00Z", { crew_size: 2 })).toThrow(/future/);
    expect(() => eventDraft(137, "START_PREP", at, { crew_size: 0 })).toThrow(/positive/);
    expect(() => eventDraft(137, "LOADED", at, { trip_id: -4 })).toThrow(/positive/);
    expect(() => eventDraft(137, "SHORTAGE", at, { sku: "", qty_missing: 3 })).toThrow(/SKU/);
    expect(() => eventDraft(137, "BREAKAGE", at, { sku: "A", qty: 1.5 })).toThrow(/positive/);
    expect(() => eventDraft(137, "VEHICLE_ISSUE", at, { vehicle_id: 0 })).toThrow(/positive/);
    expect(() => eventDraft(137, "SHIFT_CHANGE", at, { date: "2025-11-09", staff_present: -1 })).toThrow(/nonnegative/);
  });

  it("preserves the explicit device-local time and rejects missing local time", () => {
    expect(new Date(localOccurredAt("2025-11-09T07:30")).getTime()).toBe(new Date(2025, 10, 9, 7, 30).getTime());
    expect(() => localOccurredAt("")).toThrow(/Select when/);
  });
});
