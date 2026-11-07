/**
 * StatusChip — pill mono theo enum trạng thái đơn (docs/03 mục 2.1, 4, #35).
 * Nhãn là mã enum viết hoa đúng nguyên văn (PREPARING, không viết tắt "IN PREP"); không còn MANUAL_PLANNING:
 * kế hoạch tay là nhãn phụ "Manual plan" dưới chip APPROVED.
 * Màu: mặc định nền chip chữ ink; NO_FEASIBLE_DATE/FAILED bộ Predicted late; DELIVERED/APPROVED bộ On track.
 * Owner: Dev 3 (luồng C) — M0.
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
<<<<<<< HEAD
  /** Chỉ có tác dụng với APPROVED (kế hoạch do dispatcher lập tay). */
=======
>>>>>>> origin/feat/m0-frontend-foundation
  manualPlan?: boolean;
  className?: string;
}

<<<<<<< HEAD
type Tone = "neutral" | "good" | "bad";

// Chuỗi class viết đầy đủ để Tailwind quét được.
const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-chip text-ink",
  good: "bg-risk-onTrack-bg text-risk-onTrack-fg",
  bad: "bg-risk-predictedLate-bg text-risk-predictedLate-fg",
};

// Record<OrderStatus, …> buộc compiler báo lỗi khi enum thêm trạng thái mà chưa gán màu.
const TONE: Record<OrderStatus, Tone> = {
  SUBMITTED: "neutral",
  BLOCKED_UNMAPPED_SKU: "neutral",
  PLANNED: "neutral",
  APPROVED: "good",
  NO_FEASIBLE_DATE: "bad",
  PREPARING: "neutral",
  GOODS_READY: "neutral",
  LOADED: "neutral",
  DISPATCHED: "neutral",
  DELIVERED: "good",
  FAILED: "bad",
  CANCELLED: "neutral",
};

export function StatusChip({ status, manualPlan, className }: StatusChipProps) {
  // `?? "neutral"`: giá trị lạ từ API (enum mới ở backend) vẫn hiện được thay vì vỡ giao diện.
  const tone = TONE_CLASS[TONE[status] ?? "neutral"];

  return (
    <span className={["inline-flex flex-col items-start gap-0.5", className].filter(Boolean).join(" ")}>
      <span className={`inline-flex items-center rounded-full px-2 py-0.5 font-mono text-overline uppercase ${tone}`}>{status}</span>
      {status === "APPROVED" && manualPlan && <span className="pl-1 font-mono text-caption text-inkMuted">Manual plan</span>}
    </span>
  );
}
=======
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
>>>>>>> origin/feat/m0-frontend-foundation
