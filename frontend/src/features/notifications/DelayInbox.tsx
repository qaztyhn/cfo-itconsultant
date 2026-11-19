import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { isApiError, newIdempotencyKey } from "../../api/client";
import { useAuthStore } from "../../app/store";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { formatInstant } from "../tracking-risk-ui/format";
import { discardNotice, fetchDrafts, fetchNotice, sendNotice, type SendPayload } from "./api";

type SendAttempt = { id: number; key: string; payload: SendPayload };
type WindowEdit = { key: string; start: string; end: string; agreementId: string };
const OFFSET_TIMESTAMP = /^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)$/;

function instant(value: string): number | null {
  const time = Date.parse(value);
  return OFFSET_TIMESTAMP.test(value) && Number.isFinite(time) ? time : null;
}

function localDate(value: string, timeZone: string): string | null {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone, year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date(value));
  } catch {
    return null;
  }
}

function windowText(start: string, end: string, timeZone: string): string {
  return `${formatInstant(start, timeZone)} – ${formatInstant(end, timeZone)}`;
}

export function NotificationInbox() {
  const user = useAuthStore((state) => state.user);
  const canAct = Boolean(user?.roles.includes("dispatcher") && user.market);
  const [params] = useSearchParams();
  const parsedOrderId = Number(params.get("order_id"));
  const orderId = Number.isSafeInteger(parsedOrderId) && parsedOrderId > 0 ? parsedOrderId : undefined;
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [edit, setEdit] = useState<WindowEdit | null>(null);
  const [discardReason, setDiscardReason] = useState("");
  const [pendingSend, setPendingSend] = useState<SendAttempt | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [actionMessage, setActionMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  const list = useQuery({
    queryKey: ["notifications", "draft", orderId],
    queryFn: ({ signal }) => fetchDrafts(orderId, signal),
    retry: false,
  });
  const activeId = selectedId ?? list.data?.[0]?.id ?? null;
  const detail = useQuery({
    queryKey: ["notifications", "detail", activeId],
    queryFn: ({ signal }) => fetchNotice(activeId!, signal),
    enabled: activeId !== null,
    retry: false,
  });
  const notice = detail.data;
  const saved = notice?.etaWindow;
  const editKey = `${notice?.id ?? ""}:${saved?.start ?? ""}:${saved?.end ?? ""}:${saved?.version ?? ""}`;
  const activeEdit = edit?.key === editKey ? edit : null;
  const start = activeEdit?.start ?? saved?.start ?? "";
  const end = activeEdit?.end ?? saved?.end ?? "";
  const agreementId = activeEdit?.agreementId ?? "";

  function updateEdit(patch: Partial<Omit<WindowEdit, "key">>) {
    setEdit({ key: editKey, start, end, agreementId, ...patch });
  }

  const startTime = instant(start);
  const endTime = instant(end);
  const intervalValid = startTime !== null && endTime !== null && endTime > startTime;
  const changed = Boolean(saved && (start !== saved.start || end !== saved.end));
  const dateChanged = Boolean(saved && notice && startTime !== null &&
    localDate(start, notice.marketTimezone) !== localDate(saved.start, notice.marketTimezone));
  const agreement = Number(agreementId);
  const agreementValid = !dateChanged || (Number.isSafeInteger(agreement) && agreement > 0);
  const versionValid = saved?.version !== null && saved?.version !== undefined;
  const canSend = canAct && notice?.status === "draft" && versionValid && intervalValid && agreementValid && !busy && !pendingSend;

  async function refresh() {
    setEdit(null);
    await Promise.all([list.refetch(), detail.refetch()]);
  }

  function select(id: number) {
    setSelectedId(id);
    setEdit(null);
    setPendingSend(null);
    setActionError(null);
    setActionMessage("");
  }

  async function submitSend(retry: boolean) {
    if (inFlight.current || !notice || !canAct) return;
    let attempt = retry ? pendingSend : null;
    if (!attempt) {
      if (!canSend || !saved || saved.version === null) return;
      attempt = {
        id: notice.id,
        key: newIdempotencyKey(),
        payload: {
          eta_window: { start, end },
          version: changed ? saved.version + 1 : saved.version,
          reason_code: "PREDICTED_LATE",
          ...(dateChanged ? { date_negotiation_id: agreement } : {}),
        },
      };
    }
    inFlight.current = true;
    setBusy(true);
    setPendingSend(attempt);
    setActionError(null);
    try {
      const status = await sendNotice(attempt.id, attempt.payload, attempt.key);
      setPendingSend(null);
      setSelectedId(attempt.id);
      setActionMessage(status === "queued" ? "Queued for delivery. Awaiting worker confirmation." : `Server status: ${status}.`);
      await refresh();
    } catch (error) {
      setActionError(error);
      if (isApiError(error) && error.status === 409) {
        setPendingSend(null);
        setActionMessage("The draft changed. Review the refreshed version before sending again.");
        await refresh();
      } else if (isApiError(error) && error.status !== 0 && error.status !== undefined && error.status < 500) {
        setPendingSend(null);
        await detail.refetch();
      } else {
        setActionMessage("Delivery result is unknown. Retry uses the same request and key.");
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function discard() {
    if (inFlight.current || !notice || !canAct || notice.status !== "draft" || !discardReason.trim()) return;
    inFlight.current = true;
    setBusy(true);
    setActionError(null);
    try {
      const status = await discardNotice(notice.id, discardReason.trim());
      setDiscardReason("");
      setSelectedId(notice.id);
      setActionMessage(`Server status: ${status}.`);
      await refresh();
    } catch (error) {
      setActionError(error);
      if (isApiError(error) && error.status === 409) {
        setActionMessage("The draft changed. Review the refreshed version.");
        await refresh();
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <section data-screen="NotificationInbox" className="space-y-6">
      <header>
        <p className="font-mono text-xs font-semibold uppercase tracking-widest text-apricot">Customer communication · Outbox</p>
        <h1 className="mt-2 text-4xl font-bold text-ink">Notification inbox</h1>
        <p className="mt-2 text-body text-inkMuted">Email goes to Mailpit locally. DELAY notices require a Dispatcher to send or discard them. No SMS.</p>
      </header>
      <div className="grid gap-5 lg:grid-cols-[minmax(16rem,1fr)_minmax(22rem,2fr)]">
        <section aria-label="Delay drafts" className="rounded-card border border-border bg-surface p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-h3 font-semibold text-ink">Delay drafts{orderId ? ` · order ${orderId}` : ""}</h2>
            <button type="button" onClick={() => void list.refetch()} className="rounded-control border px-3 py-1 text-body text-ink">Reload</button>
          </div>
          {list.isPending ? <LoadingState rows={3} /> : list.isError ?
            <ErrorState title="Drafts unavailable" error={list.error} onRetry={() => void list.refetch()} /> :
            list.data.length === 0 ? <EmptyState message="No DELAY drafts are waiting for review." /> :
              <ul className="space-y-2">{list.data.map((item) => (
                <li key={item.id}>
                  <button type="button" onClick={() => select(item.id)} aria-current={activeId === item.id ? "true" : undefined}
                    className="w-full rounded-card border border-border bg-surface p-3 text-left hover:bg-rowHover">
                    <span className="font-mono text-body font-semibold text-ink">{item.orderNo}</span>
                    <span className="ml-2 text-caption uppercase text-inkMuted">DELAY · {item.status}</span>
                    <span className="mt-1 block text-caption text-inkMuted">{item.recipientMasked ?? "No email"}</span>
                  </button>
                </li>
              ))}</ul>}
        </section>
        <section aria-label="Notification detail" className="rounded-card border border-border bg-surface p-5">
          {activeId === null ? <EmptyState message="Select a DELAY draft to inspect its email." /> :
            detail.isPending ? <LoadingState rows={4} /> : detail.isError ?
              <ErrorState title="Draft detail unavailable" error={detail.error} onRetry={() => void detail.refetch()} /> : notice ? <>
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-h3 font-semibold text-ink">{notice.orderNo} · {notice.status}</h2>
                  <button type="button" onClick={() => void refresh()} className="rounded-control border px-3 py-1 text-body text-ink">Reload draft</button>
                </div>
                <p className="text-caption text-inkMuted">Times in {notice.marketTimezone}</p>
                {saved && <p className="mt-2 text-body text-ink">Saved preview window: {windowText(saved.start, saved.end, notice.marketTimezone)}</p>}
                <div className="mt-4 border-t-4 border-apricot bg-chip p-4">
                  <p className="text-caption text-inkMuted">From: CFO deliveries (demo) · To: {notice.recipientMasked ?? "No email"}</p>
                  <p className="mt-2 text-body font-semibold text-ink">{notice.subject ?? "No subject"}</p>
                  <pre className="mt-3 whitespace-pre-wrap font-sans text-body text-ink">{notice.bodyText}</pre>
                </div>
                <p className="mt-3 text-caption text-inkMuted">Customers see status and ETA only. Never driver location or GPS.</p>
                {canAct && notice.status === "draft" && <div className="mt-5 space-y-4 border-t border-border pt-4">
                  <h3 className="text-body font-semibold text-ink">Review DELAY notice</h3>
                  {!versionValid && <p role="alert" className="text-body text-risk-predictedLate-fg">Approved ETA version is missing. Reload the draft before Send.</p>}
                  <label className="block text-body text-ink">Proposed start · ISO 8601 with offset
                    <input value={start} onChange={(event) => updateEdit({ start: event.target.value })} disabled={Boolean(pendingSend)}
                      className="mt-1 w-full rounded-control border border-border p-2 font-mono text-body" />
                  </label>
                  <label className="block text-body text-ink">Proposed end · ISO 8601 with offset
                    <input value={end} onChange={(event) => updateEdit({ end: event.target.value })} disabled={Boolean(pendingSend)}
                      className="mt-1 w-full rounded-control border border-border p-2 font-mono text-body" />
                  </label>
                  {changed && intervalValid && <p className="text-body text-ink">Proposed window: {windowText(start, end, notice.marketTimezone)}. The saved email preview above still shows the prior window; the server renders the final email on Send.</p>}
                  {!intervalValid && <p role="alert" className="text-body text-risk-predictedLate-fg">Enter offset-aware times with an end after the start.</p>}
                  <label className="block text-body text-ink">Reason template
                    <select value="PREDICTED_LATE" disabled className="mt-1 w-full rounded-control border border-border p-2 text-body"><option value="PREDICTED_LATE">Predicted late</option></select>
                  </label>
                  {dateChanged && <label className="block text-body text-ink">Agreed date negotiation ID
                    <input value={agreementId} onChange={(event) => updateEdit({ agreementId: event.target.value })} inputMode="numeric" disabled={Boolean(pendingSend)}
                      className="mt-1 w-full rounded-control border border-border p-2 text-body" />
                  </label>}
                  {dateChanged && !agreementValid && <p role="alert" className="text-body text-risk-predictedLate-fg">A recorded customer date agreement is required.</p>}
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => void submitSend(false)} disabled={!canSend} className="rounded-control bg-pine px-4 py-2 text-body font-semibold text-white disabled:opacity-50">Send</button>
                    {pendingSend && <button type="button" onClick={() => void submitSend(true)} disabled={busy} className="rounded-control border px-4 py-2 text-body text-ink disabled:opacity-50">Retry same request</button>}
                  </div>
                  <label className="block text-body text-ink">Discard reason · internal audit only
                    <textarea value={discardReason} onChange={(event) => setDiscardReason(event.target.value)} disabled={busy || Boolean(pendingSend)}
                      className="mt-1 w-full rounded-control border border-border p-2 text-body" />
                  </label>
                  <button type="button" onClick={() => void discard()} disabled={busy || Boolean(pendingSend) || !discardReason.trim()}
                    className="rounded-control border px-4 py-2 text-body font-semibold text-ink disabled:opacity-50">Discard</button>
                </div>}
                {actionMessage && <p role="status" className="mt-4 text-body text-ink">{actionMessage}</p>}
                {actionError && <div className="mt-4"><ErrorState title="Notification action failed" error={actionError} /></div>}
              </> : null}
        </section>
      </div>
    </section>
  );
}
