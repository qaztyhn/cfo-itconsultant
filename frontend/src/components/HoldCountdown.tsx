/**
 * HoldCountdown — đếm ngược hold_expires_at (DEC-HOLD-001). Chỉ hiển thị; nút gia hạn/Plan Again do nơi gọi truyền qua `actions`.
 * Hết hạn: chữ + ký hiệu ⌛, không chỉ màu. Mốc hết hạn lấy từ server; đồng hồ máy khách chỉ dùng để đếm.
 * Owner: Dev 3 (luồng C).
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { planningNow } from "../lib/useHoldExpired";

export interface HoldCountdownProps {
  expiresAt: string;
  extensions: number;
  maxExtensions?: number;
  /** Gọi đúng một lần khi đồng hồ về 0 (vd. refetch run để lấy trạng thái server). */
  onExpire?: () => void;
  actions?: ReactNode | ((state: { expired: boolean }) => ReactNode);
  className?: string;
}

function format(msLeft: number): string {
  const total = Math.max(0, Math.floor(msLeft / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function HoldCountdown({ expiresAt, extensions, maxExtensions = 2, onExpire, actions, className }: HoldCountdownProps) {
  const [now, setNow] = useState(planningNow);
  const notified = useRef(false);

  useEffect(() => {
    const timer = setInterval(() => setNow(planningNow()), 1000);
    return () => clearInterval(timer);
  }, []);

  const msLeft = new Date(expiresAt).getTime() - now;
  const expired = Number.isNaN(msLeft) || msLeft <= 0;
  const actionContent = typeof actions === "function" ? actions({ expired }) : actions;

  useEffect(() => {
    if (expired && !notified.current) {
      notified.current = true;
      onExpire?.();
    }
    if (!expired) notified.current = false; // hold được gia hạn: cho phép báo lại ở lần hết hạn sau
  }, [expired, onExpire]);

  return (
    <div
      data-component="HoldCountdown"
      data-expired={expired ? "true" : "false"}
      className={[
        "flex flex-wrap items-center gap-3 rounded-control border px-3 py-2 text-body",
        expired ? "border-risk-predictedLate-bg bg-risk-lateRow text-risk-predictedLate-fg" : "bg-chip text-ink",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {expired ? (
        <p role="alert" className="font-semibold">
          <span aria-hidden="true">⌛ </span>
          Hold expired. This plan can no longer be approved — use Plan Again.
        </p>
      ) : (
        <p role="timer" aria-label={`Hold expires in ${format(msLeft)}`}>
          <span aria-hidden="true">⏱ </span>
          Hold expires in <span className="font-mono font-semibold">{format(msLeft)}</span>
        </p>
      )}
      <span className="font-mono text-caption text-inkMuted">
        Extended {extensions} of {maxExtensions}
      </span>
      {actionContent && <div className="ml-auto flex flex-wrap gap-2">{actionContent}</div>}
      </div>
  );
}