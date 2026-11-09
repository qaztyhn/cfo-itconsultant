/**
 * DecisionBar — Thanh deep-pine dưới trang, nút apricot 'Approve #N' (không số tiền).
 * Khoá nút khi hold hết hạn, đang gửi hoặc đã duyệt; luôn có chữ giải thích, không chỉ màu.
 * Owner: Dev 3 (luồng C).
 */
import type { Plan } from "../api/contracts/planning";
import { formatTime } from "../lib/planFormat";

export interface DecisionBarProps {
  plan: Plan | null;
  expired: boolean;
  approved: boolean;
  onApprove: () => void;
  className?: string;
}

export function DecisionBar({ plan, expired, approved, onApprove, className }: DecisionBarProps) {
  const blocked = !plan || expired || approved;
  let status = "Select a plan to approve.";
  if (approved) status = "Plan approved.";
  else if (expired) status = "Hold expired. Use Plan Again to continue.";
  else if (plan) {
    const noun = plan.vehicle_count === 1 ? "vehicle" : "vehicles";
    status = `Selected plan #${plan.rank} · ${plan.warehouse?.name ?? "warehouse"} · ${plan.vehicle_count} ${noun} · ETA ${formatTime(plan.eta_at)}`;
  }

  return (
    <div
      role="region"
      aria-label="Decision"
      data-component="DecisionBar"
      className={["sticky bottom-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-card bg-deepPine px-5 py-3 text-white shadow-card", className]
        .filter(Boolean)
        .join(" ")}
    >
      <p className="text-body">{status}</p>
      <button
        type="button"
        onClick={onApprove}
        disabled={blocked}
        className="rounded-control bg-apricot px-4 py-2 text-body font-semibold text-deepPine disabled:opacity-50"
      >
        {plan ? `Approve #${plan.rank}` : "Approve"}
      </button>
    </div>
  );
}