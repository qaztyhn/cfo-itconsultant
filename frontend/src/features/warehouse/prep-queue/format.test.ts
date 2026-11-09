import { describe, expect, it } from "vitest";
import {
  NOT_RECORDED,
  UNVERIFIED_TIME,
  formatCapacityHeadline,
  formatClock,
  formatKg,
  formatLinesWeight,
  formatLoadingTime,
  formatMinutes,
  formatShiftCaption,
  formatThousands,
  formatWindow,
  isCapacityVerified,
  isShiftFullyBooked,
} from "./format";
import type { CapacityShift } from "./types";

const TZ = "Europe/Stockholm";
const NS = "\u202f";

describe("numbers", () => {
  it("groups thousands with a narrow no-break space", () => {
    expect(formatThousands(4120)).toBe(`4${NS}120`);
    expect(formatThousands(5292)).toBe(`5${NS}292`);
    expect(formatThousands(999)).toBe("999");
    expect(formatThousands(1234567)).toBe(`1${NS}234${NS}567`);
  });

  it("shows a placeholder for non-finite numbers", () => {
    expect(formatThousands(Number.NaN)).toBe("—");
    expect(formatKg(Number.POSITIVE_INFINITY)).toBe("—");
    expect(formatMinutes(Number.NaN)).toBe("—");
  });

  it("formats kg, minutes and lines with singular/plural", () => {
    expect(formatKg(3340)).toBe(`3${NS}340 kg`);
    expect(formatMinutes(3024)).toBe(`3${NS}024 min`);
    expect(formatLinesWeight(6, 3340)).toBe(`6 lines · 3${NS}340 kg`);
    expect(formatLinesWeight(1, 80)).toBe("1 line · 80 kg");
  });
});

describe("times", () => {
  it("passes hh:mm through and converts offset timestamps to the warehouse time zone", () => {
    expect(formatClock("06:00", TZ)).toBe("06:00");
    expect(formatClock("2026-11-12T07:30:00Z", TZ)).toBe("08:30"); // CET, UTC+1 in November
    expect(formatClock("2026-07-01T07:30:00Z", TZ)).toBe("09:30"); // CEST, UTC+2
  });

  it("does not guess timestamps without an offset or invalid input", () => {
    expect(formatClock("2026-11-12T07:30:00", TZ)).toBe(UNVERIFIED_TIME);
    expect(formatClock("25:00", TZ)).toBe(UNVERIFIED_TIME);
    expect(formatClock("not a time", TZ)).toBe(UNVERIFIED_TIME);
    expect(formatClock("2026-11-12T07:30:00Z", "Not/AZone")).toBe(UNVERIFIED_TIME);
    expect(formatClock(null, TZ)).toBe(NOT_RECORDED);
    expect(formatClock("", TZ)).toBe(NOT_RECORDED);
  });

  it("formats a prep window as start → end", () => {
    expect(formatWindow("06:00", "08:10", TZ)).toBe("06:00 → 08:10");
    expect(formatWindow("2026-11-12T05:00:00Z", "2026-11-12T07:10:00Z", TZ)).toBe("06:00 → 08:10");
    expect(formatWindow(null, "08:10", TZ)).toBe(`${NOT_RECORDED} → 08:10`);
  });

  it("shows the weekday only when loading is on another day than the queue date", () => {
    expect(formatLoadingTime("2026-11-12T07:30:00Z", TZ, "2026-11-12")).toBe("08:30");
    expect(formatLoadingTime("2026-11-13T05:00:00Z", TZ, "2026-11-12")).toBe("Fri 06:00");
    expect(formatLoadingTime("08:30", TZ, "2026-11-12")).toBe("08:30");
    expect(formatLoadingTime(undefined, TZ, "2026-11-12")).toBe(NOT_RECORDED);
  });

  it("uses the warehouse time zone, not UTC, to decide the day", () => {
    // 23:30 UTC on 12 Nov is already 00:30 on 13 Nov in Stockholm.
    expect(formatLoadingTime("2026-11-12T23:30:00Z", TZ, "2026-11-12")).toBe("Fri 00:30");
  });
});

describe("US-WH-02 capacity display (values come from the API, never computed here)", () => {
  const shift: CapacityShift = { name: "Shift 1", start: "06:00", end: "14:00", present: 8, useful_hours: 7, share: 0.9, minutes: 3024, booked: 3024 };

  it("builds the headline from API numbers", () => {
    expect(formatCapacityHeadline({ booked_min: 3024, total_min: 5292, free_min: 2268 })).toBe(
      `3${NS}024 of 5${NS}292 min booked · 2${NS}268 free`,
    );
  });

  it("builds the shift caption and marks fully booked shifts", () => {
    expect(formatShiftCaption(shift)).toBe(`8 present × 7.0 h useful × 90% = 3${NS}024 min · fully booked`);
    expect(formatShiftCaption({ ...shift, name: "Shift 2", present: 6, minutes: 2268, booked: 1000 })).toBe(
      `6 present × 7.0 h useful × 90% = 2${NS}268 min`,
    );
  });

  it("does not call a zero-minute shift fully booked", () => {
    expect(isShiftFullyBooked({ minutes: 0, booked: 0 })).toBe(false);
    expect(isShiftFullyBooked({ minutes: 100, booked: 100 })).toBe(true);
    expect(isShiftFullyBooked({ minutes: 100, booked: 99 })).toBe(false);
  });

  it("ASM-007: capacity is verified only when schedule_verified === true", () => {
    expect(isCapacityVerified({ schedule_verified: true })).toBe(true);
    expect(isCapacityVerified({ schedule_verified: false })).toBe(false);
    expect(isCapacityVerified({} as { schedule_verified: boolean })).toBe(false);
    // Cast: a malformed payload (string) must not count as verified either.
    expect(isCapacityVerified({ schedule_verified: "true" as unknown as boolean })).toBe(false);
  });
});
describe("A.1 timestamps with offsets (market-local display)", () => {
  it("shows an overnight shift across the autumn DST change in the market zone", () => {
    expect(formatClock("2026-10-24T22:00:00+02:00", "Europe/Stockholm")).toBe("22:00");
    expect(formatClock("2026-10-25T06:00:00+01:00", "Europe/Stockholm")).toBe("06:00");
  });

  it("converts instants to the selected location's zone, not the browser's", () => {
    expect(formatClock("2026-11-10T07:30:00+01:00", "Europe/Oslo")).toBe("07:30");
    expect(formatClock("2026-11-10T06:30:00Z", "Europe/Copenhagen")).toBe("07:30");
  });

  it("a prep window that has not started shows 'Not recorded' for the start", () => {
    expect(formatWindow(null, "2026-11-10T09:00:00+01:00", "Europe/Stockholm")).toBe("Not recorded → 09:00");
  });
});
