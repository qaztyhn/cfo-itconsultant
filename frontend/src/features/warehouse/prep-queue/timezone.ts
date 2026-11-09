/**
 * Warehouse time zone and "today" for the Prep Queue.
 * GET /locations and /locations/{id} return a non-null IANA `timezone` (from ref.market.timezone, backend #159).
 * A missing or invalid value still makes resolveTimeZone return null and the screen stops with a clear message.
 * We never guess a time zone (docs/09 invariant 17: no implicit "now" / local clock assumptions).
 * Owner: Dev 3 (stream C) — M6.
 */
import type { WorkLocation } from "../../../api/locations";

/** WorkLocation plus the optional field the contract may add later. */
export type LocationWithTimeZone = WorkLocation & { timezone?: unknown };

export function resolveTimeZone(location: LocationWithTimeZone | null | undefined): string | null {
  const value = location?.timezone;
  if (typeof value !== "string" || value.trim() === "") {
    return null;
  }
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value });
    return value;
  } catch {
    return null;
  }
}

/** Calendar date (YYYY-MM-DD) of `now` in `timeZone`. `now` is a parameter so tests stay deterministic. */
export function todayInTimeZone(now: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}