import { describe, expect, it } from "vitest";
import { capacityVerified } from "./fixtures";
import { clockToMinutes, layoutCapacityBar } from "./capacityLayout";

describe("clockToMinutes", () => {
  it("reads hh:mm and rejects anything else", () => {
    expect(clockToMinutes("06:30")).toBe(390);
    expect(clockToMinutes("24:00")).toBeNull();
    expect(clockToMinutes("6:30")).toBeNull();
    expect(clockToMinutes(null)).toBeNull();
  });
});

describe("layoutCapacityBar", () => {
  it("places two shifts side by side and fills them by booked minutes", () => {
    const { segments, cutoffPct } = layoutCapacityBar(capacityVerified().shifts, "15:00");

    expect(segments).toHaveLength(2);
    expect(segments[0]).toMatchObject({ name: "Shift 1", leftPct: 0, widthPct: 50, fillPct: 100 });
    expect(segments[1].leftPct).toBe(50);
    expect(segments[1].fillPct).toBeCloseTo((1500 / 2268) * 100, 5);
    expect(cutoffPct).toBeCloseTo(((15 - 6) / 16) * 100, 5);
  });

  it("returns an empty layout when there are no shifts", () => {
    expect(layoutCapacityBar([], "15:00")).toEqual({ segments: [], cutoffPct: null });
  });

  it("drops shifts with invalid times instead of guessing", () => {
    const [first] = capacityVerified().shifts;
    const { segments } = layoutCapacityBar([{ ...first, start: "6am" }], null);
    expect(segments).toEqual([]);
  });

  it("returns no cut-off marker when it is unknown or outside the axis", () => {
    const shifts = capacityVerified().shifts;
    expect(layoutCapacityBar(shifts, null).cutoffPct).toBeNull();
    expect(layoutCapacityBar(shifts, "Unverified time").cutoffPct).toBeNull();
    expect(layoutCapacityBar(shifts, "05:00").cutoffPct).toBeNull();
  });

  it("caps the fill at 100% and handles a shift that ends after midnight", () => {
    const [first] = capacityVerified().shifts;
    const night = { ...first, start: "22:00", end: "06:00", minutes: 100, booked: 250 };
    const { segments } = layoutCapacityBar([night], null);
    expect(segments[0]).toMatchObject({ leftPct: 0, widthPct: 100, fillPct: 100 });
  });
});