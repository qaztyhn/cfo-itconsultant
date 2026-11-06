/**
 * RiskChip — Colored chip with dot indicating risk level.
 * Owner: Dev 3 (luồng C).
 */

export type RiskLevel = "ON_TRACK" | "AT_RISK" | "PREDICTED_LATE" | "OVERDUE";
export type RiskColor = "green" | "yellow" | "orange" | "red";

export interface RiskChipProps {
  level?: RiskLevel;
  color?: RiskColor;
  className?: string;
}

type RiskConfig = {
  bg: string;
  fg: string;
  dot: string;
  label: string;
  leftBorder?: string;
};

function getRiskConfig(level?: RiskLevel, color?: RiskColor): RiskConfig {
  // Map color to level if level not provided
  const resolvedLevel =
    level ??
    (color === "green"
      ? "ON_TRACK"
      : color === "yellow"
      ? "AT_RISK"
      : color === "orange"
      ? "AT_RISK"
      : color === "red"
      ? "PREDICTED_LATE"
      : "ON_TRACK");

  switch (resolvedLevel) {
    case "ON_TRACK":
      return {
        bg: "bg-risk-onTrack-bg",
        fg: "text-risk-onTrack-fg",
        dot: "bg-risk-onTrack-fg",
        label: "On track",
      };
    case "AT_RISK":
      if (color === "orange") {
        return {
          bg: "bg-risk-atRisk-bg",
          fg: "text-risk-atRisk-fg",
          dot: "bg-apricot",
          label: "At risk",
          leftBorder: "border-l-[3px] border-l-apricot",
        };
      }
      return {
        bg: "bg-risk-atRisk-bg",
        fg: "text-risk-atRisk-fg",
        dot: "bg-risk-atRisk-fg",
        label: "At risk",
      };
    case "PREDICTED_LATE":
      return {
        bg: "bg-risk-predictedLate-bg",
        fg: "text-risk-predictedLate-fg",
        dot: "bg-risk-predictedLate-fg",
        label: "Predicted late",
      };
    case "OVERDUE":
      return {
        bg: "bg-risk-overdue-bg",
        fg: "text-risk-overdue-fg",
        dot: "bg-risk-overdue-fg",
        label: "Overdue",
      };
    default:
      return {
        bg: "bg-chip",
        fg: "text-ink",
        dot: "bg-inkMuted",
        label: "Unknown",
      };
  }
}

export function RiskChip({ level, color, className }: RiskChipProps) {
  const cfg = getRiskConfig(level, color);

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono ${cfg.bg} ${cfg.fg} ${cfg.leftBorder ?? ""} ${className ?? ""}`}
      aria-label={`Risk: ${cfg.label}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cfg.dot}`} aria-hidden="true" />
      {cfg.label}
    </span>
  );
}
