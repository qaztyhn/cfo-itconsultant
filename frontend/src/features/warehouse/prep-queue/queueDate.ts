/**
 * Date labels for the Prep Queue header and empty state (docs/03 §5.6, §8).
 * Built from parts, so the output does not depend on the ICU build's separators.
 * Owner: Dev 3 (stream C) — M6.
 */
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export type QueueDateStyle = "short" | "long";

/** `2026-11-12` → `Thu 12 Nov` (short) or `Thursday 12 November` (long). Invalid input is returned unchanged. */
export function formatQueueDate(date: string, style: QueueDateStyle = "short"): string {
  if (!ISO_DATE.test(date)) return date;
  const instant = new Date(`${date}T12:00:00Z`);
  if (!Number.isFinite(instant.getTime())) return date;

  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: style, day: "numeric", month: style }).formatToParts(instant);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("weekday")} ${get("day")} ${get("month")}`;
}