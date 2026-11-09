/**
 * "Today" in a warehouse time zone, kept in state so the Prep Queue date rolls over at local midnight
 * even when nothing else re-renders (e.g. polling stopped after a 403/404, or the tab was hidden).
 * - Re-checked every minute and when the tab becomes visible again.
 * - Returns null while there is no time zone, and for the render in which the time zone just changed
 *   (the effect then publishes the correct date). Never falls back to the browser's time zone.
 * Owner: Dev 3 (stream C) — M6.
 */
import { useEffect, useState } from "react";
import { todayInTimeZone } from "./timezone";

export const TODAY_CHECK_MS = 60_000;

interface Snapshot {
  timeZone: string | null;
  date: string | null;
}

export function useToday(timeZone: string | null): string | null {
  const [snapshot, setSnapshot] = useState<Snapshot>(() => ({
    timeZone,
    date: timeZone ? todayInTimeZone(new Date(), timeZone) : null,
  }));

  useEffect(() => {
    const update = () => {
      const date = timeZone ? todayInTimeZone(new Date(), timeZone) : null;
      // Same values → same state → no re-render.
      setSnapshot((prev) => (prev.timeZone === timeZone && prev.date === date ? prev : { timeZone, date }));
    };
    update();
    const timer = setInterval(update, TODAY_CHECK_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") update();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [timeZone]);

  return snapshot.timeZone === timeZone ? snapshot.date : null;
}