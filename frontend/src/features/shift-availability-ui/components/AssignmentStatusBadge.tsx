/**
 * AssignmentStatusBadge — pill showing a row's or task's assignment status.
 * Always icon + text (never colour alone, docs/03 §1.5, 09 §9). Presentation only.
 */
import { AlertTriangle, CheckCircle2, Circle, Clock, MinusCircle, type LucideIcon } from "lucide-react";
import { mergeLabels, type ShiftAvailabilityLabelOverrides } from "../labels";
import { ASSIGNMENT_STATUS_CLASS } from "../styles";
import type { AssignmentStatus } from "../types";

const ICON: Record<AssignmentStatus, LucideIcon> = {
  assigned: CheckCircle2,
  tentative: Clock,
  available: Circle,
  conflict: AlertTriangle,
  unavailable: MinusCircle,
};

export interface AssignmentStatusBadgeProps {
  status: AssignmentStatus;
  labels?: ShiftAvailabilityLabelOverrides;
  className?: string;
}

export function AssignmentStatusBadge({ status, labels, className }: AssignmentStatusBadgeProps) {
  const text = mergeLabels(labels).assignmentStatus[status];
  const Icon = ICON[status];
  return (
    <span
      data-status={status}
      className={[
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-mono text-caption",
        ASSIGNMENT_STATUS_CLASS[status],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
      <span>{text}</span>
    </span>
  );
}