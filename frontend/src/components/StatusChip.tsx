/**
 * StatusChip — Pill mono theo enum trạng thái đơn (PREPARING… không viết tắt; không còn MANUAL_PLANNING; kế hoạch tay là nhãn phụ; 03 #35).
 * Owner: Dev 3 (luồng C).
 */

export type OrderStatus =
  | "SUBMITTED"
  | "BLOCKED_UNMAPPED_SKU"
  | "PLANNED"
  | "APPROVED"
  | "NO_FEASIBLE_DATE"
  | "PREPARING"
  | "GOODS_READY"
  | "LOADED"
  | "DISPATCHED"
  | "DELIVERED"
  | "FAILED"
  | "CANCELLED";

export interface StatusChipProps {
  status: OrderStatus;
  manualPlan?: boolean;
  className?: string;
}

type ColorConfig = {
  bg: string;
  fg: string;
  border?: string;
};

function getStatusColor(status: OrderStatus): ColorConfig {
  switch (status) {
    case "SUBMITTED":
    case "BLOCKED_UNMAPPED_SKU":
      return { bg: "bg-chip", fg: "text-ink" };

    case "PLANNED":
    case "APPROVED":
      return { bg: "bg-risk-onTrack-bg", fg: "text-risk-onTrack-fg" };

    case "NO_FEASIBLE_DATE":
      return { bg: "bg-risk-predictedLate-bg", fg: "text-risk-predictedLate-fg" };

    case "PREPARING":
    case "GOODS_READY":
    case "LOADED":
    case "DISPATCHED":
      return { bg: "bg-chip", fg: "text-ink", border: "border border-pine" };

    case "DELIVERED":
      return { bg: "bg-risk-onTrack-bg", fg: "text-risk-onTrack-fg" };

    case "FAILED":
    case "CANCELLED":
      return { bg: "bg-risk-predictedLate-bg", fg: "text-risk-predictedLate-fg" };

    default:
      return { bg: "bg-chip", fg: "text-ink" };
  }
}

export function StatusChip({ status, manualPlan, className }: StatusChipProps) {
  const { bg, fg, border } = getStatusColor(status);

  return (
    <span className={`inline-flex flex-col items-start gap-0.5 ${className ?? ""}`}>
      <span
        className={`inline-flex items-center px-2 py-0.5 rounded-full font-mono uppercase text-[11px] leading-tight ${bg} ${fg} ${border ?? ""}`}
        aria-label={`Status: ${status}`}
      >
        {status}
      </span>
      {status === "APPROVED" && manualPlan && (
        <span className="text-[10px] font-mono text-inkMuted pl-1">Manual plan</span>
      )}
    </span>
  );
}
