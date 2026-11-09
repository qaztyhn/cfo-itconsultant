import { describe, expect, it } from "vitest";
import { resolveTimeZone, todayInTimeZone } from "./timezone";

const base = { id: 1, code: "GBG", name: "Göteborg DC", type: "warehouse" };

describe("resolveTimeZone", () => {
  it("returns the IANA zone when the location has one", () => {
    expect(resolveTimeZone({ ...base, timezone: "Europe/Stockholm" })).toBe("Europe/Stockholm");
  });

  it("returns null when the field is missing, empty, not a string or not a valid zone", () => {
    expect(resolveTimeZone(base)).toBeNull();
    expect(resolveTimeZone({ ...base, timezone: "" })).toBeNull();
    expect(resolveTimeZone({ ...base, timezone: 42 as unknown as string })).toBeNull();
    expect(resolveTimeZone({ ...base, timezone: "Mars/Olympus" })).toBeNull();
    expect(resolveTimeZone(null)).toBeNull();
    expect(resolveTimeZone(undefined)).toBeNull();
  });
});

describe("todayInTimeZone", () => {
  it("rolls to the next day in zones that are already past midnight", () => {
    const now = new Date("2026-11-11T23:30:00Z");
    expect(todayInTimeZone(now, "Europe/Stockholm")).toBe("2026-11-12");
    expect(todayInTimeZone(now, "UTC")).toBe("2026-11-11");
  });

  it("stays on the previous day in zones behind UTC", () => {
    const now = new Date("2026-11-12T00:30:00Z");
    expect(todayInTimeZone(now, "America/Los_Angeles")).toBe("2026-11-11");
  });
});