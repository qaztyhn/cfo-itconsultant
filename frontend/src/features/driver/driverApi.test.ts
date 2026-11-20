import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet } from "../../api/client";
import { assignedTrips } from "./driverApi";

vi.mock("../../api/client", () => ({ apiGet: vi.fn(), apiPost: vi.fn() }));

beforeEach(() => vi.mocked(apiGet).mockReset());

describe("assigned-trip response boundary", () => {
  it("accepts a genuinely empty assigned list", async () => {
    vi.mocked(apiGet).mockResolvedValue({ items: [] });
    await expect(assignedTrips()).resolves.toEqual([]);
  });

  it("rejects obsolete or partial DTOs instead of showing a false empty state", async () => {
    vi.mocked(apiGet).mockResolvedValue({ items: [{ trip_id: 12, vehicle_code: "V-12", status: "loading" }] });
    await expect(assignedTrips()).rejects.toThrow("Unverified assigned-trip contract");
  });

  it("rejects a malformed stop among otherwise valid assigned trips", async () => {
    vi.mocked(apiGet).mockResolvedValue({ items: [{
      trip_id: 12, vehicle_code: "V-12", status: "loading",
      stops: [{ order_id: 44, trip_stop_id: 30, order_no: "SE-44", delivery_address: "Demo site" }],
    }] });
    await expect(assignedTrips()).rejects.toThrow("Unverified assigned-trip contract");
  });
});
