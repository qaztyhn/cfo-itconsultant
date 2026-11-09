import { describe, expect, it } from "vitest";
import {
  allowedDeliveryDate, manualPayload, totalsFor, validateManualDraft,
  type ManualDraft, type ManualOrder,
} from "./manualPlanModel";

const order: ManualOrder = {
  id: 42, order_no: "SE-0042", status: "PLANNED",
  date_request: { mode: "range", date_from: "2026-11-12", date_to: "2026-11-15" },
  lines: [{ line_no: 1, name: "Cement", qty_base: 800 }, { line_no: 2, name: "Tiles", qty_base: 30 }],
};
const draft: ManualDraft = {
  warehouseId: "3", targetDate: "2026-11-13", goodsReadyAt: "2026-11-12T11:20:00+01:00",
  reasonCode: "special_vehicle", reasonText: "Requires a verified split load",
  vehicles: [
    { key: 1, vehicleId: "15", driverId: "71", departAt: "2026-11-13T05:10:00+01:00",
      etaAt: "2026-11-13T07:00:00+01:00", loads: [{ line_no: 1, qty: "400" }, { line_no: 2, qty: "10" }] },
    { key: 2, vehicleId: "16", driverId: "72", departAt: "2026-11-13T05:20:00+01:00",
      etaAt: "2026-11-13T07:15:00+01:00", loads: [{ line_no: 1, qty: "400" }, { line_no: 2, qty: "20" }] },
  ],
};

describe("US-APR-02 AC4 — multi-vehicle draft validation", () => {
  it("accepts exact per-line splits across two vehicles and preserves the contract body", () => {
    expect(validateManualDraft(order, draft)).toEqual([]);
    expect(totalsFor(order, draft.vehicles)).toEqual([
      { lineNo: 1, name: "Cement", allocated: 800, required: 800 },
      { lineNo: 2, name: "Tiles", allocated: 30, required: 30 },
    ]);
    expect(manualPayload(draft)).toMatchObject({
      warehouse_id: 3, target_date: "2026-11-13",
      manual_reason_code: "special_vehicle",
      vehicles: [
        { vehicle_id: 15, driver_employee_id: 71, load_lines: [{ line_no: 1, qty_base: 400 }, { line_no: 2, qty_base: 10 }] },
        { vehicle_id: 16, driver_employee_id: 72, load_lines: [{ line_no: 1, qty_base: 400 }, { line_no: 2, qty_base: 20 }] },
      ],
    });
  });
  it("rejects underallocation and overallocation independently per line", () => {
    const bad = structuredClone(draft);
    bad.vehicles[1].loads[0].qty = "399";
    bad.vehicles[1].loads[1].qty = "21";
    const errors = validateManualDraft(order, bad);
    expect(errors).toEqual(expect.arrayContaining([
      expect.stringContaining("Line 1: allocated 799 / required 800"),
      expect.stringContaining("Line 2: allocated 31 / required 30"),
    ]));
  });
  it("rejects missing, negative, nonnumeric, and duplicate vehicle/driver inputs", () => {
    const bad = structuredClone(draft);
    bad.vehicles[1].vehicleId = "15";
    bad.vehicles[1].driverId = "71";
    bad.vehicles[0].loads[0].qty = "-1";
    bad.vehicles[1].loads[0].qty = "NaN";
    expect(validateManualDraft(order, bad).join(" ")).toMatch(/unique/);
    expect(validateManualDraft(order, bad).join(" ")).toMatch(/invalid quantity/);
    expect(validateManualDraft(order, { ...draft, vehicles: [] })).toContain("Add at least one vehicle.");
  });
  it("requires a reason and zoned valid times, with goods-ready before departure", () => {
    const bad = structuredClone(draft);
    bad.reasonCode = " ";
    bad.goodsReadyAt = "2026-11-13T08:00:00+01:00";
    bad.vehicles[0].etaAt = "2026-11-13T05:00:00+01:00";
    expect(validateManualDraft(order, bad).join(" ")).toMatch(/reason/);
    expect(validateManualDraft(order, bad).join(" ")).toMatch(/times after goods are ready/);
    expect(validateManualDraft(order, { ...draft, goodsReadyAt: "2026-11-12T11:20" }).join(" ")).toMatch(/time zone/);
  });
});

describe("US-PLN-04 / US-PLN-07 AC2 — customer date protection", () => {
  it("enforces exact, range and latest boundaries without silently changing requested dates", () => {
    expect(allowedDeliveryDate(order, "2026-11-13")).toBe(true);
    expect(allowedDeliveryDate(order, "2026-11-16")).toBe(false);
    expect(allowedDeliveryDate(order, "2026-02-30")).toBe(false);
    expect(allowedDeliveryDate({ ...order, date_request: { mode: "exact", date_from: null, date_to: "2026-11-13" } }, "2026-11-12")).toBe(false);
    expect(allowedDeliveryDate({ ...order, date_request: { mode: "latest", date_from: null, date_to: "2026-11-15" } }, "2026-11-12")).toBe(true);
  });
  it("blocks noneligible order states", () => {
    expect(validateManualDraft({ ...order, status: "APPROVED" }, draft)).toContain("This order is not eligible for manual planning.");
  });
});
