import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { fetchPrepQueue, parsePrepQueueResponse, prepQueuePath } from "./api";
import { FIXTURE_DATE, FIXTURE_WAREHOUSE_ID, buildPrepQueueFixture } from "./fixtures";
import { PREP_QUEUE_URL, prepQueueFailure, prepQueueSuccess } from "./mswHandlers";
import type { Capacity } from "./types";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("fetchPrepQueue", () => {
  it("builds the warehouse path", () => {
    expect(prepQueuePath(7)).toBe("/warehouses/7/prep-queue");
  });

  it("requests the queue of the warehouse for the date and returns the payload", async () => {
    const seen = vi.fn();
    server.use(prepQueueSuccess(undefined, seen));

    const result = await fetchPrepQueue({ warehouse_id: FIXTURE_WAREHOUSE_ID, date: FIXTURE_DATE });

    expect(seen).toHaveBeenCalledWith({ warehouse_id: FIXTURE_WAREHOUSE_ID, date: FIXTURE_DATE });
    expect(result.orders).toHaveLength(5);
    expect(result.capacity.shifts).toHaveLength(2);
  });

  it("turns a malformed payload into INVALID_RESPONSE", async () => {
    server.use(http.get(PREP_QUEUE_URL, () => HttpResponse.json({ orders: [] })));

    await expect(fetchPrepQueue({ warehouse_id: 1, date: FIXTURE_DATE })).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("surfaces 403 with its correlation id", async () => {
    server.use(prepQueueFailure(403, "FORBIDDEN", "Not allowed", "corr-403"));

    await expect(fetchPrepQueue({ warehouse_id: 1, date: FIXTURE_DATE })).rejects.toMatchObject({ code: "FORBIDDEN", status: 403, correlationId: "corr-403" });
  });

  it("surfaces 404 for a warehouse outside the user's scope", async () => {
    server.use(prepQueueFailure(404, "NOT_FOUND", "Warehouse not found", "corr-404"));

    await expect(fetchPrepQueue({ warehouse_id: 99, date: FIXTURE_DATE })).rejects.toMatchObject({ code: "NOT_FOUND", status: 404 });
  });
});

function errorOf(run: () => unknown): unknown {
  try {
    run();
  } catch (error) {
    return error;
  }
  return undefined;
}

type Mutable = Record<string, unknown>;

describe("parsePrepQueueResponse", () => {
  it("accepts every fixture scenario", () => {
    for (const scenario of ["verified", "unverified", "noSchedule", "empty"] as const) {
      expect(() => parsePrepQueueResponse(buildPrepQueueFixture(scenario))).not.toThrow();
    }
  });

  it("rejects non-objects", () => {
    expect(errorOf(() => parsePrepQueueResponse(null))).toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it.each<[string, string, (payload: ReturnType<typeof buildPrepQueueFixture>) => void]>([
    ["schedule_verified is missing", "capacity.schedule_verified", (p) => delete (p.capacity as Partial<Capacity>).schedule_verified],
    ["share is a percentage instead of a 0–1 ratio", "capacity.shifts[0].share", (p) => (p.capacity.shifts[0].share = 90)],
    ["a number arrives as a string", "orders[0].work_min", (p) => ((p.orders[0] as unknown as Mutable).work_min = "130")],
    ["loading is not an array", "orders[0].loading", (p) => ((p.orders[0] as unknown as Mutable).loading = null)],
    ["a handling group has no name", "orders[0].handling_mix[0].name", (p) => delete (p.orders[0].handling_mix[0] as unknown as Mutable).name],
    ["prep_state is unknown", "orders[0].prep_state", (p) => ((p.orders[0] as unknown as Mutable).prep_state = "stopped")],
    ["a loading entry has no after_cutoff flag", "orders[0].loading[0].after_cutoff", (p) => delete (p.orders[0].loading[0] as unknown as Mutable).after_cutoff],
    ["a shift has no start", "capacity.shifts[1].start", (p) => delete (p.capacity.shifts[1] as unknown as Mutable).start],
  ])("rejects the payload when %s, naming the field", (_label, field, mutate) => {
    const payload = buildPrepQueueFixture("verified");
    mutate(payload);

    expect(errorOf(() => parsePrepQueueResponse(payload))).toMatchObject({ code: "INVALID_RESPONSE", details: { field } });
  });

  it("keeps an unknown order status and treats a missing next_action as null", () => {
    const payload = buildPrepQueueFixture("verified");
    (payload.orders[0] as unknown as Mutable).status = "SOMETHING_NEW";
    delete (payload.orders[0] as unknown as Mutable).next_action;

    const parsed = parsePrepQueueResponse(payload);
    expect(parsed.orders[0].status).toBe("SOMETHING_NEW");
    expect(parsed.orders[0].next_action).toBeNull();
  });
});
describe("Q7 prep_window.start", () => {
  it("accepts null before preparation starts and still requires `end`", () => {
    const base = buildPrepQueueFixture("verified");
    const order = { ...base.orders[0], prep_window: { start: null, end: "2026-11-10T09:00:00+01:00" } };
    const parsed = parsePrepQueueResponse({ ...base, orders: [order] });
    expect(parsed.orders[0].prep_window.start).toBeNull();
    const broken = { ...base.orders[0], prep_window: { start: null } };
    expect(() => parsePrepQueueResponse({ ...base, orders: [broken] })).toThrow();
  });
});
