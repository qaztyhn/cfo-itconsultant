/**
 * ReasonModal — hộp xác nhận có lý do bắt buộc (docs/03 mục 4): chọn phương án khác, đổi tiêu chí/chạy lại, kế hoạch tay,
 * hủy/lập lại đơn, bỏ bản nháp báo trễ, từ chối ánh xạ, giữ kế hoạch cũ khi có gợi ý lập lại.
 * Danh mục mã lý do do nơi gọi truyền vào (docs/06 chưa định nghĩa danh mục). Nơi gọi gửi reason_code/reason_text lên API
 * và tự đóng modal (open=false) khi thành công; lỗi từ onConfirm hiện trong modal và modal vẫn mở.
 * A11y: role=dialog + aria-modal, bẫy phím Tab, Esc đóng (trừ lúc đang gửi), trả focus về nút đã mở. Bấm nền KHÔNG đóng.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { isApiError } from "../api/client";

export interface ReasonOption {
  code: string;
  label: string;
}

export interface ReasonResult {
  /** Có khi modal có danh sách `reasons`; undefined với endpoint chỉ cần reason_text. */
  reasonCode?: string;
  reasonText: string;
}

export interface ReasonModalProps {
  open: boolean;
  title: string;
  description?: string;
  reasons?: ReasonOption[];
  codeLabel?: string;
  noteLabel?: string;
  /** Mặc định true: ghi chú không rỗng mới bật nút xác nhận. */
  requireNote?: boolean;
  confirmLabel?: string;
  onConfirm: (result: ReasonResult) => void | Promise<void>;
  onCancel: () => void;
  className?: string;
}

const FOCUSABLE = "button:not([disabled]), select:not([disabled]), textarea:not([disabled]), input:not([disabled]), a[href]";

export function ReasonModal({ open, ...dialog }: ReasonModalProps) {
  if (!open) {
    return null;
  }
  // Chỉ mount khi mở: state của form tự reset ở lần mở sau.
  return createPortal(<ReasonDialog {...dialog} />, document.body);
}

function ReasonDialog({
  title,
  description,
  reasons,
  codeLabel = "Reason",
  noteLabel = "Note",
  requireNote = true,
  confirmLabel = "Confirm",
  onConfirm,
  onCancel,
  className,
}: Omit<ReasonModalProps, "open">) {
  const titleId = useId();
  const descriptionId = useId();
  const codeId = useId();
  const noteId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  const [code, setCode] = useState("");
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  const hasReasons = reasons !== undefined && reasons.length > 0;
  const canConfirm = !pending && (!hasReasons || code !== "") && (!requireNote || note.trim() !== "");

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.querySelector<HTMLElement>("select, textarea, button")?.focus();

    return () => {
      document.body.style.overflow = previousOverflow;
      opener?.focus();
    };
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (!pending) {
          event.preventDefault();
          onCancel();
        }
        return;
      }
      if (event.key !== "Tab") {
        return;
      }

      const panel = panelRef.current;
      const items = Array.from(panel?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
      if (!panel || items.length === 0) {
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const outside = !panel.contains(document.activeElement);

      if (event.shiftKey && (document.activeElement === first || outside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || outside)) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [pending, onCancel]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canConfirm) {
      return;
    }
    setPending(true);
    setFailure(null);
    try {
      await onConfirm({ reasonCode: hasReasons ? code : undefined, reasonText: note.trim() });
    } catch (error) {
      setFailure(error);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        className={["w-full max-w-lg rounded-card border bg-surface p-6 shadow-card", className].filter(Boolean).join(" ")}
      >
        <form onSubmit={(event) => void handleSubmit(event)} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h2 id={titleId} className="text-h2 text-ink">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="text-body text-inkMuted">
                {description}
              </p>
            )}
          </div>

          {hasReasons && (
            <div className="flex flex-col gap-1">
              <label htmlFor={codeId} className="font-mono text-overline uppercase text-inkMuted">
                {codeLabel}
              </label>
              <select
                id={codeId}
                value={code}
                onChange={(event) => setCode(event.target.value)}
                disabled={pending}
                className="rounded-control border bg-surface px-3 py-2 text-body text-ink"
              >
                <option value="">Select a reason</option>
                {reasons.map((reason) => (
                  <option key={reason.code} value={reason.code}>
                    {reason.label}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex flex-col gap-1">
            <label htmlFor={noteId} className="font-mono text-overline uppercase text-inkMuted">
              {noteLabel}
            </label>
            <textarea
              id={noteId}
              rows={3}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              disabled={pending}
              aria-required={requireNote}
              className="rounded-control border bg-surface px-3 py-2 text-body text-ink"
            />
          </div>

          {failure !== null && (
            <div role="alert" className="rounded-control border border-risk-predictedLate-bg bg-risk-lateRow p-3 text-body text-risk-predictedLate-fg">
              <p>{isApiError(failure) ? failure.message : "Something went wrong. Try again."}</p>
              {isApiError(failure) && failure.correlationId && <p className="mt-1 font-mono text-caption">Ref {failure.correlationId}</p>}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button type="button" onClick={onCancel} disabled={pending} className="rounded-control border bg-surface px-4 py-2 text-body font-semibold text-ink">
              Cancel
            </button>
            <button type="submit" disabled={!canConfirm} className="rounded-control bg-pine px-4 py-2 text-body font-semibold text-white disabled:opacity-50">
              {pending ? "Working…" : confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}