/**
 * DriverAvailabilityPanel — driver shifts, rest periods, task phases, and already-evaluated
 * eligibility. Duty time and driving time are shown separately and exactly as supplied
 * (DEC-DRIVER-001). No limit is computed or hard-coded here.
 */
import { useId } from "react";
import { mergeLabels, type ShiftAvailabilityLabelOverrides } from "../labels";
import { formatDuration } from "../time";
import type { DriverRow, PanelState, ShiftTimelineModel } from "../types";
import { DriverEligibilityList } from "./DriverEligibilityList";
import { ShiftTimeline } from "./ShiftTimeline";
import { StatePanel } from "./StatePanel";
import { WarningList } from "./WarningList";

export interface DriverAvailabilityPanelProps {
  state: PanelState<ShiftTimelineModel<DriverRow>>;
  labels?: ShiftAvailabilityLabelOverrides;
  className?: string;
}

export function DriverAvailabilityPanel({ state, labels, className }: DriverAvailabilityPanelProps) {
  const text = mergeLabels(labels);
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className={["rounded-card border bg-surface p-4 shadow-card", className].filter(Boolean).join(" ")}
    >
      <h2 id={headingId} className="text-h2 text-ink">
        {text.driverTitle}
      </h2>
      <StatePanel state={state} labels={labels} className="mt-3">
        {(model) => {
          if (model.rows.length === 0) {
            return <p className="py-8 text-center text-body text-inkMuted">{text.emptyDefault}</p>;
          }
          const details = model.rows;
          return (
            <div className="flex flex-col gap-4">
              {model.dataAsOf && (
                <p className="font-mono text-caption text-inkMuted">
                  {text.dataAsOf} {model.dataAsOf}
                </p>
              )}
              <WarningList warnings={model.warnings ?? []} labels={labels} />
              <ShiftTimeline model={model} labels={labels} />
              {details.length > 0 && (
                <section aria-label={text.eligibilityTitle}>
                  <h3 className="mb-2 text-h3 text-ink">{text.eligibilityTitle}</h3>
                  <ul className="flex flex-col gap-4">
                    {details.map((row) => (
                      <li key={row.id} data-driver-id={row.id}>
                        <p className="text-body font-semibold text-ink">{row.displayName}</p>
                        {row.totals && (
                          <dl className="mt-1 flex flex-wrap gap-x-6 gap-y-1 text-body">
                            {row.totals.dutyMinutes !== undefined && (
                              <div className="flex gap-2">
                                <dt className="text-inkMuted">{text.dutyTime}</dt>
                                <dd className="font-mono text-ink">{formatDuration(row.totals.dutyMinutes)}</dd>
                              </div>
                            )}
                            {row.totals.drivingMinutes !== undefined && (
                              <div className="flex gap-2">
                                <dt className="text-inkMuted">{text.drivingTime}</dt>
                                <dd className="font-mono text-ink">{formatDuration(row.totals.drivingMinutes)}</dd>
                              </div>
                            )}
                          </dl>
                        )}
                        <DriverEligibilityList items={row.eligibility} labels={labels} className="mt-2" />
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              <p className="text-caption text-inkMuted">{text.backendValidationNote}</p>
            </div>
          );
        }}
      </StatePanel>
    </section>
  );
}