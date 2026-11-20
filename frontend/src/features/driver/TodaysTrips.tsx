/** Driver R3: on-demand location only. No GPS polling, offline queue or browser persistence. */
import { useCallback, useEffect, useRef, useState } from "react";
import { isApiError, newIdempotencyKey } from "../../api/client";
import { useAuthStore } from "../../app/store";
import {
  assignedTrips, submitDriverEvent, submitPosition,
  type DriverEvent, type DriverPosition, type DriverTrip,
} from "./driverApi";

const card = "rounded-card border border-border bg-surface p-5 shadow-card";
const primary = "min-h-12 w-full rounded-control bg-apricot px-4 py-3 text-body font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50";
const secondary = "min-h-12 rounded-control border border-border bg-surface px-4 py-3 text-body text-ink disabled:opacity-50";
const terminal = new Set(["completed", "cancelled", "failed"]);
const failureOptions = [
  ["customer_absent", "Customer absent"], ["site_inaccessible", "Site inaccessible"],
  ["refused", "Delivery refused"], ["wrong_address", "Wrong address"],
  ["vehicle_breakdown", "Vehicle breakdown"], ["goods_damaged", "Goods damaged"],
  ["other", "Other"],
] as const;
const incidentOptions = [
  ["vehicle_breakdown", "Vehicle breakdown"], ["traffic_or_accident", "Traffic or accident"],
  ["site_inaccessible", "Site inaccessible"], ["other", "Other"],
] as const;
type IncidentReason = (typeof incidentOptions)[number][0];
type EventRequest = { kind: "event"; key: string; userId: number; tripId: number; orderId: number; body: DriverEvent };
type PointRequest = { kind: "position"; key: string; userId: number; tripId: number; point: DriverPosition };
type PendingRequest = EventRequest | PointRequest;
type DriverAction = "DISPATCHED" | "DELIVERED" | "FAILED" | "DRIVER_INCIDENT" | "POSITION";

function timeLabel(value: string | undefined | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString(undefined, {
    dateStyle: "medium", timeStyle: "short",
  });
}

function failureMessage(error: unknown): string {
  if (!isApiError(error)) return "No verified server ACK. Retry uses exactly the same request.";
  if (error.status === 404) return "This trip is not assigned to your account.";
  if (error.status === 403) return "This operation is not permitted for your account.";
  if (error.status === 409) return `Trip conflict (${error.code}). Reload before a new operation.`;
  if (error.status === 422) return "The server rejected the submitted details.";
  return "No verified server ACK. Retry uses exactly the same request.";
}

/** Capture exactly one fresh fix. Browser timestamp is retained in the retry snapshot. */
function capturePosition(): Promise<DriverPosition> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation?.getCurrentPosition) {
      reject(new Error("Geolocation is unavailable. Enable location services and retry."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (fix) => {
        const { latitude, longitude, accuracy } = fix.coords;
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude) ||
            Math.abs(latitude) > 90 || Math.abs(longitude) > 180 ||
            !Number.isFinite(accuracy) || accuracy <= 0 || !Number.isFinite(fix.timestamp)) {
          reject(new Error("Location accuracy is invalid. Try again."));
          return;
        }
        resolve({ lat: latitude, lon: longitude, accuracy_m: accuracy, recorded_at: new Date(fix.timestamp).toISOString() });
      },
      () => reject(new Error("Location denied or timed out. Enable permission and try again.")),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 12000 },
    );
  });
}

