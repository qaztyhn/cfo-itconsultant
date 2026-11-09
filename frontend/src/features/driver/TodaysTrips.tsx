import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { useAuthStore } from "../../app/store";
import { USE_MOCKS } from "../../api/config";
import { getDriverTrip, listDriverTrips, type DriverTrip } from "./driverApi";
import { TripDetail } from "./TripDetail";
import { flush, pendingFor } from "./offlineQueue";

export function TodaysTrips() {
  const user = useAuthStore(s => s.user);
  const driverUserId = user?.id;
  const driver = Boolean(user?.roles.includes("driver") && user.employee_id);
  const [online, setOnline] = useState(() => typeof navigator === "undefined" || navigator.onLine);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [pending, setPending] = useState(0);
  const [queueMessage, setQueueMessage] = useState("");
  const list = useQuery({ queryKey: ["driver", "trips", user?.id], queryFn: ({ signal }) => listDriverTrips(undefined, signal), enabled: driver, retry: false });
  const detail = useQuery({ queryKey: ["driver", "trip", selectedId], queryFn: ({ signal }) => getDriverTrip(selectedId!, signal), enabled: driver && selectedId !== null, retry: false });
  const refreshQueue = useCallback(async () => {
    if (!driverUserId) return;
    try { setPending((await pendingFor(driverUserId)).length); }
    catch { setQueueMessage("Offline storage is unavailable. Updates cannot be saved on this device."); }
  }, [driverUserId]);
  const sync = useCallback(async () => {
    if (!driverUserId || USE_MOCKS) return;
    try {
      const result = await flush(driverUserId);
      setPending(result.pending);
      if (result.conflict) setQueueMessage(result.conflict);
      else if (result.sent) { setQueueMessage(`${result.sent} update(s) confirmed by the server.`); void list.refetch(); void detail.refetch(); }
    } catch { setQueueMessage("Offline storage is unavailable. Updates remain unverified."); }
  }, [driverUserId, list, detail]);
  useEffect(() => { void Promise.resolve().then(refreshQueue); }, [refreshQueue]);
  useEffect(() => {
    const onOnline = () => { setOnline(true); void sync(); };
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline); window.addEventListener("offline", onOffline);
    return () => { window.removeEventListener("online", onOnline); window.removeEventListener("offline", onOffline); };
  }, [sync]);
  const trips = list.data ?? [];
  const chosen = selectedId === null ? null : detail.data;

  return <main data-screen="TodaysTrips" className="min-h-screen bg-stone text-deepPine">
    <header className="rounded-b-3xl bg-deepPine px-5 pb-7 pt-8 text-white">
      <div className="mx-auto flex max-w-2xl items-start justify-between gap-3">
        <div><p className="text-sm uppercase tracking-[0.2em]">CFO Driver</p><h1 className="mt-2 text-3xl font-bold">Today&apos;s trips</h1></div>
        <span className="rounded-full border border-white/40 px-3 py-2 font-mono text-sm">{chosen?.vehicle_code ?? `${trips.length} trips`}</span>
      </div>
      <div className="mx-auto mt-5 flex max-w-2xl flex-wrap gap-2 text-sm">
        <span role="status" className="rounded-full bg-white/15 px-3 py-2">{online ? "Online" : "Offline"}</span>
        <span className="rounded-full bg-white/15 px-3 py-2">{pending ? `${pending} update(s) waiting to send` : "No offline updates pending"}</span>
      </div>
    </header>
    {!driver ? <p role="alert" className="mx-auto max-w-2xl p-5">Permission denied. This app is for assigned drivers.</p> : selectedId !== null ?
      detail.isPending ? <p role="status" className="p-5">Loading trip details…</p> :
      detail.isError ? <div role="alert" className="mx-auto max-w-2xl p-5">Trip unavailable or not assigned. <button className="underline" onClick={() => void detail.refetch()}>Retry</button><button className="ml-4 underline" onClick={() => setSelectedId(null)}>Back</button></div> :
      chosen ? <TripDetail trip={chosen} driverUserId={user!.id} online={online} mock={USE_MOCKS}
        onBack={() => setSelectedId(null)} onUpdated={() => { void detail.refetch(); void list.refetch(); }} onSaved={() => void refreshQueue()} /> : null
      : <section className="mx-auto max-w-2xl space-y-5 px-4 py-6" aria-label="Assigned trips">
        {USE_MOCKS && <p role="status" className="rounded-xl bg-amber-50 p-4">Synthetic contract preview · not live assigned trips.</p>}
        {list.isPending ? <p role="status">Loading assigned trips…</p> : list.isError ?
          <div role="alert" className="rounded-xl bg-white p-5">Assigned trips unavailable. <button className="underline" onClick={() => void list.refetch()}>Retry</button></div> :
          trips.length === 0 ? <p className="rounded-xl bg-white p-5">No assigned trips for the market day.</p> :
          trips.map((trip: DriverTrip) => <article key={trip.trip_id} className="rounded-2xl bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between"><span className="font-mono text-sm">TRIP #{trip.trip_id}</span><span className="rounded-full bg-slate-100 px-3 py-1 text-sm">{trip.status}</span></div>
            <h2 className="mt-3 text-xl font-semibold">{trip.vehicle_code}</h2>
            <p className="mt-1">{trip.warehouse_code} · {trip.stops.length} stop(s)</p>
            <p className="mt-2 text-sm text-slate-600">{trip.stops.map(stop => stop.order_no).join(" · ")}</p>
            <p className="mt-2 text-sm">Planned departure {new Date(trip.depart_planned_at).toLocaleString()}</p>
            <button className="mt-4 min-h-12 w-full rounded-xl bg-apricot px-4 py-3 font-semibold text-deepPine" onClick={() => setSelectedId(trip.trip_id)}>View trip details</button>
          </article>)}
        <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5" aria-label="Duty and location privacy">
          <h2 className="text-lg font-semibold">Duty and location</h2>
          <p className="mt-2">Official shift and driver availability: not supplied by the current trip DTO. The server checks eligibility before recording an event.</p>
          <p className="mt-2">Location off. Individual notice, acknowledgment, approved duty and trip evidence are not connected to this UI. Browser permission alone is insufficient.</p>
          <button type="button" disabled className="mt-3 min-h-12 w-full rounded-xl border border-slate-400 px-4 text-slate-500" aria-describedby="gps-permission-reason">Location permission unavailable</button>
          <p id="gps-permission-reason" className="mt-2 text-sm">Collection can be offered only after the server provides verified individual permission and active duty evidence.</p>
          <details className="mt-3"><summary className="cursor-pointer font-semibold">GPS privacy details</summary>
            <p className="mt-2">If separately authorized, location is collected only during an active trip and official duty, at a 30-minute cadence. It stops at trip or duty end. Valid historical points may be retained for up to 7 days under restricted audited access. Customers cannot see location; this app has no history controls.</p>
          </details>
        </section>
      </section>}
    {queueMessage && <p role="alert" className="mx-auto max-w-2xl px-4 pb-5">{queueMessage}</p>}
    {online && pending > 0 && !USE_MOCKS && <button className="mx-auto block min-h-12 rounded-xl border px-5" onClick={() => void sync()}>Retry pending updates</button>}
  </main>;
}
