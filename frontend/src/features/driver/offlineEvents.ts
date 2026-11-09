/** Persistent, user-partitioned, idempotent driver event outbox (docs/03 §5.10).
 * Only server 200 responses remove records; offline/timeout does NOT mean delivered.
 * No GPS or coordinates are ever written here.
 */
import { isApiError } from "../../api/client";
import { assignedTrip, stopScopedPodEnabled, submitDriverEvent, type DriverEvent } from "./driverApi";

export type PendingEvent = {
  key: string;
  userId: number;
  tripId: number;
  stopId: number;
  orderId: number;
  event: DriverEvent;
  state: "pending" | "conflict";
  errorCode?: string;
};
export type ReplayResult = { sent: number; conflict: number; waiting: number };
const DB_NAME = "cfo-driver-events-v1";
const STORE = "events";
let replaying = false;

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("Secure offline storage is unavailable."));
      return;
    }
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "key" });
    request.onerror = () => reject(new Error("Offline storage is unavailable."));
    request.onsuccess = () => resolve(request.result);
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore, finish: (result: T) => void, fail: (error: Error) => void) => void,
): Promise<T> {
  const db = await database();
  return new Promise<T>((resolve, reject) => {
    const transaction = db.transaction(STORE, mode);
    const store = transaction.objectStore(STORE);
    let result: T;
    let settled = false;
    const fail = (error: Error) => {
      if (!settled) { settled = true; reject(error); }
    };
    transaction.oncomplete = () => { db.close(); if (!settled) resolve(result); };
    transaction.onerror = () => { db.close(); fail(new Error("Offline storage transaction failed.")); };
    transaction.onabort = () => { db.close(); fail(new Error("Offline storage transaction aborted.")); };
    try {
      action(store, (value) => { result = value; }, fail);
    } catch {
      db.close();
      fail(new Error("Offline storage operation failed."));
    }
  });
}

export async function pendingForUser(userId: number): Promise<PendingEvent[]> {
  const items = await withStore<PendingEvent[]>("readonly", (store, finish, fail) => {
    const request = store.getAll();
    request.onsuccess = () => finish((request.result as PendingEvent[]).filter((item) => item.userId === userId));
    request.onerror = () => fail(new Error("Could not read offline events."));
  });
  return items.sort((a, b) => a.event.occurred_at.localeCompare(b.event.occurred_at));
}

export async function enqueueEvent(event: PendingEvent): Promise<void> {
  await withStore<void>("readwrite", (store, finish) => {
    store.put(event);
    finish(undefined);
  });
}

async function removeEvent(key: string): Promise<void> {
  await withStore<void>("readwrite", (store, finish) => {
    store.delete(key);
    finish(undefined);
  });
}

async function markConflict(event: PendingEvent, code: string): Promise<void> {
  await enqueueEvent({ ...event, state: "conflict", errorCode: code });
}

/** Assignment, trip lifecycle and stop identity are re-read before replay.
 * The server is authoritative for shift/licence/rest/POD transition checks.
 * Completed trips are allowed only to replay the *same* immutable idempotency key,
 * so a lost success response can be recovered instead of forging an acknowledgment.
 */
export async function eligibleForReplay(item: PendingEvent): Promise<boolean> {
  const trip = await assignedTrip(item.tripId);
  const assignedStop = trip.stops.find((stop) => stop.trip_stop_id === item.stopId && stop.order_id === item.orderId);
  if (!assignedStop || item.event.payload.trip_id !== item.tripId) return false;
  if (item.event.event_type === "DISPATCHED") {
    // Dispatch is trip-scoped and cannot introduce stop-specific fields.
    return trip.status === "loading" || trip.status === "on_road";
  }
  // Older queued POD events with no trip_stop_id cannot be sent after a
  // contract upgrade. Exact stop identity must match both outbox and server.
  if (item.event.payload.trip_stop_id === undefined) {
    // Legacy single-stop queued events remain replayable against the merged
    // backend. Never infer a stop from an ambiguous multi-stop trip.
    if (trip.stops.length !== 1 || stopScopedPodEnabled()) return false;
  } else if (item.event.payload.trip_stop_id !== item.stopId) {
    return false;
  }
  const matchingTerminal = item.event.event_type === "DELIVERED" ? "delivered" : "failed";
  return (trip.status === "on_road" &&
      (assignedStop.status === "pending" || assignedStop.status === matchingTerminal)) ||
    (trip.status === "completed" && assignedStop.status === matchingTerminal);
}

/** Injectable replay core for deterministic offline/RBAC/conflict tests.
 * Does not forge an ACK from a trip status or a successful HTTP status with no event_id.
 */
export async function replayBatch(
  items: PendingEvent[],
  dependencies: {
    eligible: (item: PendingEvent) => Promise<boolean>;
    send: (item: PendingEvent) => Promise<{ event_id: number }>;
    acknowledge: (key: string) => Promise<void>;
    reject: (item: PendingEvent, code: string) => Promise<void>;
  },
): Promise<{ sent: number; conflict: number }> {
  let sent = 0;
  let conflict = 0;
  for (const item of items) {
    if (item.state === "conflict") { conflict++; break; }
    try {
      if (!(await dependencies.eligible(item))) {
        await dependencies.reject(item, "NOT_ON_TRIP");
        conflict++;
        // Never skip an unacknowledged predecessor.
        break;
      }
      const ack = await dependencies.send(item);
      if (!Number.isInteger(ack.event_id) || ack.event_id <= 0) {
        throw new Error("Unverified server acknowledgment.");
      }
      await dependencies.acknowledge(item.key);
      sent++;
    } catch (error) {
      if (isApiError(error) && [403, 404, 409, 422].includes(error.status ?? 0)) {
        await dependencies.reject(item, error.code);
        conflict++;
      }
      // Only a definitive server ACK can remove a queued record.
      break;
    }
  }
  return { sent, conflict };
}

export async function replayEvents(userId: number): Promise<ReplayResult> {
  if (replaying || (typeof navigator !== "undefined" && !navigator.onLine)) {
    return { sent: 0, conflict: 0, waiting: (await pendingForUser(userId)).length };
  }
  replaying = true;
  try {
    const result = await replayBatch(await pendingForUser(userId), {
      eligible: eligibleForReplay,
      send: (item) => submitDriverEvent(item.orderId, item.event, item.key),
      acknowledge: removeEvent,
      reject: markConflict,
    });
    return { ...result, waiting: (await pendingForUser(userId)).length };
  } finally {
    replaying = false;
  }
}

/** Explicit user action only: discard a conflicting event with no success claim. */
export async function discardEvent(userId: number, key: string): Promise<void> {
  if (!(await pendingForUser(userId)).some((item) => item.key === key)) {
    throw new Error("Event does not belong to this session.");
  }
  await removeEvent(key);
}
