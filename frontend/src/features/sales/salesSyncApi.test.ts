import { describe, expect, it } from "vitest";
import { eligibleSalesPlan, eligibleStandardPlan, isCfoRouting, safeExternalRef, validReasonCode, type SalesRun, type SyncResult } from "./salesSyncApi";

const gates = {
  stock: { passed: true, code: "STOCK_OK" },
  preparation: { passed: true, code: "PREP_OK" },
  truck: { passed: true, code: "TRUCK_OK" },
  site_date: { passed: true, code: "DATE_OK" },
  safety: { passed: true, code: "SAFETY_OK" },
};
const run: SalesRun = {
  id: 700, order_id: 44, run_no: 1, kind: "initial", result: "feasible",
  reserve_class: "safe", hold_expires_at: "2027-12-01T00:00:00Z", hold_extensions: 0,
  sales_approvable: true,
  plans: [{
    id: 88, rank: 1, approvable: true, status: "proposed", target_date: "2027-11-30",
    eta_at: "2027-11-30T09:00:00Z", vehicle_count: 1,
    vehicles: [{ seq: 1, vehicle: { id: 1, code: "TRK-1", name: "Truck", capacity_kg: "6000", capacity_m3: "30" },
      load_kg: "700", load_m3: "2", loading_start_at: "2027-11-30T06:00:00Z",
      depart_at: "2027-11-30T07:00:00Z", eta_at: "2027-11-30T09:00:00Z" }],
    checks: gates,
  }],
};
describe("DEC-ROUTING-002: routing decisions", () => {
  it("only a cfo route with a real order id enters CFO planning", () => {
    for (const status of ["legacy", "unresolved"] as const) {
      expect(isCfoRouting({ routing_status: status, order_id: 44, external_ref: "POS-1" })).toBe(false);
    }
    expect(isCfoRouting({ routing_status: "cfo", order_id: null, external_ref: "POS-1" })).toBe(false);
    expect(isCfoRouting({ routing_status: "cfo", order_id: 44, external_ref: "POS-1" })).toBe(true);
  });
  it("does not infer a routing decision from sync_status or SKU list", () => {
    const value = { external_ref: "POS-1", routing_status: "unresolved", sync_status: "synced" } as SyncResult;
    expect(isCfoRouting(value)).toBe(false);
  });
  it("permits only safely encoded POS references", () => {
    expect(safeExternalRef(" POS-SE/88_2 ")).toBe("POS-SE/88_2");
    for (const value of ["", " ", "../POS", "<script>", "ab?x=1", "a".repeat(101)]) {
      expect(safeExternalRef(value)).toBeNull();
    }
  });
});
describe("DEC-R3-10: ranked Sales plans fail closed", () => {
  it("requires an explicit server approval flag, a valid hold and all five gates", () => {
    expect(eligibleStandardPlan(run, Date.parse("2027-11-20"))).toBe(true);
    expect(eligibleStandardPlan({ ...run, sales_approvable: undefined }, Date.parse("2027-11-20"))).toBe(false);
    expect(eligibleStandardPlan({ ...run, plans: [{ ...run.plans[0], checks: undefined }] }, Date.parse("2027-11-20"))).toBe(false);
    expect(eligibleStandardPlan({ ...run, plans: [{ ...run.plans[0], checks: {
      ...gates, safety: { passed: false, code: "NO_DRIVER" },
    } }] }, Date.parse("2027-11-20"))).toBe(false);
  });
  it("accepts verified tight, alternative-rank, multi-vehicle and rerun plans", () => {
    const now = Date.parse("2027-11-20");
    const two = { ...run.plans[0], id: 89, rank: 2, vehicle_count: 2,
      vehicles: [...run.plans[0].vehicles, { ...run.plans[0].vehicles[0], seq: 2 }] };
    const three = { ...run.plans[0], id: 90, rank: 3 };
    const alternatives = { ...run, kind: "rerun" as const, reserve_class: "tight" as const,
      plans: [run.plans[0], two, three] };
    expect(eligibleSalesPlan(alternatives, 89, now)).toBe(true);
    expect(eligibleSalesPlan(alternatives, 90, now)).toBe(true);
    expect(eligibleSalesPlan(alternatives, 90, Date.parse("2027-12-02"))).toBe(false);
    expect(eligibleSalesPlan({ ...alternatives, result: "infeasible" }, 89, now)).toBe(false);
  });
  it("requires valid machine-readable reason codes", () => {
    expect(validReasonCode("customer_prefers_earlier_slot")).toBe(true);
    for (const value of ["", " A note", "Two words", "UPPER", "../unsafe"]) {
      expect(validReasonCode(value)).toBe(false);
    }
  });
});
