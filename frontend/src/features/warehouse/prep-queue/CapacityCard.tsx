/**
 * "Capacity today" card (docs/03 §5.6, US-WH-02). Read-only.
 * - Shifts come from the official schedule entered by the warehouse team; there is NO equipment row (adjustment #25, invariant 23).
 * - ASM-007: figures are shown as verified only when `schedule_verified === true`. Otherwise a warning is shown.
 *   The warning never disables actions and the card never states that the warehouse can accept more orders.
 * Owner: Dev 3 (stream C) — M6.
 */
import { AlertTriangle } from "lucide-react";
import { layoutCapacityBar } from "./capacityLayout";
import { formatCapacityHeadline, formatClock, formatMinutes, formatShiftCaption, isCapacityVerified } from "./format";
import type { Capacity } from "./types";

export const LABOUR_BANNER = "Labour standards are shared rule-based assumptions set by IT; shifts are entered by the warehouse team.";

export interface CapacityCardProps {
  capacity: Capacity;
  /** IANA time zone of the warehouse, used only to read an ISO cut-off. */
  timeZone: string;
  className?: string;
}

export function CapacityCard({ capacity, timeZone, className }: CapacityCardProps) {
  const verified = isCapacityVerified(capacity);
  // Shift times may be `hh:mm` or ISO with offset: show and lay out both in the warehouse's local time.
  const shifts = capacity.shifts.map((shift) => ({ ...shift, start: formatClock(shift.start, timeZone), end: formatClock(shift.end, timeZone) }));
  const hasShifts = shifts.length > 0;
  const cutoff = formatClock(capacity.cutoff, timeZone);
  const cutoffKnown = /^\d{2}:\d{2}$/.test(cutoff);
  const layout = layoutCapacityBar(shifts, cutoffKnown ? cutoff : null);

  return (
    <section aria-labelledby="capacity-heading" className={["rounded-card border bg-surface p-6 shadow-card", className].filter(Boolean).join(" ")}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="capacity-heading" className="text-h3 text-ink">
          Capacity today
        </h2>
        {hasShifts && <p className="font-mono text-body text-ink">{formatCapacityHeadline(capacity)}</p>}
      </div>

      {!verified && (
        <div role="status" className="mt-3 flex items-start gap-2 rounded-control bg-risk-atRisk-bg px-3 py-2 text-body text-risk-atRisk-fg">
          <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            <span className="font-semibold">Capacity not verified.</span> {hasShifts ? "The shift schedule for today is not confirmed as official. Do not use these figures to promise delivery." : "No official shift schedule is entered for today."}
          </p>
        </div>
      )}

      {hasShifts ? (
        <>
          <div className="relative mt-4" data-testid="capacity-bar">
            <div className="relative h-4 w-full rounded-control bg-chip" aria-hidden="true">
              {layout.segments.map((segment) => (
                <div key={segment.name} className="absolute top-0 h-4 overflow-hidden rounded-control border bg-surface" style={{ left: `${segment.leftPct}%`, width: `${segment.widthPct}%` }}>
                  <div className="h-full bg-pine" style={{ width: `${segment.fillPct}%` }} />
                </div>
              ))}
              {layout.cutoffPct !== null && <div className="absolute -top-1 h-6 border-l-2 border-dashed border-ink" style={{ left: `${layout.cutoffPct}%` }} />}
            </div>
          </div>

          <ul className="mt-4 flex flex-col gap-3">
            {shifts.map((shift) => (
              <li key={shift.name} className="flex flex-col gap-0.5">
                <p className="text-body font-semibold text-ink">
                  {shift.name} <span className="font-mono font-normal text-inkMuted">{shift.start}–{shift.end}</span>
                </p>
                <p className="text-caption text-inkMuted">{formatShiftCaption(shift)}</p>
                <p className="text-caption text-inkMuted">
                  {formatMinutes(shift.booked)} booked of {formatMinutes(shift.minutes)}
                </p>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <p className="mt-4 text-caption text-inkMuted">
        Loading cut-off <span className="font-mono text-ink">{cutoff}</span>
      </p>
      <p className="mt-1 text-caption text-inkMuted">{LABOUR_BANNER}</p>
    </section>
  );
}