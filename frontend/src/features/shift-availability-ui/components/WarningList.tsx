/**
 * WarningList — scheduling conflicts and warnings (display only).
 * Each item has an icon, a severity word, the reference code and the message; a polite live region
 * announces newly added warnings (09 §9). Whether a plan is allowed is decided by the backend.
 */
import { AlertTriangle, Info, OctagonAlert, type LucideIcon } from "lucide-react";
import { mergeLabels, type ShiftAvailabilityLabelOverrides } from "../labels";
import { WARNING_SEVERITY_CLASS } from "../styles";
import type { SchedulingWarning, WarningSeverity } from "../types";

const ICON: Record<WarningSeverity, LucideIcon> = {
  info: Info,
  warning: AlertTriangle,
  blocking: OctagonAlert,
};

export interface WarningListProps {
  warnings: readonly SchedulingWarning[];
  labels?: ShiftAvailabilityLabelOverrides;
  /** Show the section heading (default true). */
  showTitle?: boolean;
  className?: string;
}

export function WarningList({ warnings, labels, showTitle = true, className }: WarningListProps) {
  const text = mergeLabels(labels);
  if (warnings.length === 0) return null;
  return (
    <section aria-label={text.warningsTitle} className={className}>
      {showTitle && <h3 className="mb-2 text-h3 text-ink">{text.warningsTitle}</h3>}
      <ul aria-live="polite" className="flex flex-col gap-2">
        {warnings.map((w) => {
          const Icon = ICON[w.severity];
          return (
            <li
              key={w.id}
              data-severity={w.severity}
              className={["flex items-start gap-2 rounded-control px-3 py-2 text-body", WARNING_SEVERITY_CLASS[w.severity]].join(" ")}
            >
              <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="min-w-0">
                <p>
                  <span className="font-semibold">{text.warningSeverity[w.severity]}</span>
                  <span className="mx-1.5" aria-hidden="true">
                    ·
                  </span>
                  <span className="break-all font-mono text-caption">{w.code}</span>
                </p>
                <p>{w.message}</p>
                {w.ruleSource && <p className="font-mono text-caption opacity-80">{w.ruleSource}</p>}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}