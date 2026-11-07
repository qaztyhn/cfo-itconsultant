/**
 * RiskChip — chip rủi ro có chấm tròn trước chữ (docs/03 mục 2.1, 4).
 * Màu theo eta_forecast.risk_color, nhãn theo risk_status; truyền cả hai khi API trả cả hai (red = Predicted late hoặc Overdue).
 * At risk (cam) có viền trái apricot 3px. Không có dữ liệu thì KHÔNG render (không khẳng định "On track").
 * Owner: Dev 3 (luồng C) — M0.
 */

export type RiskLevel = "ON_TRACK" | "AT_RISK" | "PREDICTED_LATE" | "OVERDUE";
export type RiskColor = "green" | "yellow" | "orange" | "red";

export interface RiskChipProps {
  level?: RiskLevel;
  color?: RiskColor;
  className?: string;
}

interface Look {
  chip: string;
  dot: string;
  label: string;
}

// Chuỗi class viết đầy đủ để Tailwind quét được.
const LOOK: Record<RiskLevel, Look> = {
  ON_TRACK: { chip: "bg-risk-onTrack-bg text-risk-onTrack-fg", dot: "bg-risk-onTrack-fg", label: "On track" },
  AT_RISK: { chip: "bg-risk-atRisk-bg text-risk-atRisk-fg", dot: "bg-risk-atRisk-fg", label: "At risk" },
  PREDICTED_LATE: { chip: "bg-risk-predictedLate-bg text-risk-predictedLate-fg", dot: "bg-risk-predictedLate-fg", label: "Predicted late" },
  OVERDUE: { chip: "bg-risk-overdue-bg text-risk-overdue-fg", dot: "bg-risk-overdue-fg", label: "Overdue" },
};

/** Khi chỉ biết màu: red hiểu là Predicted late (không phân biệt được Overdue nếu thiếu risk_status). */
const LEVEL_FROM_COLOR: Record<RiskColor, RiskLevel> = {
  green: "ON_TRACK",
  yellow: "AT_RISK",
  orange: "AT_RISK",
  red: "PREDICTED_LATE",
};

export function RiskChip({ level, color, className }: RiskChipProps) {
  const resolved = level ?? (color ? LEVEL_FROM_COLOR[color] : undefined);
  if (!resolved) {
    return null;
  }

  const look = LOOK[resolved];
  const orangeAtRisk = resolved === "AT_RISK" && color === "orange";
  const classes = [
    "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-overline",
    look.chip,
    orangeAtRisk ? "border-l-[3px] border-l-apricot" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span role="img" aria-label={`Risk: ${look.label}`} className={classes}>
      <span aria-hidden="true" className={`h-1.5 w-1.5 shrink-0 rounded-full ${look.dot}`} />
      <span aria-hidden="true">{look.label}</span>
    </span>
  );
}