/**
 * Decides which warehouse and date the Prep Queue shows (docs/03 §3.2 scope, docs/09 invariant 17).
 * - Warehouse: sidebar choice (useScopeStore). With "All warehouses" and exactly one selectable warehouse, use it.
 *   With several, ask the user to pick: never default to the first one (writes in PR 2 must not hit the wrong warehouse).
 * - Date: "today" in the warehouse time zone. No time zone → stop, never guess.
 * Shares the ["locations"] query with ScopePicker, so no extra request.
 * Owner: Dev 3 (stream C) — M6.
 */
import { useQuery } from "@tanstack/react-query";
import { fetchLocations, type WorkLocation } from "../../../api/locations";
import { selectableWarehouses, useScopeStore, usesWarehouseScope } from "../../../app/scope";
import { useAuthStore } from "../../../app/store";
import { resolveTimeZone, todayInTimeZone, type LocationWithTimeZone } from "./timezone";

export type WarehouseChoice =
  | { status: "none" }
  | { status: "choose" }
  | { status: "selected"; warehouse: WorkLocation };

/** Pure rule, unit-tested. `selectable` is already limited to the user's allowed warehouses. */
export function chooseWarehouse(selectable: WorkLocation[], scopeWarehouseId: number | null): WarehouseChoice {
  if (selectable.length === 0) {
    return { status: "none" };
  }
  if (scopeWarehouseId !== null) {
    const picked = selectable.find((w) => w.id === scopeWarehouseId);
    return picked ? { status: "selected", warehouse: picked } : { status: "none" };
  }
  return selectable.length === 1 ? { status: "selected", warehouse: selectable[0] } : { status: "choose" };
}

export type PrepQueueScope =
  | { status: "loading" }
  | { status: "error"; error: unknown; retry: () => void }
  | { status: "no-warehouse" }
  | { status: "choose-warehouse" }
  | { status: "no-timezone"; warehouse: WorkLocation }
  | { status: "ready"; warehouse: WorkLocation; warehouseId: number; date: string; timeZone: string };

export function useWarehouseSelection(now: Date = new Date()): PrepQueueScope {
  const user = useAuthStore((s) => s.user);
  const scopeWarehouseId = useScopeStore((s) => s.warehouseId);
  const wanted = user ? usesWarehouseScope(user) : false;

  const query = useQuery({
    queryKey: ["locations"],
    queryFn: ({ signal }) => fetchLocations(signal),
    enabled: wanted,
    staleTime: 5 * 60_000,
  });

  if (!user || !wanted) {
    return { status: "no-warehouse" };
  }
  if (query.isError) {
    return { status: "error", error: query.error, retry: () => void query.refetch() };
  }
  if (query.data === undefined) {
    return { status: "loading" };
  }

  const choice = chooseWarehouse(selectableWarehouses(user, query.data), scopeWarehouseId);
  if (choice.status === "none") {
    return { status: "no-warehouse" };
  }
  if (choice.status === "choose") {
    return { status: "choose-warehouse" };
  }

  const timeZone = resolveTimeZone(choice.warehouse as LocationWithTimeZone);
  if (timeZone === null) {
    return { status: "no-timezone", warehouse: choice.warehouse };
  }
  return {
    status: "ready",
    warehouse: choice.warehouse,
    warehouseId: choice.warehouse.id,
    date: todayInTimeZone(now, timeZone),
    timeZone,
  };
}