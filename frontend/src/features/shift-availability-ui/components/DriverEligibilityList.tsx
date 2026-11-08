/**
 * DriverEligibilityList — already-evaluated eligibility results for one driver (display only).
 * Icon + text + reference codes; never colour alone. `unknown` is its own state and is never
 * shown as eligible or as out of scope (DEC-DEV2-D7-001).
 * An empty `items` list means eligibility was NOT evaluated; that is stated explicitly so an
 * "available" assignment status is never read as "meets every requirement".
 */
import { CheckCircle2, HelpCircle, XCircle, type LucideIcon } from "lucide-react";
import { mergeLabels, type ShiftAvailabilityLabelOverrides } from "../labels";
import { ELIGIBILITY_STATUS_CLASS } from "../styles";
import type { DriverEligibilityItem, EligibilityStatus } from "../types";

const ICON: Record<EligibilityStatus, LucideIcon> = {
  eligible: CheckCircle2,
  not_eligible: XCircle,
  unknown: HelpCircle,
};

export interface DriverEligibilityListProps {
  items: readonly DriverEligibilityItem[];
  labels?: ShiftAvailabilityLabelOverrides;
  className?: string;
}

export function DriverEligibilityList({ items, labels, className }: DriverEligibilityListProps) {
  const text = mergeLabels(labels);

  if (items.length === 0) {
    return (
      <div
        role="note"
        data-eligibility="not-evaluated"
        className={[
          "flex items-start gap-2 rounded-control px-3 py-2 text-body",
          ELIGIBILITY_STATUS_CLASS.unknown,
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <HelpCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <p className="font-semibold">{text.eligibilityNotEvaluated}</p>
          <p>{text.eligibilityNotEvaluatedHint}</p>
        </div>
      </div>
    );
  }

  return (
    <ul aria-label={text.eligibilityTitle} className={["flex flex-col gap-2", className].filter(Boolean).join(" ")}>
      {items.map((item) => {
        const Icon = ICON[item.status];
        return (
          <li
            key={item.id}
            data-status={item.status}
            data-kind={item.kind}
            className={["flex items-start gap-2 rounded-control px-3 py-2 text-body", ELIGIBILITY_STATUS_CLASS[item.status]].join(" ")}
          >
            <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="min-w-0">
              <p>
                <span className="font-semibold">{text.eligibilityKind[item.kind]}</span>
                <span className="mx-1.5" aria-hidden="true">
                  ·
                </span>
                <span>{text.eligibilityStatus[item.status]}</span>
              </p>
              <p>{item.summary}</p>
              {(item.reasonCode || item.ruleSource) && (
                <p className="break-all font-mono text-caption opacity-80">
                  {[item.reasonCode, item.ruleSource].filter(Boolean).join(" · ")}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}