/** Pure, side-effect-free formatting helpers. Never infer ETA, timezone, freshness or status. */
import type { TimeDatum } from "./types";

export function formatInstant(value: string | null | undefined, timeZone: string): string {
  if (!value) return "Not recorded";
  if (!/(Z|[+-][0-9]{2}:[0-9]{2})$/i.test(value)) return "Unverified timestamp";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Invalid timestamp";
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone,
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).format(date);
  } catch {
    return "Unknown time zone";
  }
}

export function timeText(datum: TimeDatum | null | undefined, timeZone: string): string {
  if (!datum) return "Not supplied";
  if (datum.quality === "missing") return "Not recorded";
  if (datum.quality === "unknown") return "Unknown";
  if (datum.quality === "unavailable") return "Unavailable";
  if (!datum.at) return "Not recorded";
  return formatInstant(datum.at, timeZone);
}

