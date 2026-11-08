/**
 * WarehouseShiftPanel — warehouse staff shifts and availability for one period.
 * Wraps ShiftTimeline in the shared loading / empty / error / unavailable handling.
 * `expected_staff` is deliberately not shown or compared here (ASM-007: no staffing suggestions).
 */
import { useId } from "react";
import { mergeLabels, type ShiftAvailabilityLabelOverrides } from "../labels";
import type { PanelState, ShiftTimelineModel, WarehouseStaffRow } from "../types";
import { ShiftTimeline } from "./ShiftTimeline";
import { StatePanel } from "./StatePanel";
import { WarningList } from "./WarningList";

export interface WarehouseShiftPanelProps {
  state: PanelState<ShiftTimelineModel<WarehouseStaffRow>>;
  labels?: ShiftAvailabilityLabelOverrides;
  className?: string;
}

export function WarehouseShiftPanel({ state, labels, className }: WarehouseShiftPanelProps) {
  const text = mergeLabels(labels);
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className={["rounded-card border bg-surface p-4 shadow-card", className].filter(Boolean).join(" ")}
    >
      <h2 id={headingId} className="text-h2 text-ink">
        {text.warehouseTitle}
      </h2>
      <StatePanel state={state} labels={labels} className="mt-3">
        {(model) =>
          model.rows.length === 0 ? (
            <p className="py-8 text-center text-body text-inkMuted">{text.emptyDefault}</p>
          ) : (
            <div className="flex flex-col gap-4">
              {model.dataAsOf && (
                <p className="font-mono text-caption text-inkMuted">
                  {text.dataAsOf} {model.dataAsOf}
                </p>
              )}
              <WarningList warnings={model.warnings ?? []} labels={labels} />
              <ShiftTimeline model={model} labels={labels} />
              <p className="text-caption text-inkMuted">{text.backendValidationNote}</p>
            </div>
          )
        }
      </StatePanel>
    </section>
  );
}