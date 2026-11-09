import { describe, expect, it } from "vitest";
import { PATHS } from "../../../app/access";
import { customerSite, destinationFor, requestedLabel, warehouseLabel } from "./rowView";

describe("destinationFor", () => {
  it("test_US_ORD_02_AC3_planned_goes_to_plan_review_list", () => {
    expect(destinationFor({ status: "PLANNED" })).toEqual({ to: PATHS.dispatcherPlanReview, label: "Plan review" });
  });

  it("test_US_ORD_02_AC3_no_feasible_date_goes_to_exceptions_list", () => {
    expect(destinationFor({ status: "NO_FEASIBLE_DATE" })).toEqual({ to: PATHS.dispatcherExceptions, label: "Exceptions" });
  });

  it.each(["APPROVED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED"])(
    "test_US_ORD_02_AC3_%s_goes_to_tracking_list",
    (status) => {
      expect(destinationFor({ status })).toEqual({ to: PATHS.dispatcherTracking, label: "Tracking" });
    },
  );

  it.each(["SUBMITTED", "FAILED", "DELIVERED", "CANCELLED", "UNKNOWN", "BLOCKED_UNMAPPED_SKU", ""])(
    "test_US_ORD_02_AC3_%s_has_no_destination",
    (status) => {
      expect(destinationFor({ status })).toBeNull();
    },
  );
});

describe("requestedLabel", () => {
  const base = { dateMode: null, dateFrom: null, dateTo: null };

  it("test_US_ORD_02_AC3_exact_shows_the_date", () => {
    expect(requestedLabel({ dateMode: "exact", dateFrom: "2026-11-10", dateTo: "2026-11-10" })).toBe("2026-11-10");
  });

  it("test_US_ORD_02_AC3_exact_prefers_date_to_and_falls_back_to_date_from", () => {
    expect(requestedLabel({ dateMode: "exact", dateFrom: "2026-11-09", dateTo: "2026-11-10" })).toBe("2026-11-10");
    expect(requestedLabel({ dateMode: "exact", dateFrom: "2026-11-09", dateTo: null })).toBe("2026-11-09");
  });

  it("test_US_ORD_02_AC3_range_shows_both_ends", () => {
    expect(requestedLabel({ dateMode: "range", dateFrom: "2026-11-10", dateTo: "2026-11-14" })).toBe("2026-11-10 → 2026-11-14");
  });

  it("test_US_ORD_02_AC3_latest_shows_by_date_to", () => {
    expect(requestedLabel({ dateMode: "latest", dateFrom: null, dateTo: "2026-11-18" })).toBe("By 2026-11-18");
  });

  it.each([
    ["exact without any date", { ...base, dateMode: "exact" }],
    ["range missing date_to", { ...base, dateMode: "range", dateFrom: "2026-11-10" }],
    ["range missing date_from", { ...base, dateMode: "range", dateTo: "2026-11-14" }],
    ["latest missing date_to", { ...base, dateMode: "latest", dateFrom: "2026-11-10" }],
    ["unknown mode", { ...base, dateMode: "flexible", dateFrom: "2026-11-10", dateTo: "2026-11-14" }],
    ["no mode", base],
  ])("test_US_ORD_02_AC3_missing_data_is_not_available_%s", (_name, order) => {
    expect(requestedLabel(order)).toBe("Not available");
  });
});

describe("warehouseLabel", () => {
  it("test_US_ORD_02_AC3_no_warehouse_says_no_source_yet", () => {
    expect(warehouseLabel({ warehouse: null })).toBe("No source yet");
  });

  it("test_US_ORD_02_AC3_warehouse_shows_code", () => {
    expect(warehouseLabel({ warehouse: { id: 7, code: "STO" } })).toBe("STO");
  });

  it("test_US_ORD_02_AC3_warehouse_without_code_falls_back_to_id", () => {
    expect(warehouseLabel({ warehouse: { id: 7, code: null } })).toBe("Warehouse #7");
  });
});

describe("customerSite", () => {
  it("test_US_ORD_02_AC3_returns_customer_and_site_as_given", () => {
    expect(customerSite({ customer: "Nordbygg AB", site: "Göteborg" })).toEqual({ customer: "Nordbygg AB", site: "Göteborg" });
  });

  it("test_US_ORD_02_AC3_missing_customer_or_site_uses_placeholders", () => {
    expect(customerSite({ customer: null, site: null })).toEqual({ customer: "Customer unavailable", site: "Site unavailable" });
  });
});