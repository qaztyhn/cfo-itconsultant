import type { ShiftBlock, TimeRange, TimelineWindow } from "./types";

const EMPTY = "—";

export function toMs(iso: string): number {
  return Date.parse(iso);
}

function toRange(startMs: number, endMs: number): TimeRange {
  return { start: new Date(startMs).toISOString(), end: new Date(endMs).toISOString() };
}

/** "HH:mm" (24 h) in the given IANA time zone; "—" for invalid input. */
export function formatClock(iso: string, timeZone: string): string {
  const ms = toMs(iso);
  if (Number.isNaN(ms)) return EMPTY;
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).format(new Date(ms));
  } catch {
    return EMPTY;
  }
}

/** "7 h 30 min", "45 min", "2 h". */
export function formatDuration(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes < 0) return EMPTY;
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

export interface PercentRange {
  left: number;
  width: number;
  /** The range started before the window. */
  clippedStart: boolean;
  /** The range ends after the window (e.g. a shift crossing midnight). */
  clippedEnd: boolean;
}

/** Position of a range inside a window as percentages; null when invalid or outside. */
export function rangeToPercent(range: TimeRange, window: TimelineWindow): PercentRange | null {
  const ws = toMs(window.start);
  const we = toMs(window.end);
  const s = toMs(range.start);
  const e = toMs(range.end);
  if ([ws, we, s, e].some(Number.isNaN) || we <= ws || e <= s) return null;
  const cs = Math.max(s, ws);
  const ce = Math.min(e, we);
  if (ce <= cs) return null;
  const span = we - ws;
  return {
    left: ((cs - ws) / span) * 100,
    width: ((ce - cs) / span) * 100,
    clippedStart: s < ws,
    clippedEnd: e > we,
  };
}

/**
 * Parts of `task` not covered by any official shift. Purely geometric DISPLAY hint:
 * it encodes no legal limit and does not replace backend validation.
 */
export function outsideShiftPortions(task: TimeRange, shifts: readonly ShiftBlock[]): TimeRange[] {
  const ts = toMs(task.start);
  const te = toMs(task.end);
  if (Number.isNaN(ts) || Number.isNaN(te) || te <= ts) return [];
  const covered = shifts
    .map((s) => [toMs(s.range.start), toMs(s.range.end)] as const)
    .filter(([a, b]) => !Number.isNaN(a) && !Number.isNaN(b) && b > a)
    .sort((x, y) => x[0] - y[0]);
  const out: TimeRange[] = [];
  let cursor = ts;
  for (const [a, b] of covered) {
    if (b <= cursor) continue;
    if (a >= te) break;
    if (a > cursor) out.push(toRange(cursor, a));
    cursor = Math.max(cursor, b);
    if (cursor >= te) break;
  }
  if (cursor < te) out.push(toRange(cursor, te));
  return out;
}

/** Hourly tick timestamps (ISO) from the window start; capped for safety. */
export function hourTicks(window: TimelineWindow): string[] {
  const ws = toMs(window.start);
  const we = toMs(window.end);
  if (Number.isNaN(ws) || Number.isNaN(we) || we <= ws) return [];
  const ticks: string[] = [];
  for (let t = ws; t <= we && ticks.length < 200; t += 3_600_000) ticks.push(new Date(t).toISOString());
  return ticks;
}