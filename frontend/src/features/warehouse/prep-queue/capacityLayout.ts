/**
 * Pure layout for the Capacity bar: each shift is placed on a time axis (first start → last end),
 * filled by booked / minutes. Nothing here decides whether capacity is verified (see isCapacityVerified).
 * Owner: Dev 3 (stream C) — M6.
 */
import type { CapacityShift } from "./types";

const CLOCK = /^([01]\d|2[0-3]):([0-5]\d)$/;
const DAY = 1440;

export function clockToMinutes(value: string | null | undefined): number | null {
  const match = value ? CLOCK.exec(value) : null;
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}

export interface ShiftSegment {
  name: string;
  leftPct: number;
  widthPct: number;
  /** Share of this shift's minutes that is booked, 0–100. */
  fillPct: number;
}

export interface CapacityBarLayout {
  segments: ShiftSegment[];
  /** Position of the loading cut-off on the same axis, or null when unknown or outside the axis. */
  cutoffPct: number | null;
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

/** `cutoffClock` must already be `hh:mm` in the warehouse time zone (use formatClock first). */
export function layoutCapacityBar(shifts: CapacityShift[], cutoffClock: string | null): CapacityBarLayout {
  const placed = shifts
    .map((shift) => {
      const start = clockToMinutes(shift.start);
      const rawEnd = clockToMinutes(shift.end);
      if (start === null || rawEnd === null) return null;
      return { shift, start, end: rawEnd <= start ? rawEnd + DAY : rawEnd };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null);

  if (placed.length === 0) {
    return { segments: [], cutoffPct: null };
  }

  const axisStart = Math.min(...placed.map((p) => p.start));
  const axisEnd = Math.max(...placed.map((p) => p.end));
  const span = axisEnd - axisStart;

  const segments = placed.map(({ shift, start, end }) => ({
    name: shift.name,
    leftPct: ((start - axisStart) / span) * 100,
    widthPct: ((end - start) / span) * 100,
    fillPct: shift.minutes > 0 && Number.isFinite(shift.booked) ? clamp((shift.booked / shift.minutes) * 100, 0, 100) : 0,
  }));

  let cutoffPct: number | null = null;
  const cutoff = clockToMinutes(cutoffClock);
  if (cutoff !== null) {
    const adjusted = cutoff < axisStart ? cutoff + DAY : cutoff;
    if (adjusted >= axisStart && adjusted <= axisEnd) {
      cutoffPct = ((adjusted - axisStart) / span) * 100;
    }
  }
  return { segments, cutoffPct };
}