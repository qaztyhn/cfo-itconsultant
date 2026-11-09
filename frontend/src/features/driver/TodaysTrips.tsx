/** Driver PWA · docs/03 §5.10, docs/06 §8, GPS retention/privacy decisions.
 * Only authenticated driver's server-assigned trips are shown. Offline events
 * are PENDING until acknowledged by the execution API; no GPS is collected.
 */
import { useCallback, useEffect, useState } from "react";
import { isApiError, newIdempotencyKey } from "../../api/client";
import { useAuthStore } from "../../app/store";
import { assignedTrips, type DriverStop, type DriverTrip, type DriverEventType } from "./driverApi";
import { discardEvent, enqueueEvent, pendingForUser, replayEvents, type PendingEvent } from "./offlineEvents";

const card = "rounded-card border border-border bg-surface p-5 shadow-card";
const primary = "min-h-12 w-full rounded-control bg-apricot px-4 py-3 text-body font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50";
const secondary = "min-h-12 rounded-control border border-border bg-surface px-4 py-3 text-body font-semibold text-ink disabled:opacity-50";
const terminal = new Set(["completed", "cancelled", "failed"]);

const failureOptions = [
  { code: "customer_absent", label: "Customer absent" },
  { code: "site_inaccessible", label: "Site inaccessible" },
  { code: "refused", label: "Delivery refused" },
  { code: "wrong_address", label: "Wrong address" },
  { code: "vehicle_breakdown", label: "Vehicle breakdown" },
  { code: "goods_damaged", label: "Goods damaged" },
  { code: "other", label: "Other" },
];

