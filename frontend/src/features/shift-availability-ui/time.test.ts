import { describe, expect, it } from "vitest";
import { DEMO_WINDOW } from "./fixtures";
import {
  formatClock,
  formatDuration,
  hourTicks,
  outsideShiftPortions,
  rangeToPercent,
} from "./time";
import type { ShiftBlock } from "./types";

/** Demo timestamp at +01:00. */
const t = (hhmm: string, day = 9) => `2026-11-${String(day).padStart(2, "0")}T${hhmm}:00+01:00`;

const shift = (id: string, start: string, end: string): ShiftBlock => ({ id, range: { start, end } });

describe("formatClock", () => {
  it("shows 24 h time in the requested time zone", () => {
    expect(formatClock(t("06:00"), "Europe/Stockholm")).toBe("06:00");
    expect(formatClock(t("06:00"), "UTC")).toBe("05:00");
  });

  it("returns a dash for invalid input instead of throwing", () => {
    expect(formatClock("not-a-date", "UTC")).toBe("—");
    expect(formatClock(t("06:00"), "Not/AZone")).toBe("—");
  });
});

describe("formatDuration", () => {
  it.each([
    [450, "7 h 30 min"],
    [45, "45 min"],
    [120, "2 h"],
    [0, "0 min"],
  ])("formats %i minutes as %s", (minutes, expected) => {
    expect(formatDuration(minutes)).toBe(expected);
  });

  it("returns a dash for negative or non-finite values", () => {
    expect(formatDuration(-1)).toBe("—");
    expect(formatDuration(Number.NaN)).toBe("—");
  });
});

describe("rangeToPercent", () => {
  it("positions a range inside a 24 h window", () => {
    const pos = rangeToPercent({ start: t("06:00"), end: t("14:00") }, DEMO_WINDOW);
    expect(pos).not.toBeNull();
    expect(pos?.left).toBeCloseTo((2 / 24) * 100, 3);
    expect(pos?.width).toBeCloseTo((8 / 24) * 100, 3);
    expect(pos?.clippedStart).toBe(false);
    expect(pos?.clippedEnd).toBe(false);
  });

  it("positions a shift that crosses midnight as one continuous block", () => {
    const pos = rangeToPercent({ start: t("18:00"), end: t("02:00", 10) }, DEMO_WINDOW);
    expect(pos?.left).toBeCloseTo((14 / 24) * 100, 3);
    expect(pos?.width).toBeCloseTo((8 / 24) * 100, 3);
    expect(pos?.clippedEnd).toBe(false);
  });

  it("clips a range that ends after the window", () => {
    const pos = rangeToPercent({ start: t("03:00", 10), end: t("05:00", 10) }, DEMO_WINDOW);
    expect(pos?.clippedEnd).toBe(true);
    expect(pos?.clippedStart).toBe(false);
    expect(pos?.left).toBeCloseTo((23 / 24) * 100, 3);
    expect(pos?.width).toBeCloseTo((1 / 24) * 100, 3);
  });

  it("clips a range that starts before the window", () => {
    const pos = rangeToPercent({ start: t("02:00"), end: t("05:00") }, DEMO_WINDOW);
    expect(pos?.clippedStart).toBe(true);
    expect(pos?.left).toBe(0);
    expect(pos?.width).toBeCloseTo((1 / 24) * 100, 3);
  });

  it("returns null for ranges outside the window, reversed ranges and invalid dates", () => {
    expect(rangeToPercent({ start: t("01:00"), end: t("03:00") }, DEMO_WINDOW)).toBeNull();
    expect(rangeToPercent({ start: t("10:00"), end: t("09:00") }, DEMO_WINDOW)).toBeNull();
    expect(rangeToPercent({ start: "bad", end: t("09:00") }, DEMO_WINDOW)).toBeNull();
  });
});

describe("outsideShiftPortions (display hint only)", () => {
  it("returns the part of a task that runs past the shift end", () => {
    const parts = outsideShiftPortions({ start: t("12:30"), end: t("15:30") }, [shift("s1", t("06:00"), t("14:00"))]);
    expect(parts).toEqual([{ start: "2026-11-09T13:00:00.000Z", end: "2026-11-09T14:30:00.000Z" }]);
  });

  it("returns nothing when the task is fully inside a shift", () => {
    expect(outsideShiftPortions({ start: t("07:00"), end: t("09:00") }, [shift("s1", t("06:00"), t("14:00"))])).toEqual([]);
  });

  it("treats adjacent shifts as continuous coverage", () => {
    const shifts = [shift("s1", t("06:00"), t("10:00")), shift("s2", t("10:00"), t("14:00"))];
    expect(outsideShiftPortions({ start: t("08:00"), end: t("12:00") }, shifts)).toEqual([]);
  });

  it("returns the gap between two shifts", () => {
    const shifts = [shift("s1", t("06:00"), t("10:00")), shift("s2", t("12:00"), t("14:00"))];
    expect(outsideShiftPortions({ start: t("09:00"), end: t("13:00") }, shifts)).toEqual([
      { start: "2026-11-09T09:00:00.000Z", end: "2026-11-09T11:00:00.000Z" },
    ]);
  });

  it("handles a task inside a shift that crosses midnight", () => {
    const night = [shift("s1", t("18:00"), t("02:00", 10))];
    expect(outsideShiftPortions({ start: t("23:30"), end: t("01:00", 10) }, night)).toEqual([]);
  });

  it("returns the whole task when there is no shift, and nothing for invalid input", () => {
    expect(outsideShiftPortions({ start: t("09:00"), end: t("10:00") }, [])).toHaveLength(1);
    expect(outsideShiftPortions({ start: "bad", end: t("10:00") }, [])).toEqual([]);
    expect(outsideShiftPortions({ start: t("10:00"), end: t("09:00") }, [])).toEqual([]);
  });
});

describe("hourTicks", () => {
  it("returns one tick per hour including both ends of a 24 h window", () => {
    const ticks = hourTicks(DEMO_WINDOW);
    expect(ticks).toHaveLength(25);
    expect(Date.parse(ticks[0])).toBe(Date.parse(DEMO_WINDOW.start));
    expect(Date.parse(ticks[24])).toBe(Date.parse(DEMO_WINDOW.end));
  });

  it("returns no ticks for an invalid or reversed window", () => {
    expect(hourTicks({ start: "bad", end: t("10:00"), timeZone: "UTC" })).toEqual([]);
    expect(hourTicks({ start: t("10:00"), end: t("09:00"), timeZone: "UTC" })).toEqual([]);
  });
});