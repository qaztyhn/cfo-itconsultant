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
  /** Chỉ có tác dụng với APPROVED (kế hoạch do dispatcher lập tay). */
  manualPlan?: boolean;
  className?: string;
}

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