function timeLabel(value: string | null | undefined): string {
  if (!value) return "Not available";
  const time = new Date(value);
  return Number.isNaN(time.getTime())
    ? "Not available"
    : time.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function safeApiMessage(error: unknown): string {
  if (!isApiError(error)) return "Could not verify the latest trip status.";
  if (error.status === 403) return "Your driver account is not authorized for this action.";
  if (error.status === 404) return "The trip is no longer assigned to you.";
  if (error.status === 409) return "This trip changed or the event conflicts. Review it before retrying.";
  if (error.status === 422) return "The server rejected the event details.";
  if (error.status === 503 || error.status === 0) return "Service unavailable. No event was confirmed.";
  return `The request could not be verified (reference ${error.correlationId ?? "unavailable"}).`;
}

function labelForTrip(status: string): string {
  const labels: Record<string, string> = {
    planned: "Awaiting preparation",
    loading: "Loaded — awaiting dispatch",
    on_road: "On the road",
    completed: "Completed",
    cancelled: "Cancelled",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function detailAction(trip: DriverTrip): "DISPATCHED" | "POD" | null {
  // A trip is exclusively one order: never guess which order to dispatch.
  const orderIds = new Set(trip.stops.map((stop) => stop.order_id));
  if (trip.stops.length === 0 || orderIds.size !== 1) return null;
  if (trip.status === "loading") return "DISPATCHED";
  if (trip.status === "on_road" && trip.stops.some((stop) => stop.status === "pending")) return "POD";
  return null;
}

export function TodaysTrips() {
  const user = useAuthStore((state) => state.user);
  const authenticatedDriver = user?.roles.includes("driver") ?? false;
  const userId = authenticatedDriver ? user?.id ?? null : null;

  const [trips, setTrips] = useState<DriverTrip[]>([]);
  const [tripOwner, setTripOwner] = useState<number | null>(null);
  const [selectedTrip, setSelectedTrip] = useState<number | null>(null);
  const [selectedStop, setSelectedStop] = useState<number | null>(null);
  const [pending, setPending] = useState<PendingEvent[]>([]);
  const [online, setOnline] = useState(() => typeof navigator === "undefined" || navigator.onLine);
  const [permission, setPermission] = useState(() => "permissions" in navigator ? "not requested" : "unavailable");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<"DELIVERED" | "FAILED">("DELIVERED");
  const [recipient, setRecipient] = useState("");
  const [failure, setFailure] = useState("");
  const [note, setNote] = useState("");
  const [privacyOpen, setPrivacyOpen] = useState(false);

  const refreshPending = useCallback(async () => {
    if (userId === null) { setPending([]); return; }
    try {
      const items = await pendingForUser(userId);
      if (useAuthStore.getState().user?.id === userId) setPending(items);
    }
    catch { setError("Secure offline storage is unavailable. Updates cannot be queued."); }
  }, [userId]);

  const refreshTrips = useCallback(async () => {
    if (userId === null) { setTrips([]); setLoading(false); return; }
    setLoading(true);
    try {
      const items = await assignedTrips();
      if (useAuthStore.getState().user?.id !== userId) return;
      setTripOwner(userId);
      setTrips(items);
      setError(null);
    } catch (cause) {
      if (useAuthStore.getState().user?.id !== userId) return;
      setError(safeApiMessage(cause));
      // Never show previous user's trips after an authorization failure.
      if (isApiError(cause) && [401, 403, 404].includes(cause.status ?? 0)) setTrips([]);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  const retryPending = useCallback(async () => {
    if (userId === null || !online) return;
    setBusy(true);
    try {
      const result = await replayEvents(userId);
      await refreshPending();
      if (result.sent) {
        setNotice(`${result.sent} update${result.sent === 1 ? "" : "s"} acknowledged by CFO.`);
        await refreshTrips();
      } else if (result.conflict) {
        setNotice("An update needs review. It has not been recorded as delivered.");
      }
    } catch {
      setError("Offline replay could not be verified. Events remain pending.");
    } finally {
      setBusy(false);
    }
  }, [online, refreshPending, refreshTrips, userId]);

  useEffect(() => {
    let active = true;
    // Schedule state-changing refresh after effect setup (React compiler lint rule).
    void Promise.resolve().then(() => {
      if (!active) return;
      if (userId === null) { setTrips([]); setTripOwner(null); setPending([]); setSelectedTrip(null); return; }
      void refreshTrips();
      void refreshPending();
    });
    return () => { active = false; };
  }, [userId, refreshTrips, refreshPending]);

  useEffect(() => {
    const updateOnline = () => setOnline(navigator.onLine);
    window.addEventListener("online", updateOnline);
    window.addEventListener("offline", updateOnline);
    return () => {
      window.removeEventListener("online", updateOnline);
      window.removeEventListener("offline", updateOnline);
    };
  }, []);

  useEffect(() => {
    if (online && userId !== null && pending.some((item) => item.state === "pending")) {
      void Promise.resolve().then(() => retryPending());
    }
    // Deliberately do not loop on changes in the pending list; only on re-connection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online, userId]);

  useEffect(() => {
    if (!navigator.permissions?.query) return;
    let active = true;
    let status: PermissionStatus | null = null;
    void navigator.permissions.query({ name: "geolocation" }).then((result) => {
      if (!active) return;
      status = result;
      setPermission(result.state);
      result.onchange = () => { if (active) setPermission(result.state); };
    }).catch(() => { if (active) setPermission("unavailable"); });
    return () => { active = false; if (status) status.onchange = null; };
  }, []);

  const safeTrips = tripOwner === userId ? trips : [];
  const safePending = pending.filter((event) => event.userId === userId);
  const activeTrip = selectedTrip === null ? null : safeTrips.find((trip) => trip.trip_id === selectedTrip) ?? null;
  const pendingForTrip = activeTrip
    ? safePending.some((event) => event.tripId === activeTrip.trip_id)
    : false;
  const pendingStops = activeTrip?.stops.filter((stop) => stop.status === "pending") ?? [];
  const currentStop = pendingStops.find((stop) => stop.trip_stop_id === selectedStop) ?? null;

  async function record(
    trip: DriverTrip,
    stop: DriverStop,
    type: DriverEventType,
  ): Promise<void> {
    if (userId === null || busy || safePending.some((item) => item.tripId === trip.trip_id)) return;
    if (!trip.stops.some((item) => item.trip_stop_id === stop.trip_stop_id && item.order_id === stop.order_id)) return;
    const action = detailAction(trip);
    if ((type === "DISPATCHED" && action !== "DISPATCHED") ||
        (type !== "DISPATCHED" && (action !== "POD" || stop.status !== "pending" ||
          stop.trip_stop_id !== selectedStop))) return;
    if (type === "DELIVERED" && !recipient.trim()) { setError("Recipient name is required for delivery proof."); return; }
    if (type === "FAILED" && !failure) { setError("Select a failure reason."); return; }
    const payload = type === "DISPATCHED"
      ? { trip_id: trip.trip_id }
      : type === "DELIVERED"
        ? { trip_id: trip.trip_id, trip_stop_id: stop.trip_stop_id, recipient_name: recipient.trim(),
            ...(note.trim() ? { note: note.trim() } : {}) }
        : { trip_id: trip.trip_id, trip_stop_id: stop.trip_stop_id, failure_reason: failure,
            ...(note.trim() ? { note: note.trim() } : {}) };
    const event: PendingEvent = {
      key: newIdempotencyKey(),
      userId,
      tripId: trip.trip_id,
      stopId: stop.trip_stop_id,
      orderId: stop.order_id,
      event: { event_type: type, occurred_at: new Date().toISOString(), payload },
      state: "pending",
    };
    setBusy(true);
    setError(null);
    try {
      await enqueueEvent(event);
      await refreshPending();
      setSelectedStop(null);
      setRecipient("");
      setFailure("");
      setNote("");
      setNotice("Update stored on this device. Not yet confirmed by CFO.");
    } catch {
      setError("The event could not be stored safely. Nothing was submitted.");
      setBusy(false);
      return;
    }
    setBusy(false);
    if (online) await retryPending();
  }

  if (!authenticatedDriver || userId === null) {
    return <main data-screen="TodaysTrips" className="mx-auto max-w-lg p-5" role="alert">Driver authorization required. No trip information is available.</main>;
  }

  return (
    <main data-screen="TodaysTrips" className="min-h-screen bg-stone pb-12 text-ink">
      <header className="rounded-b-card bg-deepPine px-5 pb-8 pt-7 text-white">
        <div className="mx-auto flex max-w-lg items-center justify-between gap-3">
          <div>
            <p className="text-caption uppercase tracking-wide text-white/80">Driver PWA</p>
            <h1 className="text-h2 font-semibold">Today&apos;s trips</h1>
            <p className="text-body text-white/80">Only trips assigned to your driver account</p>
          </div>
          <span className="rounded-control border border-white/40 px-3 py-2 font-mono text-caption">
            {activeTrip?.vehicle_code ?? safeTrips[0]?.vehicle_code ?? "No vehicle"}
          </span>
        </div>
      </header>

      <div className="mx-auto -mt-4 flex max-w-lg flex-col gap-4 px-4">
        <div className={card} aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="font-semibold">{online ? "Online" : "Offline · updates not sent"}</span>
            <span className="text-caption">{safePending.length} update{safePending.length === 1 ? "" : "s"} pending / needing review</span>
          </div>
          <p className="mt-2 text-caption text-inkMuted">
            An update is confirmed only after CFO acknowledges it. The local outbox is not proof of delivery.
          </p>
          <div className="mt-3 flex gap-2">
            <button type="button" className={secondary} onClick={() => void refreshTrips()} disabled={!online || busy}>Refresh trips</button>
            <button type="button" className={secondary} onClick={() => void retryPending()} disabled={!online || busy || !safePending.some((item) => item.state === "pending")}>Retry pending</button>
          </div>
        </div>
        {notice && <p role="status" className="rounded-control bg-surface p-3 text-body">{notice}</p>}
        {error && <div role="alert" className={card}><p>{error}</p><button type="button" className={secondary} onClick={() => { setError(null); void refreshTrips(); }}>Retry load</button></div>}

        {safePending.filter((item) => item.state === "conflict").map((item) => (
          <div className={card} role="alert" key={item.key}>
            <p className="font-semibold">Update needs manual review</p>
            <p className="text-body">Order {item.orderId} · {item.errorCode ?? "CONFLICT"}. It has not been confirmed.</p>
            <p className="text-caption text-inkMuted">Contact Dispatcher before discarding; do not record a second POD.</p>
            <button className={secondary} type="button" disabled={busy} onClick={() => {
              void discardEvent(userId, item.key).then(() => refreshPending()).catch(() => setError("Could not discard update."));
            }}>Discard local update</button>
          </div>
        ))}

        {loading && safeTrips.length === 0 ? <div className={card} role="status">Loading assigned trips…</div> : null}
        {!loading && safeTrips.length === 0 && !error ? <div className={card}>No assigned trips for today.</div> : null}
        {activeTrip ? (
          <section className={card} aria-label="Trip details">
            <button type="button" className={secondary} onClick={() => {
              setSelectedTrip(null); setSelectedStop(null); setOutcome("DELIVERED");
            }}>Back to trips</button>
            <div className="mt-4 flex items-center justify-between gap-2">
              <h2 className="text-h3 font-semibold">Trip {activeTrip.trip_id} · {activeTrip.vehicle_code}</h2>
              <span className="text-caption">{labelForTrip(activeTrip.status)}</span>
            </div>
            <p className="mt-2 text-caption text-inkMuted">Departure: {timeLabel(activeTrip.depart_actual_at ?? activeTrip.depart_planned_at)}</p>
            {activeTrip.stops.map((stop) => (
              <div key={stop.trip_stop_id} className="mt-4 rounded-control border border-border p-4">
                <p className="font-semibold">{stop.order_no} · Stop {stop.trip_stop_id}</p>
                <p className="text-body">{stop.delivery_address}</p>
                <p className="text-caption text-inkMuted">Receiving: {stop.receiving_window.start ?? "—"}–{stop.receiving_window.end ?? "—"}</p>
                <p className="text-caption text-inkMuted">ETA: {timeLabel(stop.eta_planned_at)}</p>
                <p className="text-caption">Stop status: {stop.status}</p>
              </div>
            ))}
            {activeTrip.stops.length > 0 && new Set(activeTrip.stops.map((stop) => stop.order_id)).size > 1 && (
              <p role="alert" className="mt-3 text-body">
                This trip references multiple orders and cannot be verified. Contact Dispatcher.
              </p>
            )}
            {detailAction(activeTrip) === "DISPATCHED" && (
              <button type="button" className={`${primary} mt-4`} disabled={busy || pendingForTrip}
                onClick={() => void record(activeTrip, activeTrip.stops[0], "DISPATCHED")}>Mark dispatched</button>
            )}
            {detailAction(activeTrip) === "POD" && (
              <div className="mt-4 space-y-3">
                <h3 className="font-semibold">Choose the delivery stop</h3>
                <p className="text-caption text-inkMuted">
                  Each stop needs its own proof of delivery. Choose the correct stop before recording an outcome.
                </p>
                {pendingStops.map((stop) => (
                  <button key={stop.trip_stop_id} type="button"
                    className={`${secondary} w-full text-left ${selectedStop === stop.trip_stop_id ? "border-pine" : ""}`}
                    aria-pressed={selectedStop === stop.trip_stop_id}
                    disabled={busy || pendingForTrip}
                    onClick={() => { setSelectedStop(stop.trip_stop_id); setRecipient(""); setFailure(""); setNote(""); }}>
                    Select stop {stop.trip_stop_id} · {stop.order_no}
                  </button>
                ))}
              </div>
            )}
            {detailAction(activeTrip) === "POD" && currentStop && (
              <div className="mt-4 space-y-4">
                <fieldset>
                  <legend className="font-semibold">Delivery outcome</legend>
                  <div className="flex gap-4">
                    <label className="flex min-h-12 items-center gap-2"><input type="radio" checked={outcome === "DELIVERED"} onChange={() => setOutcome("DELIVERED")} /> Delivered</label>
                    <label className="flex min-h-12 items-center gap-2"><input type="radio" checked={outcome === "FAILED"} onChange={() => setOutcome("FAILED")} /> Failed</label>
                  </div>
                </fieldset>
                {outcome === "DELIVERED" ? (
                  <label className="block font-semibold">Received by
                    <input className="mt-1 min-h-12 w-full rounded-control border border-border p-3 font-normal" autoComplete="off"
                      value={recipient} onChange={(e) => setRecipient(e.target.value)} maxLength={150} />
                  </label>
                ) : (
                  <label className="block font-semibold">Failure reason
                    <select className="mt-1 min-h-12 w-full rounded-control border border-border p-3 font-normal"
                      value={failure} onChange={(e) => setFailure(e.target.value)}>
                      <option value="">Select a reason</option>
                      {failureOptions.map((entry) => <option key={entry.code} value={entry.code}>{entry.label}</option>)}
                    </select>
                  </label>
                )}
                <label className="block font-semibold">Note (optional)
                  <textarea className="mt-1 min-h-12 w-full rounded-control border border-border p-3 font-normal"
                    value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={2} />
                </label>
                <button type="button" className={primary} disabled={busy || pendingForTrip || (outcome === "DELIVERED" ? !recipient.trim() : !failure)}
                  onClick={() => void record(activeTrip, currentStop, outcome)}>
                  {outcome === "DELIVERED" ? "Confirm delivered" : "Confirm failed"}
                </button>
              </div>
            )}
            <p className="mt-3 text-caption text-inkMuted">
              Driver duty and licence eligibility are checked by CFO on every event; no verified shift
              window is available in this trip response. Do not infer availability from a trip card.
            </p>
            {pendingForTrip && <p role="status" className="mt-3 text-body">An update for this trip is awaiting acknowledgment. New actions are paused.</p>}
            {terminal.has(activeTrip.status) && <p className="mt-3 text-body">Trip ended. No further updates or location sharing are permitted.</p>}
          </section>
        ) : (
          <section aria-label="Assigned trips" className="flex flex-col gap-4">
            {safeTrips.map((trip, index) => (
              <article className={card} key={trip.trip_id}>
                <p className="text-caption font-semibold uppercase">{index === 0 ? "Now" : "Later"} · Trip {trip.trip_id}</p>
                <h2 className="mt-1 text-h3 font-semibold">{trip.vehicle_code}</h2>
                <p className="text-body">{labelForTrip(trip.status)} · {trip.stops.length} stop{trip.stops.length === 1 ? "" : "s"}</p>
                <p className="text-caption text-inkMuted">Depart: {timeLabel(trip.depart_actual_at ?? trip.depart_planned_at)}</p>
                {trip.stops.map((stop) => <p key={stop.trip_stop_id} className="mt-2 text-body">{stop.order_no} · {stop.delivery_address}</p>)}
                <button type="button" className={`${primary} mt-4`} onClick={() => { setSelectedTrip(trip.trip_id); setSelectedStop(null); }}>
                  {trip.status === "loading" ? "Review and dispatch" : trip.status === "on_road" ? "Record delivery outcome" : "View trip"}
                </button>
              </article>
            ))}
          </section>
        )}
        <section className={card} aria-label="GPS and privacy notice">
          <h2 className="text-h3 font-semibold">Location privacy</h2>
          <p className="mt-2 text-body">GPS upload is off. Browser permission: {permission}. No device coordinates are collected by this screen.</p>
          <p className="mt-2 text-caption text-inkMuted">
            During an authorized on-road trip and official shift, location may be shared with the assigned dispatcher every 30 minutes only after approved notice, consent and legal checks.
            Live collection stops at trip or duty end. Lawfully collected history may be retained for up to 7 days for case-authorized review; drivers cannot access investigations.
          </p>
          <button type="button" className={`${secondary} mt-3`} onClick={() => setPrivacyOpen((open) => !open)}>
            Privacy details
          </button>
          {privacyOpen && <p className="mt-2 text-caption">
            Current GPS backend contracts are not enabled for this screen. Permission alone does not authorize GPS upload.
            You must have an active assigned trip, verified duty, individual notice/acknowledgment, and approved deployment before sharing begins.
            Offline GPS points are never queued by this app.
          </p>}
        </section>
      </div>
    </main>
  );
}
