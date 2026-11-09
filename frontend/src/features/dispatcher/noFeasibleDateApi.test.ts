import { describe, expect, it } from "vitest";
import { gateStatus, readableNumber, validIsoDate } from "./noFeasibleDateApi";

describe("US-PLN-07 — fail-closed evidence semantics", () => {
  it("treats missing, legacy pass, and ambiguous checks as UNKNOWN", () => {
    expect(gateStatus(undefined)).toBe("unknown");
    expect(gateStatus(null)).toBe("unknown");
    expect(gateStatus({ pass: true, code: "STOCK_OK" })).toBe("unknown");
    expect(gateStatus({ code: "STOCK_OK" })).toBe("unknown");
    expect(gateStatus({ passed: true, code: "STOCK_OK" })).toBe("passed");
    expect(gateStatus({ passed: false, code: "STOCK_SHORT" })).toBe("failed");
  });
  it("never presents stock that is unavailable, null or negative as a verified quantity", () => {
    for (const value of [null, undefined, "", "-1", "NaN", "Infinity"]) {
      expect(readableNumber(value)).toBe("Unknown");
    }
    expect(readableNumber("0")).toBe("0");
    expect(readableNumber("150")).toBe("150");
  });
  it("accepts only real ISO calendar dates", () => {
    expect(validIsoDate("2026-11-12")).toBe(true);
    for (const value of ["2026-11-31", "2026-02-29", "12 Nov", ""]) {
      expect(validIsoDate(value)).toBe(false);
    }
  });
});
