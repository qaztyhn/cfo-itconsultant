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
import { resolveTimeZone, type LocationWithTimeZone } from "./timezone";
import { useToday } from "./useToday";

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

export function useWarehouseSelection(): PrepQueueScope {
  const user = useAuthStore((s) => s.user);
  const scopeWarehouseId = useScopeStore((s) => s.warehouseId);
  const wanted = user ? usesWarehouseScope(user) : false;

  const query = useQuery({
    queryKey: ["locations"],
    queryFn: ({ signal }) => fetchLocations(signal),
    enabled: wanted,
    staleTime: 5 * 60_000,
  });

  // Hooks must run on every render, so the warehouse and time zone are resolved before any early return.
  const choice = user && wanted && query.data !== undefined ? chooseWarehouse(selectableWarehouses(user, query.data), scopeWarehouseId) : null;
  const warehouse = choice?.status === "selected" ? choice.warehouse : null;
  const timeZone = warehouse ? resolveTimeZone(warehouse as LocationWithTimeZone) : null;
  const today = useToday(timeZone);

  if (!user || !wanted) {
    return { status: "no-warehouse" };
  }
  if (query.isError) {
    return { status: "error", error: query.error, retry: () => void query.refetch() };
  }
  if (query.data === undefined || choice === null) {
    return { status: "loading" };
  }
  if (choice.status === "none") {
    return { status: "no-warehouse" };
  }
  if (choice.status === "choose") {
    return { status: "choose-warehouse" };
  }
  if (timeZone === null) {
    return { status: "no-timezone", warehouse: choice.warehouse };
  }
  if (today === null) {
    return { status: "loading" };
  }
  return { status: "ready", warehouse: choice.warehouse, warehouseId: choice.warehouse.id, date: today, timeZone };
}