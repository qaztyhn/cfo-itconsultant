/** Warehouse execution confirmation. No local transition is displayed as complete until event_id ACK. */
import { useRef, useState } from "react";
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
  choice, warehouseId, reportDate, onClose, onAcknowledged,
}: {
  choice: ActionChoice;
  warehouseId: number;
  reportDate: string;
  onClose: () => void;
  onAcknowledged: () => Promise<unknown>;
}) {
  const [clockValue, setClockValue] = useState(nowLocal);
  const [crew, setCrew] = useState("1");
  const [sku, setSku] = useState("");
  const [qty, setQty] = useState("1");
  const [vehicleId, setVehicleId] = useState("");
  const [date, setDate] = useState(reportDate);
  const [staffPresent, setStaffPresent] = useState("0");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [hasAttempt, setHasAttempt] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const attempt = useRef<PreparedEvent | null>(null);
  const { order, type, tripId } = choice;

  const requiresCrew = type === "START_PREP" || type === "PREP_RESUMED";
  const skuReport = type === "SHORTAGE" || type === "BREAKAGE";

  function fields(): EventPayload {
    switch (type) {
      case "START_PREP":
      case "PREP_RESUMED": return { crew_size: Number(crew) };
      case "LOADED": return { trip_id: tripId ?? 0 };
      case "SHORTAGE": return { sku: sku.trim(), qty_missing: Number(qty), ...(note.trim() ? { note: note.trim() } : {}) };
      case "BREAKAGE": return { sku: sku.trim(), qty: Number(qty), ...(note.trim() ? { note: note.trim() } : {}) };
      case "VEHICLE_ISSUE": return { vehicle_id: Number(vehicleId), ...(note.trim() ? { note: note.trim() } : {}) };
      case "SHIFT_CHANGE": return { date, staff_present: Number(staffPresent), ...(note.trim() ? { note: note.trim() } : {}) };
      case "PREP_PAUSED": return note.trim() ? { note: note.trim() } : {};
      default: return {};
    }
  }

  async function send(): Promise<void> {
    if (busy) return;
    setWarning(null);
    setResult(null);
    if (!canPerform(order, type, tripId)) {
      setWarning("This action is not available for the current order status. Refresh the queue.");
      return;
    }
    let prepared: PreparedEvent;
    try {
      const draft = eventDraft(order.order_id, type, localOccurredAt(clockValue), fields());
      prepared = prepareEvent(draft, attempt.current);
      attempt.current = prepared;
      setHasAttempt(true);
    } catch (cause) {
      setWarning(cause instanceof Error ? cause.message : "Check the event fields.");
      return;
    }
    setBusy(true);
    try {
      const ack = await submitPrepEvent(prepared);
      setResult(`CFO recorded event #${ack.event_id} for order ${order.order_no}.`);
      attempt.current = null;
      setHasAttempt(false);
      // A refresh failure never reverses an already acknowledged server write.
      try {
        await onAcknowledged();
      } catch {
        // The caller already displayed the authoritative ACK. Re-fetch on the next poll.
      }
      onClose();
    } catch (cause) {
      setWarning(safeActionError(cause));
      // Preserve the original idempotency key, occurred_at and body for identical retry.
    } finally {
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
        {type === "SHIFT_CHANGE" && <p className="text-caption text-inkMuted">
          This reports a shift exception for review. It does not change the official manager-approved shift or capacity.
        </p>}
        {type === "VEHICLE_ISSUE" && <p className="text-caption text-inkMuted">
          Enter the numeric ID of a vehicle assigned to this order. The server validates it. No vehicle status is changed here.
        </p>}
        <label className="block space-y-1 text-body font-semibold">
          <span>Occurred at (device local time)</span>
          <input className={inputClass} type="datetime-local" value={clockValue}
            onChange={(e) => setClockValue(e.target.value)} required />
        </label>
        {requiresCrew && (
          <label className="block space-y-1 text-body font-semibold">
            <span>Crew size (people actually working)</span>
            <input className={inputClass} type="number" min="1" step="1" value={crew} onChange={(e) => setCrew(e.target.value)} />
          </label>
        )}
        {skuReport && (
          <>
            <label className="block space-y-1 text-body font-semibold"><span>Local SKU</span>
              <input className={inputClass} value={sku} maxLength={120} onChange={(e) => setSku(e.target.value)} /></label>
            <label className="block space-y-1 text-body font-semibold">
              <span>{type === "SHORTAGE" ? "Quantity missing" : "Quantity damaged"} (whole units)</span>
              <input className={inputClass} type="number" min="1" step="1" value={qty} onChange={(e) => setQty(e.target.value)} />
            </label>
          </>
        )}
        {type === "VEHICLE_ISSUE" && <label className="block space-y-1 text-body font-semibold">
          <span>Assigned vehicle ID</span>
          <input className={inputClass} type="number" min="1" step="1" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} />
        </label>}
        {type === "SHIFT_CHANGE" && (
          <>
            <label className="block space-y-1 text-body font-semibold"><span>Official shift date</span>
              <input className={inputClass} type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
            <label className="block space-y-1 text-body font-semibold"><span>Staff present (observed, not a schedule edit)</span>
              <input className={inputClass} type="number" min="0" step="1" value={staffPresent} onChange={(e) => setStaffPresent(e.target.value)} /></label>
          </>
        )}
        {(["PREP_PAUSED", "SHORTAGE", "BREAKAGE", "VEHICLE_ISSUE", "SHIFT_CHANGE"] as PrepEventType[]).includes(type) && (
          <label className="block space-y-1 text-body font-semibold"><span>Note (optional)</span>
            <textarea className={inputClass} value={note} maxLength={500} rows={2} onChange={(e) => setNote(e.target.value)} /></label>
        )}
        {warning && <p role="alert" className="rounded-control bg-risk-atRisk-bg p-3 text-body text-risk-atRisk-fg">{warning}</p>}
        {result && <p role="status">{result}</p>}
        <p className="text-caption text-inkMuted">
          This writes a milestone only if the server validates scope, state and timing. Never assume success while processing.
        </p>
        <div className="flex flex-wrap gap-3">
          <button type="button" className={secondary} onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className={primary} onClick={() => void send()} disabled={busy}>
            {busy ? "Sending · awaiting CFO…" : hasAttempt ? "Retry / confirm same event" : `Confirm ${ACTION_NAMES[type]}`}
          </button>
        </div>
      </section>
    </div>
  );
}
