import { describe, expect, it } from "vitest";
import { isDriverTrip } from "./driverApi";

describe("driver trip read contract", () => {
  it("rejects the obsolete global mock shape without stop evidence", () => {
    expect(isDriverTrip({ id: 1, order_id: 2, status: "LOADED", vehicle_code: "V1" })).toBe(false);
  });
  it("accepts the scoped #129 trip and stop projection", () => {
    expect(isDriverTrip({ trip_id: 1, status: "loading", vehicle_code: "V1", warehouse_code: "WH",
      depart_planned_at: "2026-11-09T08:00:00Z", stops: [{ trip_stop_id: 2, order_id: 3, order_no: "O3",
        status: "pending", eta_planned_at: "2026-11-09T09:00:00Z", receiving_window: { start: "09:00", end: "10:00" } }] })).toBe(true);
  });
});
