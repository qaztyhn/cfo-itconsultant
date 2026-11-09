import { describe, expect, it } from "vitest";
import { buildPrepQueueFixture, capacityUnverified, orderApproved } from "./fixtures";

describe("prep queue fixtures", () => {
  it("verified scenario has consistent capacity totals", () => {
    const { capacity } = buildPrepQueueFixture("verified");
    expect(capacity.shifts.reduce((sum, s) => sum + s.minutes, 0)).toBe(capacity.total_min);
    expect(capacity.shifts.reduce((sum, s) => sum + s.booked, 0)).toBe(capacity.booked_min);
    expect(capacity.total_min - capacity.booked_min).toBe(capacity.free_min);
    expect(capacity.schedule_verified).toBe(true);
  });

  it("covers every row state the screen must render", () => {
    const { orders } = buildPrepQueueFixture("verified");
    const states = orders.map((o) => `${o.status}/${o.prep_state ?? "-"}`);
    expect(states).toEqual(expect.arrayContaining(["APPROVED/-", "PREPARING/running", "PREPARING/paused", "GOODS_READY/-"]));
    expect(orders.some((o) => o.loading.length > 1)).toBe(true);
    expect(orders.some((o) => o.loading.some((l) => l.after_cutoff))).toBe(true);
    expect(orders.some((o) => o.loading.some((l) => l.loaded))).toBe(true);
  });

  it("ASM-007: the unverified scenario has people present but schedule_verified is false", () => {
    const capacity = capacityUnverified();
    expect(capacity.shifts.every((s) => s.present > 0)).toBe(true);
    expect(capacity.schedule_verified).toBe(false);
  });

  it("no-schedule scenario has no capacity", () => {
    const { capacity } = buildPrepQueueFixture("noSchedule");
    expect(capacity.shifts).toEqual([]);
    expect(capacity.total_min).toBe(0);
    expect(capacity.schedule_verified).toBe(false);
  });

  it("empty scenario has no orders", () => {
    expect(buildPrepQueueFixture("empty").orders).toEqual([]);
  });

  it("builders return fresh objects", () => {
    const first = orderApproved();
    first.status = "CANCELLED";
    expect(orderApproved().status).toBe("APPROVED");
  });
});