import { beforeEach, describe, expect, it } from "vitest";
import type { WorkLocation } from "../api/locations";
import { useAuthStore } from "./store";
import { selectableWarehouses, useScopeStore } from "./scope";
import { signInAs, userByEmail } from "../test/utils";

const locations: WorkLocation[] = [
  { id: 1, code: "GBG", name: "Göteborg DC", type: "warehouse" },
  { id: 2, code: "STO", name: "Stockholm DC", type: "warehouse" },
  { id: 3, code: "MLM", name: "Malmö DC", type: "warehouse" },
  { id: 101, code: "S-GV", name: "Store Göteborg Väst", type: "store" },
];

beforeEach(() => useScopeStore.setState({ warehouseId: null }));

describe("selectableWarehouses", () => {
  it("dispatcher gets the warehouses in location_ids, never stores", () => {
    expect(selectableWarehouses(userByEmail("dispatcher@cfo.demo"), locations).map((l) => l.code)).toEqual(["GBG", "STO", "MLM"]);
  });

  it("warehouse manager is limited to their own warehouse", () => {
    expect(selectableWarehouses(userByEmail("wm.got@cfo.demo"), locations).map((l) => l.code)).toEqual(["GBG"]);
  });

  it("returns nothing for roles that do not use a warehouse scope", () => {
    expect(selectableWarehouses(userByEmail("sales@cfo.demo"), locations)).toEqual([]);
    expect(selectableWarehouses(userByEmail("admin@cfo.demo"), locations)).toEqual([]);
  });

  it("an empty location_ids means no restriction for a dispatcher", () => {
    const open = { ...userByEmail("dispatcher@cfo.demo"), location_ids: [] };
    expect(selectableWarehouses(open, locations)).toHaveLength(3);
  });
});

describe("useScopeStore", () => {
  it("forgets the chosen warehouse on sign-out", () => {
    signInAs(userByEmail("dispatcher@cfo.demo"));
    useScopeStore.getState().setWarehouse(2);
    expect(useScopeStore.getState().warehouseId).toBe(2);

    useAuthStore.getState().clearAuth();
    expect(useScopeStore.getState().warehouseId).toBeNull();
  });
});