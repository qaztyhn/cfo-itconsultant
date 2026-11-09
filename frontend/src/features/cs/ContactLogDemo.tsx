/**
 * Log a contact — CHỈ DEMO (docs/03 A14; docs/proposals/CS_ORDER_LOOKUP_ASSUMPTIONS_20261109.md).
 * POST/GET /orders/{id}/contact-logs còn là stub phía backend (F3) nên form KHÔNG gọi API.
 * Bản ghi chỉ nằm trong state của component, luôn gắn nhãn "Demo", không bao giờ báo đã lưu.
 * Nơi gọi truyền key={orderId} để đổi đơn thì bản ghi demo của đơn trước biến mất.
 * Switch-over: khi Dev 1 ship endpoint (docs/06 §11), thay bằng lời gọi thật theo hợp đồng đã duyệt và thêm bằng chứng tích hợp.
 */
import { useId, useState, type FormEvent } from "react";
import { CONTACT_CHANNELS, CONTACT_REASONS, DEMO_LABEL } from "./constants";
import { CsSection } from "./CsSection";

interface DemoEntry {
  id: number;
  channel: string;
  reason: string;
  note: string;
}

const FIELD = "rounded-control border bg-surface px-3 py-2 text-body text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-pine";

export function ContactLogDemo() {
  const channelId = useId();
  const reasonId = useId();
  const noteId = useId();
  const [channel, setChannel] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [entries, setEntries] = useState<DemoEntry[]>([]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const channelOption = CONTACT_CHANNELS.find((option) => option.value === channel);
    const reasonOption = CONTACT_REASONS.find((option) => option.value === reason);
    if (!channelOption || !reasonOption) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    setEntries((previous) => [
      { id: previous.length + 1, channel: channelOption.label, reason: reasonOption.label, note: note.trim() },
      ...previous,
    ]);
    setChannel("");
    setReason("");
    setNote("");
  }

  return (
    <CsSection title="Log a contact">
      <p className="w-fit rounded-control border bg-chip px-3 py-1 font-mono text-caption font-semibold text-ink">{DEMO_LABEL}</p>
      <p className="text-caption text-inkMuted">Entries below exist only on this page and disappear when you open another order.</p>

      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <label htmlFor={channelId} className="text-caption font-semibold text-ink">
              Channel
            </label>
            <select id={channelId} value={channel} onChange={(event) => setChannel(event.target.value)} className={FIELD}>
              <option value="">Choose a channel</option>
              {CONTACT_CHANNELS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor={reasonId} className="text-caption font-semibold text-ink">
              Reason
            </label>
            <select id={reasonId} value={reason} onChange={(event) => setReason(event.target.value)} className={FIELD}>
              <option value="">Choose a reason</option>
              {CONTACT_REASONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={noteId} className="text-caption font-semibold text-ink">
            Note (optional)
          </label>
          <textarea id={noteId} value={note} onChange={(event) => setNote(event.target.value)} rows={3} className={FIELD} />
        </div>
        {invalid && (
          <p role="alert" className="text-caption font-semibold text-risk-predictedLate-fg">
            Choose a channel and a reason.
          </p>
        )}
        <div>
          <button type="submit" className="rounded-control bg-pine px-4 py-2 text-body font-semibold text-white">
            Add demo entry
          </button>
        </div>
      </form>

      {entries.length > 0 && (
        <ul aria-label="Demo entries" className="flex flex-col gap-2">
          {entries.map((entry) => (
            <li key={entry.id} className="flex flex-col gap-1 rounded-card border bg-surface px-4 py-2">
              <span className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-chip px-2 py-0.5 font-mono text-overline uppercase text-ink">Demo</span>
                <span className="text-body text-ink">
                  {entry.channel} · {entry.reason}
                </span>
              </span>
              {entry.note && <p className="text-body text-inkMuted">{entry.note}</p>}
            </li>
          ))}
        </ul>
      )}
    </CsSection>
  );
}