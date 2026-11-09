import { describe, expect, it } from "vitest";
import { money, noCustomerNames, validPeriod } from "./revenueApi";
describe("US-REV-01 AC5–AC11 — display-only contract helpers", () => {
  it("rejects invalid/reversed and >366-day ranges before an API call", () => {
    expect(validPeriod("", "")).toBe(true);
    expect(validPeriod("2026-11-01", "2026-11-30")).toBe(true);
    expect(validPeriod("2026-11-30", "2026-11-01")).toBe(false);
    expect(validPeriod("2026-02-30", "2026-11-30")).toBe(false);
    expect(validPeriod("2025-01-01", "2026-11-30")).toBe(false);
    expect(validPeriod("2026-11-01", "")).toBe(false);
  });
  it("renders only server decimal strings, without recomputing authoritative totals", () => {
    expect(money("1284500.00", "SEK")).toBe("1\u202f284\u202f500 SEK");
    expect(money("214300.50", "SEK")).toBe("214\u202f300.50 SEK");
    expect(money(null, "SEK")).toBe("—");
    expect(money("not-a-number", "SEK")).toBe("—");
  });
  it("removes customer names from a Business owner order list even if the API leaks one", () => {
    const raw = [{ order_no: "SE-1", delivered_at: null, amount: "20.00", currency: "SEK",
      status: "DELIVERED", customer_name: "PRIVATE TEST CUSTOMER" }];
    expect(JSON.stringify(noCustomerNames(raw))).not.toContain("PRIVATE TEST CUSTOMER");
  });
});
