import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { fetchPrepQueue, parsePrepQueueResponse } from "./api";
import { FIXTURE_DATE, FIXTURE_WAREHOUSE_ID } from "./fixtures";
import { PREP_QUEUE_URL, prepQueueFailure, prepQueueSuccess } from "./mswHandlers";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("fetchPrepQueue", () => {
  it("calls the canonical /warehouses/{id}/prep-queue with the date and returns the payload", async () => {
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

    await expect(fetchPrepQueue({ warehouse_id: 1, date: FIXTURE_DATE })).rejects.toMatchObject({
      code: "FORBIDDEN",
      status: 403,
      correlationId: "corr-403",
    });
  });

  it("surfaces 404 for a warehouse outside the user's scope", async () => {
    server.use(prepQueueFailure(404, "NOT_FOUND", "Warehouse not found", "corr-404"));

    await expect(fetchPrepQueue({ warehouse_id: 99, date: FIXTURE_DATE })).rejects.toMatchObject({ code: "NOT_FOUND", status: 404 });
  });
});

describe("parsePrepQueueResponse", () => {
  it("rejects non-objects and missing arrays", () => {
    expect(() => parsePrepQueueResponse(null)).toThrow();
    expect(() => parsePrepQueueResponse({ capacity: {}, orders: [] })).toThrow();
    expect(() => parsePrepQueueResponse({ capacity: { shifts: [], schedule_verified: true }, orders: "x" })).toThrow();
  });

  it("requires schedule_verified to be a boolean (a missing flag is never treated as verified)", () => {
    expect(() => parsePrepQueueResponse({ capacity: { shifts: [] }, orders: [] })).toThrow();
    expect(() => parsePrepQueueResponse({ capacity: { shifts: [], schedule_verified: "true" }, orders: [] })).toThrow();
  });

  it("accepts an empty queue", () => {
    expect(parsePrepQueueResponse({ capacity: { shifts: [], schedule_verified: false }, orders: [] }).orders).toEqual([]);
  });
});