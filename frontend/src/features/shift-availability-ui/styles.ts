import type { AssignmentStatus, EligibilityStatus, WarningSeverity } from "./types";

/**
 * Tailwind class maps built only from the design tokens in tailwind.config.ts (09 §9: no hex).
 * Full class strings are written out so Tailwind can scan them. Meaning is never carried by
 * colour alone: every consumer also renders a text label and an icon.
 */
export const ASSIGNMENT_STATUS_CLASS: Record<AssignmentStatus, string> = {
  assigned: "bg-risk-onTrack-bg text-risk-onTrack-fg",
  tentative: "bg-risk-atRisk-bg text-risk-atRisk-fg",
  available: "bg-surface text-ink border",
  conflict: "bg-risk-predictedLate-bg text-risk-predictedLate-fg",
  unavailable: "bg-chip text-inkMuted",
};

export const WARNING_SEVERITY_CLASS: Record<WarningSeverity, string> = {
  info: "bg-chip text-ink",
  warning: "bg-risk-atRisk-bg text-risk-atRisk-fg border-l-[3px] border-l-apricot",
  blocking: "bg-risk-predictedLate-bg text-risk-predictedLate-fg font-semibold",
};

export const ELIGIBILITY_STATUS_CLASS: Record<EligibilityStatus, string> = {
  eligible: "bg-risk-onTrack-bg text-risk-onTrack-fg",
  not_eligible: "bg-risk-predictedLate-bg text-risk-predictedLate-fg",
  unknown: "bg-risk-atRisk-bg text-risk-atRisk-fg",
};