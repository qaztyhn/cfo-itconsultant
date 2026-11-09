/**
 * Pure formatting helpers for the Prep Queue (docs/03 §8: 24h `hh:mm`, `Thu 12 Nov`, narrow-space thousands).
 * Never infer status, capacity or verification; invalid input is shown as an explicit placeholder.
 * Owner: Dev 3 (stream C) — M6.
 */
import type { Capacity, CapacityShift } from "./types";

const NARROW_SPACE = "\u202f";
const CLOCK = /^([01]\d|2[0-3]):[0-5]\d$/;
const WITH_OFFSET = /(Z|[+-]\d{2}:\d{2})$/i;

export const NOT_RECORDED = "Not recorded";
export const UNVERIFIED_TIME = "Unverified time";
export const NO_VALUE = "—";

/** `4120` → `4 120` (narrow no-break space, independent of the ICU build). */
export function formatThousands(value: number): string {
  if (!Number.isFinite(value)) return NO_VALUE;
  const rounded = Math.round(value);
  const digits = String(Math.abs(rounded)).replace(/\B(?=(\d{3})+(?!\d))/g, NARROW_SPACE);
  return rounded < 0 ? `-${digits}` : digits;
}

export const formatKg = (value: number): string => (Number.isFinite(value) ? `${formatThousands(value)} kg` : NO_VALUE);

export const formatMinutes = (value: number): string => (Number.isFinite(value) ? `${formatThousands(value)} min` : NO_VALUE);

/** `6 lines · 3 340 kg`, singular for one line. */
export function formatLinesWeight(lines: number, weightKg: number): string {
  if (!Number.isFinite(lines)) return formatKg(weightKg);
  return `${formatThousands(lines)} ${lines === 1 ? "line" : "lines"} · ${formatKg(weightKg)}`;
}

function parseInstant(value: string): Date | null {
  if (!WITH_OFFSET.test(value)) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}

/**
 * Accepts `hh:mm` (already local) or ISO 8601 with an explicit offset. A timestamp without offset is NOT guessed.
 */
export function formatClock(value: string | null | undefined, timeZone: string): string {
  if (!value) return NOT_RECORDED;
  if (CLOCK.test(value)) return value;
  const date = parseInstant(value);
  if (!date) return UNVERIFIED_TIME;
  try {
    return new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
  } catch {
    return UNVERIFIED_TIME;
  }
}

/** `YYYY-MM-DD` of an instant in the given time zone, or null when it cannot be determined. */
export function localDate(value: string, timeZone: string): string | null {
  const date = parseInstant(value);
  if (!date) return null;
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
  } catch {
    return null;
  }
}

/** `06:00 → 08:10`. */
export function formatWindow(start: string | null | undefined, end: string | null | undefined, timeZone: string): string {
  return `${formatClock(start, timeZone)} → ${formatClock(end, timeZone)}`;
}

/**
 * Loading time: `08:30`, or `Fri 06:00` when the instant falls on another day than the queue date.
 * `hh:mm` input carries no date, so it is shown as is.
 */
export function formatLoadingTime(at: string | null | undefined, timeZone: string, queueDate: string): string {
  const clock = formatClock(at, timeZone);
  if (!at || clock === NOT_RECORDED || clock === UNVERIFIED_TIME || CLOCK.test(at)) return clock;
  const day = localDate(at, timeZone);
  if (!day || day === queueDate) return clock;
  const date = parseInstant(at);
  if (!date) return clock;
  try {
    const weekday = new Intl.DateTimeFormat("en-GB", { timeZone, weekday: "short" }).format(date);
    return `${weekday} ${clock}`;
  } catch {
    return clock;
  }
}

/** `3 024 of 5 292 min booked · 2 268 free` shape from docs/03 §5.6: "<booked> of <total> min booked · <free> free". */
export function formatCapacityHeadline(capacity: Pick<Capacity, "booked_min" | "total_min" | "free_min">): string {
  return `${formatThousands(capacity.booked_min)} of ${formatThousands(capacity.total_min)} min booked · ${formatThousands(capacity.free_min)} free`;
}

/** Docs/03 §5.6 caption: "8 present × 7.0 h useful × 90% = 3 024 min" (+ " · fully booked"). Values come from the API. */
export function formatShiftCaption(shift: CapacityShift): string {
  const percent = Number.isFinite(shift.share) ? `${Math.round(shift.share * 100)}%` : NO_VALUE;
  const hours = Number.isFinite(shift.useful_hours) ? shift.useful_hours.toFixed(1) : NO_VALUE;
  const base = `${shift.present} present × ${hours} h useful × ${percent} = ${formatMinutes(shift.minutes)}`;
  return isShiftFullyBooked(shift) ? `${base} · fully booked` : base;
}

export function isShiftFullyBooked(shift: Pick<CapacityShift, "booked" | "minutes">): boolean {
  return Number.isFinite(shift.minutes) && shift.minutes > 0 && shift.booked >= shift.minutes;
}

/** Capacity is verified ONLY when the optional local field is exactly `true` (ASM-007; never infer from `present`). */
export function isCapacityVerified(capacity: Pick<Capacity, "schedule_verified">): boolean {
  return capacity.schedule_verified === true;
}