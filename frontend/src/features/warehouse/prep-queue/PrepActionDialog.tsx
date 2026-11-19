/** Warehouse execution confirmation. No local transition is displayed as complete until event_id ACK. */
import { useRef, useState } from "react";
import { isApiError } from "../../../api/client";
import type { PrepQueueOrder } from "./types";
import {
  ACTION_NAMES, canPerform, eventDraft, localOccurredAt, nowLocal, prepareEvent,
  submitPrepEvent, safeActionError, type EventPayload, type PreparedEvent, type PrepEventType,
} from "./executionActions";

export interface ActionChoice {
  order: PrepQueueOrder;
  type: PrepEventType;
  tripId?: number;
  vehicleCode?: string;
}

const inputClass = "min-h-[48px] w-full rounded-control border border-border bg-surface p-3 text-body";
const secondary = "min-h-[48px] rounded-control border border-border bg-surface px-4 py-2 font-semibold text-ink";
const primary = "min-h-[48px] rounded-control bg-pine px-4 py-2 font-semibold text-white disabled:opacity-50";

/** Confirmed warehouse action only; shift-change is a report, never an edit to the approved official roster. */
export function PrepActionDialog({
  choice, warehouseId, onClose, onAcknowledged, onReload,
}: {
  choice: ActionChoice;
  warehouseId: number;
  onClose: () => void;
  onAcknowledged: () => Promise<unknown>;
  onReload: () => Promise<unknown>;
}) {
  const [clockValue, setClockValue] = useState(nowLocal);
  const [crew, setCrew] = useState("1");
  const [sku, setSku] = useState("");
  const [qty, setQty] = useState("1");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [hasAttempt, setHasAttempt] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const inFlight = useRef(false);
  const attempt = useRef<PreparedEvent | null>(null);
  const { order, type, tripId } = choice;

  const requiresCrew = type === "START_PREP";
  const skuReport = type === "SHORTAGE" || type === "BREAKAGE";

  function fields(): EventPayload {
    switch (type) {
      case "START_PREP": return { crew_size: Number(crew) };
      case "LOADED": return { trip_id: tripId ?? 0 };
      case "SHORTAGE": return { sku: sku.trim(), qty_missing: Number(qty), ...(note.trim() ? { note: note.trim() } : {}) };
      case "BREAKAGE": return { sku: sku.trim(), qty: Number(qty), ...(note.trim() ? { note: note.trim() } : {}) };
      default: return {};
    }
  }

  async function send(): Promise<void> {
    if (busy || inFlight.current || conflict || acknowledged) return;
    setWarning(null);
    setResult(null);
    if (!canPerform(order, type, tripId)) {
      setWarning("This action is not available for the current order status. Refresh the queue.");
      return;
    }
    let prepared: PreparedEvent;
    try {
      prepared = attempt.current ?? prepareEvent(eventDraft(order.order_id, type, localOccurredAt(clockValue), fields()));
      attempt.current = prepared;
      setHasAttempt(true);
    } catch (cause) {
      setWarning(cause instanceof Error ? cause.message : "Check the event fields.");
      return;
    }
    inFlight.current = true;
    setBusy(true);
    try {
      const ack = await submitPrepEvent(prepared);
      setResult(`CFO acknowledged event #${ack.event_id} for order ${order.order_no}. Refreshing the queue…`);
      setAcknowledged(true);
      attempt.current = null;
      try {
        await onAcknowledged();
        onClose();
      } catch {
        setWarning("The event was accepted, but the queue could not be refreshed. Refresh the queue; do not send the event again.");
      }
    } catch (cause) {
      setWarning(safeActionError(cause));
      if (isApiError(cause) && cause.status === 409) setConflict(true);
      // Preserve the original idempotency key, occurred_at and body for identical retry.
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-auto bg-ink/60 p-3" role="presentation">
      <section role="dialog" aria-modal="true" aria-label={`Confirm ${ACTION_NAMES[type]}`}
        className="my-auto w-full max-w-lg space-y-4 rounded-card bg-surface p-5 shadow-card">
        <h3 className="text-h3 font-semibold">Confirm {ACTION_NAMES[type]}</h3>
        <p className="text-body">Order <strong>{order.order_no}</strong> · Warehouse #{warehouseId}
          {choice.vehicleCode ? ` · ${choice.vehicleCode}` : ""}
        </p>
        <label className="block space-y-1 text-body font-semibold">
          <span>Occurred at (device local time)</span>
          <input className={inputClass} type="datetime-local" value={clockValue}
            onChange={(e) => setClockValue(e.target.value)} disabled={hasAttempt} required />
        </label>
        {requiresCrew && (
          <label className="block space-y-1 text-body font-semibold">
            <span>Crew size (people actually working)</span>
            <input className={inputClass} type="number" min="1" step="1" value={crew} onChange={(e) => setCrew(e.target.value)} disabled={hasAttempt} />
          </label>
        )}
        {skuReport && (
          <>
            <label className="block space-y-1 text-body font-semibold"><span>Local SKU</span>
              <input className={inputClass} value={sku} maxLength={120} onChange={(e) => setSku(e.target.value)} disabled={hasAttempt} /></label>
            <label className="block space-y-1 text-body font-semibold">
              <span>{type === "SHORTAGE" ? "Quantity missing" : "Quantity damaged"} (whole units)</span>
              <input className={inputClass} type="number" min="1" step="1" value={qty} onChange={(e) => setQty(e.target.value)} disabled={hasAttempt} />
            </label>
          </>
        )}
        {(["SHORTAGE", "BREAKAGE"] as PrepEventType[]).includes(type) && (
          <label className="block space-y-1 text-body font-semibold"><span>Note (optional)</span>
            <textarea className={inputClass} value={note} maxLength={500} rows={2} onChange={(e) => setNote(e.target.value)} disabled={hasAttempt} /></label>
        )}
        {warning && <p role="alert" className="rounded-control bg-risk-atRisk-bg p-3 text-body text-risk-atRisk-fg">{warning}</p>}
        {result && <p role="status">{result}</p>}
        <p className="text-caption text-inkMuted">
          This writes a milestone only if the server validates scope, state and timing. Never assume success while processing.
        </p>
        <div className="flex flex-wrap gap-3">
          <button type="button" className={secondary} onClick={onClose} disabled={busy}>Cancel</button>
          {conflict ? (
            <button type="button" className={primary} disabled={busy} onClick={() => void onReload().catch(() => setWarning("Queue refresh failed. Try refreshing again."))}>
              Reload queue
            </button>
          ) : acknowledged ? (
            <button type="button" className={primary} disabled={busy} onClick={() => void onAcknowledged().then(onClose).catch(() => setWarning("Queue refresh failed. Try refreshing again."))}>
              Retry queue refresh
            </button>
          ) : (
            <button type="button" className={primary} onClick={() => void send()} disabled={busy}>
              {busy ? "Sending · awaiting CFO…" : hasAttempt ? "Retry same event" : `Confirm ${ACTION_NAMES[type]}`}
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
