import { isApiError } from "../../api/client";
import { eventAllowed, getDriverTrip, sendDriverEvent, type DriverEvent } from "./driverApi";

export interface QueuedEvent extends DriverEvent { driverUserId: number }
export interface QueueStore {
  put(event: QueuedEvent): Promise<void>;
  list(): Promise<QueuedEvent[]>;
  remove(key: string): Promise<void>;
}
const DB = "cfo-driver-events-v1";
const TABLE = "events";

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") { reject(new Error("Offline storage is unavailable.")); return; }
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(TABLE, { keyPath: "idempotencyKey" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Offline storage failed."));
  });
}
async function transaction<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore, done: (value: T) => void) => void): Promise<T> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(TABLE, mode);
    let value: T;
    tx.oncomplete = () => { db.close(); resolve(value); };
    tx.onerror = () => { db.close(); reject(tx.error ?? new Error("Offline storage failed.")); };
    tx.onabort = () => { db.close(); reject(tx.error ?? new Error("Offline storage failed.")); };
    action(tx.objectStore(TABLE), result => { value = result; });
  });
}

export const indexedQueue: QueueStore = {
  put: event => transaction<void>("readwrite", store => { store.put(event); }),
  list: () => transaction<QueuedEvent[]>("readonly", (store, done) => {
    const req = store.getAll();
    req.onsuccess = () => done(req.result as QueuedEvent[]);
  }),
  remove: key => transaction<void>("readwrite", store => { store.delete(key); }),
};

export async function enqueue(event: QueuedEvent, store: QueueStore = indexedQueue): Promise<void> {
  await store.put(event); // Only after this resolves may the UI say "saved offline".
}

export async function pendingFor(driverUserId: number, store: QueueStore = indexedQueue): Promise<QueuedEvent[]> {
  return (await store.list()).filter(event => event.driverUserId === driverUserId)
    .sort((a, b) => a.occurredAt.localeCompare(b.occurredAt));
}

export interface ReplayResult { sent: number; pending: number; conflict: string | null }
/** Recheck assignment and current trip state before every retry; stop at first conflict. */
export async function flush(driverUserId: number, store: QueueStore = indexedQueue): Promise<ReplayResult> {
  const events = await pendingFor(driverUserId, store);
  let sent = 0;
  for (const event of events) {
    try {
      const trip = await getDriverTrip(event.tripId, undefined, false);
      if (!eventAllowed(trip, event)) return { sent, pending: events.length - sent, conflict: "Trip state changed. Review this update with dispatch." };
      const ack = await sendDriverEvent(event, false);
      if (!Number.isInteger(ack.event_id) || ack.event_id <= 0) return { sent, pending: events.length - sent, conflict: "Server acknowledgment is incomplete." };
      await store.remove(event.idempotencyKey);
      sent++;
    } catch (error) {
      if (isApiError(error) && (error.status === 403 || error.status === 404 || error.status === 409 || error.status === 422)) {
        return { sent, pending: events.length - sent, conflict: `${error.code}: review this update with dispatch.` };
      }
      return { sent, pending: events.length - sent, conflict: null }; // Network failure: retain original key/body.
    }
  }
  return { sent, pending: 0, conflict: null };
}
