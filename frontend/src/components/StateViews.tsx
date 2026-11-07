/**
 * Trạng thái rỗng / tải / lỗi (docs/03 mục 4).
 * Rỗng: biểu tượng + một câu + hành động. Tải: skeleton cùng kích thước hàng thật. Lỗi: khung Predicted late nhạt,
 * nút Retry và correlation_id (mono, chép được).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { Inbox } from "lucide-react";
import { useState, type ReactNode } from "react";
import { isApiError } from "../api/client";

export interface EmptyStateProps {
  /** Một câu, vd. "No orders match these filters". */
  message: string;
  icon?: ReactNode;
  action?: { label: string; onClick: () => void };
  className?: string;
}

export function EmptyState({ message, icon, action, className }: EmptyStateProps) {
  return (
    <div className={["flex flex-col items-center gap-3 px-6 py-12 text-center", className].filter(Boolean).join(" ")}>
      <span aria-hidden="true" className="text-inkMuted">
        {icon ?? <Inbox className="h-8 w-8" />}
      </span>
      <p className="text-body text-inkMuted">{message}</p>
      {action && (
        <button type="button" onClick={action.onClick} className="rounded-control border bg-surface px-4 py-2 text-body font-semibold text-ink hover:bg-rowHover">
          {action.label}
        </button>
      )}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={["animate-pulse rounded-control bg-chip", className].filter(Boolean).join(" ")} />;
}

export interface LoadingStateProps {
  rows?: number;
  /** Chiều cao mỗi hàng; mặc định 72px = hàng bảng thấp nhất (03 mục 4). */
  rowClassName?: string;
  className?: string;
}

export function LoadingState({ rows = 5, rowClassName = "h-[72px]", className }: LoadingStateProps) {
  return (
    <div role="status" aria-busy="true" className={["flex flex-col gap-2", className].filter(Boolean).join(" ")}>
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className={rowClassName} />
      ))}
    </div>
  );
}

export interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
}

export function ErrorState({ error, onRetry, title = "Something went wrong", className }: ErrorStateProps) {
  const [copied, setCopied] = useState(false);
  const apiError = isApiError(error) ? error : null;
  const forbidden = apiError?.code === "FORBIDDEN";
  const message = forbidden ? "You don't have permission to view this." : (apiError?.message ?? "Unexpected error. Try again.");
  const reference = apiError?.correlationId;

  async function copyReference() {
    try {
      await navigator.clipboard.writeText(reference ?? "");
      setCopied(true);
    } catch {
      /* clipboard không khả dụng (vd. trang không bảo mật): người dùng vẫn chọn chép tay được */
    }
  }

  return (
    <div
      role="alert"
      className={["flex flex-col gap-3 rounded-card border border-risk-predictedLate-bg bg-risk-lateRow p-6", className].filter(Boolean).join(" ")}
    >
      <h2 className="text-h3 text-risk-predictedLate-fg">{title}</h2>
      <p className="text-body text-ink">{message}</p>
      {reference && (
        <p className="flex items-center gap-2 text-caption text-inkMuted">
          <span>Reference</span>
          <code className="select-all font-mono text-ink">{reference}</code>
          <button type="button" onClick={() => void copyReference()} className="rounded-control border bg-surface px-2 py-0.5 font-mono text-overline text-ink hover:bg-rowHover">
            {copied ? "Copied" : "Copy"}
          </button>
        </p>
      )}
      {onRetry && !forbidden && (
        <div>
          <button type="button" onClick={onRetry} className="rounded-control bg-pine px-4 py-2 text-body font-semibold text-white">
            Retry
          </button>
        </div>
      )}
    </div>
  );
}