export function TodaysTrips() {
  const user = useAuthStore((state) => state.user);
  const userId = user?.roles.includes("driver") ? user.id : null;
  const [trips, setTrips] = useState<DriverTrip[]>([]);
  const [tripOwner, setTripOwner] = useState<number | null>(null);
  const [selectedTrip, setSelectedTrip] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingRequest | null>(null);
  const pendingRef = useRef<PendingRequest | null>(null);
  const busyRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [acceptedPrivacy, setAcceptedPrivacy] = useState(false);
  const [lastAck, setLastAck] = useState<{ userId: number; tripId: number; recordedAt: string } | null>(null);
  const [outcome, setOutcome] = useState<"DELIVERED" | "FAILED">("DELIVERED");
  const [recipient, setRecipient] = useState("");
  const [failure, setFailure] = useState("");
  const [note, setNote] = useState("");
  const [incidentReason, setIncidentReason] = useState<IncidentReason>("traffic_or_accident");
  const [incidentNote, setIncidentNote] = useState("");

  const refreshTrips = useCallback(async () => {
    if (userId === null) { setTrips([]); setLoading(false); return; }
    setLoading(true);
    try {
      const items = await assignedTrips();
      if (useAuthStore.getState().user?.id === userId) {
        setTrips(items);
        setTripOwner(userId);
      }
    } catch (cause) {
      if (useAuthStore.getState().user?.id === userId) {
        setError(failureMessage(cause));
        setTrips([]);
      }
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    let active = true;
    // Do not carry a previous driver's position consent, ACK or retry snapshot into a new session.
    void Promise.resolve().then(() => {
      if (!active) return;
      pendingRef.current = null;
      setPending(null);
      setLastAck(null);
      setNotice(null);
      setAcceptedPrivacy(false);
      setSelectedTrip(null);
      void refreshTrips();
    });
    return () => { active = false; };
  }, [refreshTrips]);

  const safeTrips = tripOwner === userId ? trips : [];
  const trip = selectedTrip === null ? null : safeTrips.find((item) => item.trip_id === selectedTrip) ?? null;
  const stop = trip?.stops.length === 1 ? trip.stops[0] : null;
  const unconfirmed = pending !== null && pending.userId === userId;

  async function send(request: PendingRequest): Promise<void> {
    try {
      if (request.kind === "position") {
        const ack = await submitPosition(request.tripId, request.point, request.key);
        if (ack.accepted !== 1 || ack.trip_id !== request.tripId ||
            !Number.isFinite(Date.parse(ack.recorded_at)) ||
            Date.parse(ack.recorded_at) !== Date.parse(request.point.recorded_at)) {
          throw new Error("Unverified GPS acknowledgment");
        }
        if (useAuthStore.getState().user?.id !== request.userId || pendingRef.current?.key !== request.key) return;
        setLastAck({ userId: request.userId, tripId: request.tripId, recordedAt: request.point.recorded_at });
        setNotice(`Position sent · ${timeLabel(request.point.recorded_at)}`);
      } else {
        const ack = await submitDriverEvent(request.orderId, request.body, request.key);
        if (!Number.isSafeInteger(ack.event_id) || ack.event_id <= 0) {
          throw new Error("Unverified event acknowledgment");
        }
        if (useAuthStore.getState().user?.id !== request.userId || pendingRef.current?.key !== request.key) return;
        setNotice(`${request.body.event_type.replaceAll("_", " ")} acknowledged by CFO.`);
      }
      pendingRef.current = null;
      setPending(null);
      setError(null);
      void refreshTrips();
    } catch (cause) {
      if (useAuthStore.getState().user?.id !== request.userId || pendingRef.current?.key !== request.key) return;
      setError(failureMessage(cause));
      if (isApiError(cause) && [400, 401, 403, 404, 409, 422].includes(cause.status ?? -1)) {
        // A definitive rejected request is not retried. Unknown network/server outcome is retained.
        pendingRef.current = null;
        setPending(null);
      }
    }
  }

  async function retryPending(): Promise<void> {
    const request = pendingRef.current;
    if (busyRef.current || !request || userId === null || request.userId !== userId) return;
    busyRef.current = true;
    setBusy(true);
    try { await send(request); }
    finally { busyRef.current = false; setBusy(false); }
  }

  async function act(action: DriverAction): Promise<void> {
    if (busyRef.current || pendingRef.current !== null || !trip || !stop || userId === null ||
        !safeTrips.some((item) => item.trip_id === trip.trip_id)) return;
    if (action === "DISPATCHED" ? trip.status !== "loading" : trip.status !== "on_road") return;
    if (action !== "DISPATCHED" && !acceptedPrivacy) {
      setError("Read and acknowledge the location privacy notice before continuing.");
      return;
    }
    if (action === "DELIVERED" && !recipient.trim()) { setError("Recipient name is required."); return; }
    if (action === "FAILED" && !failure) { setError("Select a failure reason."); return; }
    if (action === "DRIVER_INCIDENT" && incidentReason === "other" && !incidentNote.trim()) {
      setError("Please describe the incident when choosing Other.");
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      let point: DriverPosition | undefined;
      if (action !== "DISPATCHED") {
        try { point = await capturePosition(); }
        catch (cause) {
          if (action !== "DRIVER_INCIDENT") {
            setError(cause instanceof Error ? cause.message : "Location required. Try again.");
            return;
          }
          // Incident reporting is allowed without a location fix.
        }
      }
      // The user may have signed out while the browser permission prompt was open.
      if (useAuthStore.getState().user?.id !== userId) return;
      const key = newIdempotencyKey();
      let request: PendingRequest;
      if (action === "POSITION") {
        if (!point) return;
        request = { kind: "position", tripId: trip.trip_id, key, userId, point };
      } else {
        const occurred_at = new Date().toISOString();
        let body: DriverEvent;
        if (action === "DISPATCHED") {
          body = { event_type: action, occurred_at, payload: { trip_id: trip.trip_id } };
        } else if (action === "DELIVERED" && point) {
          body = { event_type: action, occurred_at, payload: { trip_id: trip.trip_id, recipient_name: recipient.trim(), position: point } };
        } else if (action === "FAILED" && point) {
          body = { event_type: action, occurred_at, payload: { trip_id: trip.trip_id, failure_reason: failure, position: point, ...(note.trim() ? { note: note.trim() } : {}) } };
        } else if (action === "DRIVER_INCIDENT") {
          body = { event_type: action, occurred_at, payload: { trip_id: trip.trip_id, reason: incidentReason,
            ...(incidentNote.trim() ? { note: incidentNote.trim() } : {}), ...(point ? { position: point } : {}) } };
        } else return; // A terminal action cannot proceed without a fresh position.
        request = { kind: "event", tripId: trip.trip_id, orderId: stop.order_id, key, userId, body };
      }
      pendingRef.current = request;
      setPending(request);
      await send(request);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  if (userId === null) {
    return <main data-screen="TodaysTrips" role="alert" className="p-5">Driver authorization required. No trip information is available.</main>;
  }

  return (
    <main data-screen="TodaysTrips" className="min-h-screen bg-stone pb-12 text-ink">
      <header className="rounded-b-card bg-deepPine px-5 pb-8 pt-7 text-white">
        <div className="mx-auto max-w-lg">
          <p className="text-caption uppercase tracking-wide text-white/80">Driver PWA</p>
          <h1 className="text-h2 font-semibold">Today&apos;s trips</h1>
          <p className="text-body text-white/80">Only trips assigned to your driver account</p>
        </div>
      </header>
      <div className="mx-auto -mt-4 flex max-w-lg flex-col gap-4 px-4">
        {error && <div role="alert" className={card}>{error}</div>}
        {notice && <p role="status" className={card}>{notice}</p>}
        {unconfirmed && <div className={card} role="alert">
          <p>No verified server ACK. The original request and Idempotency-Key are retained in this screen only.</p>
          <button type="button" className={secondary} disabled={busy} onClick={() => void retryPending()}>Retry same request</button>
        </div>}
        <div className={card}>
          <button type="button" className={secondary} disabled={busy} onClick={() => void refreshTrips()}>Refresh trips</button>
        </div>
        {loading && safeTrips.length === 0 && <div role="status" className={card}>Loading assigned trips…</div>}
        {!loading && safeTrips.length === 0 && <div className={card}>No assigned trips for today.</div>}
        {trip ? (
          <section aria-label="Trip details" className={card}>
            <button type="button" className={secondary} disabled={busy} onClick={() => setSelectedTrip(null)}>Back to trips</button>
            <h2 className="mt-4 text-h3 font-semibold">Trip {trip.trip_id} · {trip.vehicle_code}</h2>
            <p className="text-body">{trip.status === "on_road" ? "On the road" : trip.status}</p>
            <p className="text-caption text-inkMuted">Departure: {timeLabel(trip.depart_actual_at ?? trip.depart_planned_at)}</p>
            {trip.stops.map((item) => <div className="mt-4 rounded-control border p-3" key={item.trip_stop_id}>
              <p className="font-semibold">{item.order_no} · Stop {item.trip_stop_id}</p>
              <p className="text-body">{item.delivery_address}</p>
              <p className="text-caption">ETA: {timeLabel(item.eta_planned_at)}</p>
            </div>)}
            {!stop && <p role="alert">Multi-stop events require an explicit stop selection; actions disabled.</p>}
            {stop && trip.status === "loading" && <button className={primary} type="button" disabled={busy || unconfirmed}
              onClick={() => void act("DISPATCHED")}>Mark dispatched</button>}
            {stop && trip.status === "on_road" && <>
              <section className="mt-4 space-y-3 rounded-control border border-border p-3" aria-label="Location privacy notice">
                <h3 className="font-semibold">Your location, your action</h3>
                <p>Only when you tap an action will CFO request one GPS fix. The assigned Dispatcher may see the latest position, update time and ETA while this trip is on the road. No periodic tracking or offline GPS storage. Real-worker location collection requires approved notice and legal clearance.</p>
                <label className="flex items-center gap-2"><input type="checkbox" checked={acceptedPrivacy}
                  onChange={(e) => setAcceptedPrivacy(e.target.checked)} /> I have read the location privacy notice.</label>
              </section>
              <div className="mt-4 space-y-3">
                <button type="button" className={primary} disabled={busy || unconfirmed || !acceptedPrivacy}
                  onClick={() => void act("POSITION")}>Update location</button>
                {lastAck?.userId === userId && lastAck.tripId === trip.trip_id &&
                  <p role="status">Last position sent: {timeLabel(lastAck.recordedAt)}</p>}
                <fieldset className="space-y-3 rounded-control border border-border p-3">
                  <legend className="font-semibold">Report incident</legend>
                  <label className="block">Incident reason
                    <select value={incidentReason} onChange={(e) => setIncidentReason(e.target.value as IncidentReason)}
                      className="mt-1 w-full rounded-control border p-2">
                      {incidentOptions.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
                    </select>
                  </label>
                  <label className="block">Incident note {incidentReason === "other" ? "(required)" : "(optional)"}
                    <textarea value={incidentNote} onChange={(e) => setIncidentNote(e.target.value)} maxLength={500}
                      className="mt-1 w-full rounded-control border p-2" />
                  </label>
                  <button type="button" className={secondary}
                    disabled={busy || unconfirmed || !acceptedPrivacy || (incidentReason === "other" && !incidentNote.trim())}
                    onClick={() => void act("DRIVER_INCIDENT")}>Report incident</button>
                  <p className="text-caption">An incident can be sent even when a location fix is unavailable.</p>
                </fieldset>
                <fieldset className="space-y-3 rounded-control border border-border p-3">
                  <legend className="font-semibold">Delivery outcome</legend>
                  <label className="flex items-center gap-2"><input type="radio" checked={outcome === "DELIVERED"}
                    onChange={() => setOutcome("DELIVERED")} /> Delivered</label>
                  <label className="flex items-center gap-2"><input type="radio" checked={outcome === "FAILED"}
                    onChange={() => setOutcome("FAILED")} /> Failed</label>
                  {outcome === "DELIVERED" ? <label className="block">Received by
                    <input value={recipient} onChange={(e) => setRecipient(e.target.value)} maxLength={150}
                      className="mt-1 w-full rounded-control border p-2" />
                  </label> : <>
                    <label className="block">Failure reason
                      <select value={failure} onChange={(e) => setFailure(e.target.value)}
                        className="mt-1 w-full rounded-control border p-2">
                        <option value="">Select a reason</option>
                        {failureOptions.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
                      </select>
                    </label>
                    <label className="block">Note (optional)
                      <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500}
                        className="mt-1 w-full rounded-control border p-2" />
                    </label>
                  </>}
                  <button type="button" className={primary}
                    disabled={busy || unconfirmed || !acceptedPrivacy || (outcome === "DELIVERED" ? !recipient.trim() : !failure)}
                    onClick={() => void act(outcome)}>
                    {outcome === "DELIVERED" ? "Confirm delivered" : "Confirm failed"}
                  </button>
                  <p className="text-caption">A new GPS fix is required for each completion. Permission denial or timeout stops completion.</p>
                </fieldset>
              </div>
            </>}
            {terminal.has(trip.status) && <p>Trip ended. No further updates or location sharing are permitted.</p>}
          </section>
        ) : (
          <section aria-label="Assigned trips" className="space-y-3">
            {safeTrips.map((item) => <article className={card} key={item.trip_id}>
              <h2 className="font-semibold">Trip {item.trip_id} · {item.vehicle_code}</h2>
              <p>{item.status} · {item.stops.length} stop(s)</p>
              {item.stops.map((s) => <p key={s.trip_stop_id}>{s.order_no} · {s.delivery_address}</p>)}
              <button type="button" className={primary} onClick={() => setSelectedTrip(item.trip_id)}>
                {item.status === "loading" ? "Review and dispatch" : item.status === "on_road" ? "Record delivery outcome" : "View trip"}
              </button>
            </article>)}
          </section>
        )}
      </div>
    </main>
  );
}
