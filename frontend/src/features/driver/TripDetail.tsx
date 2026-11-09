import { useRef, useState } from "react";
import { isApiError, newIdempotencyKey } from "../../api/client";
import { eventAllowed, getDriverTrip, sendDriverEvent, type DriverEvent, type DriverEventType, type DriverTrip } from "./driverApi";
import { enqueue } from "./offlineQueue";

const FAILURE_REASONS = [
  ["customer_absent", "Customer absent"], ["site_inaccessible", "Site inaccessible"],
  ["refused", "Delivery refused"], ["wrong_address", "Wrong address"],
  ["vehicle_breakdown", "Vehicle breakdown"], ["goods_damaged", "Goods damaged"], ["other", "Other"],
] as const;
const button = "min-h-12 w-full rounded-xl bg-[#E07B39] px-5 py-3 text-base font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50";

interface Props { trip: DriverTrip; driverUserId: number; online: boolean; mock: boolean; onBack: () => void; onUpdated: () => void; onSaved: () => void }
export function TripDetail({ trip, driverUserId, online, mock, onBack, onUpdated, onSaved }: Props) {
  const [outcome, setOutcome] = useState<"DELIVERED" | "FAILED">("DELIVERED");
  const [recipient, setRecipient] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const intent = useRef<{ fingerprint: string; key: string; occurredAt: string } | null>(null);
  const pendingStops = trip.stops.filter(stop => stop.status === "pending");
  const canDispatch = trip.status === "loading" && pendingStops.length === 1;
  const canFinish = trip.status === "on_road" && pendingStops.length === 1;
  const eventType: DriverEventType = canDispatch ? "DISPATCHED" : outcome;
  const valid = !mock && (canDispatch || canFinish) &&
    (eventType === "DISPATCHED" || (eventType === "DELIVERED" ? recipient.trim().length > 0 : reason.length > 0));

  async function confirm() {
    if (!valid || busy || pendingStops.length !== 1) return;
    const stop = pendingStops[0];
    const payload: Record<string, string | number> = { trip_id: trip.trip_id };
    if (eventType === "DELIVERED") payload.recipient_name = recipient.trim();
    if (eventType === "FAILED") payload.failure_reason = reason;
    if (note.trim() && eventType !== "DISPATCHED") payload.note = note.trim();
    const fingerprint = `${stop.order_id}:${eventType}:${JSON.stringify(payload)}`;
    if (intent.current?.fingerprint !== fingerprint) intent.current = { fingerprint, key: newIdempotencyKey(), occurredAt: new Date().toISOString() };
    const event: DriverEvent = { tripId: trip.trip_id, orderId: stop.order_id, eventType, payload,
      idempotencyKey: intent.current.key, occurredAt: intent.current.occurredAt };
    setBusy(true); setError(""); setMessage("");
    try {
      if (!online) {
        await enqueue({ ...event, driverUserId });
        setMessage("Saved on this device; not confirmed by the server. It will be checked again when online.");
        onSaved();
        return;
      }
      const fresh = await getDriverTrip(trip.trip_id, undefined, false);
      if (!eventAllowed(fresh, event)) { setError("Trip assignment or state changed. Refresh before retrying."); return; }
      const ack = await sendDriverEvent(event, false);
      if (!Number.isInteger(ack.event_id) || ack.event_id <= 0) { setError("Server acknowledgment is incomplete. Check the trip before retrying."); return; }
      setMessage(`Server confirmed ${eventType.toLowerCase()} event #${ack.event_id}.`);
      onUpdated();
    } catch (cause) {
      const code = isApiError(cause) ? cause.code : "STORAGE_OR_NETWORK_ERROR";
      setError(`${code}: update not confirmed. Retry with the same request or contact dispatch.`);
      if (isApiError(cause) && cause.status === 409) onUpdated();
    } finally { setBusy(false); }
  }

  return <section aria-label="Trip detail" className="mx-auto max-w-2xl space-y-5 px-4 pb-12 pt-5 text-base">
    <button className="min-h-12 text-[#0B2E2B] underline" onClick={onBack}>← Today&apos;s trips</button>
    <div className="rounded-2xl bg-[#0B2E2B] p-5 text-white">
      <p className="text-sm uppercase tracking-widest">Trip #{trip.trip_id} · {trip.status}</p>
      <h1 className="mt-2 text-2xl font-semibold">{trip.vehicle_code}</h1>
      <p>From {trip.warehouse_code} · planned {new Date(trip.depart_planned_at).toLocaleString()}</p>
    </div>
    {trip.stops.map((stop, index) => <article key={stop.trip_stop_id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-semibold uppercase tracking-wide text-slate-600">Stop {index + 1} · {stop.status}</p>
      <h2 className="mt-2 text-xl font-semibold">{stop.order_no}</h2>
      <address className="mt-2 not-italic">{stop.delivery_address ?? "Address unavailable — contact dispatch"}</address>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div><dt className="text-slate-500">Planned ETA</dt><dd>{new Date(stop.eta_planned_at).toLocaleString()}</dd></div>
        <div><dt className="text-slate-500">Receiving window</dt><dd>{stop.receiving_window.start ?? "Unknown"}–{stop.receiving_window.end ?? "Unknown"}</dd></div>
      </dl>
      {stop.special_requirements && <p className="mt-3 rounded-lg bg-amber-50 p-3">Receiving details: {stop.special_requirements}</p>}
      {stop.contact_name && <p className="mt-3">Contact: {stop.contact_name}{stop.contact_phone ? ` · ${stop.contact_phone}` : ""}</p>}
      <p className="mt-3 text-sm text-slate-600">POD for this stop is created by the server after a confirmed outcome.</p>
    </article>)}
    {pendingStops.length > 1 && <p role="alert" className="rounded-xl bg-amber-50 p-4">This trip has multiple pending stops. The current event contract cannot identify a stop; contact dispatch. No outcome can be submitted.</p>}
    {canFinish && <fieldset className="space-y-4 rounded-2xl border bg-white p-5">
      <legend className="font-semibold">Outcome for pending stop</legend>
      <div className="flex gap-4"><label><input type="radio" checked={outcome === "DELIVERED"} onChange={() => setOutcome("DELIVERED")} /> Delivered</label>
        <label><input type="radio" checked={outcome === "FAILED"} onChange={() => setOutcome("FAILED")} /> Failed</label></div>
      {outcome === "DELIVERED" ? <label className="block">Received by <input className="mt-1 min-h-12 w-full rounded-lg border p-3" value={recipient} onChange={e => setRecipient(e.target.value)} /></label>
        : <label className="block">Failure reason <select className="mt-1 min-h-12 w-full rounded-lg border p-3" value={reason} onChange={e => setReason(e.target.value)}>
          <option value="">Select a reason</option>{FAILURE_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>}
      <label className="block">Note (optional) <textarea className="mt-1 w-full rounded-lg border p-3" value={note} onChange={e => setNote(e.target.value)} /></label>
    </fieldset>}
    {(canDispatch || canFinish) && <button className={button} disabled={!valid || busy} onClick={() => void confirm()}>
      {busy ? "Checking…" : eventType === "DISPATCHED" ? "Mark dispatched" : `Confirm ${eventType.toLowerCase()}`}
    </button>}
    {mock && <p role="status" className="rounded-xl bg-amber-50 p-4">Synthetic contract preview. Delivery actions are disabled; no event is saved or sent.</p>}
    {error && <p role="alert" className="rounded-xl bg-red-50 p-4">{error}</p>}
    {message && <p role="status" className="rounded-xl bg-amber-50 p-4">{message}</p>}
  </section>;
}
