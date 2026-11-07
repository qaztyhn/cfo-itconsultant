import { beforeEach, describe, expect, it } from "vitest";
import type { WorkLocation } from "../api/locations";
import { useAuthStore } from "./store";
import { selectableWarehouses, useScopeStore } from "./scope";
import { signInAs, userByEmail } from "../test/utils";

const locations: WorkLocation[] = [
  { id: 1, code: "GBG", name: "Göteborg DC", type: "warehouse" },
  { id: 2, code: "STO", name: "Stockholm DC", type: "warehouse" },
  { id: 3, code: "MLM", name: "Malmö DC", type: "warehouse" },
  { id: 4, code: "DC", name: "Dispatch Center", type: "dispatch_center" },
  { id: 101, code: "S-GV", name: "Store Göteborg Väst", type: "store" },
];

beforeEach(() => useScopeStore.setState({ warehouseId: null }));

describe("selectableWarehouses", () => {
  it("dispatcher (seed M0: assigned to DC only) still gets every warehouse the backend returned", () => {
    const dispatcher = userByEmail("dispatcher@cfo.demo");
    expect(dispatcher.location_ids).toEqual([4]); // đúng seed M0: chỉ DC
    expect(selectableWarehouses(dispatcher, locations).map((l) => l.code)).toEqual(["GBG", "STO", "MLM"]);
  });

  it("dispatcher never gets non-warehouse locations (DC, stores)", () => {
    const codes = selectableWarehouses(userByEmail("dispatcher@cfo.demo"), locations).map((l) => l.code);
    expect(codes).not.toContain("DC");
    expect(codes).not.toContain("S-GV");
  });

  it("warehouse manager with no assignment sees no warehouse", () => {
    const unassigned = { ...userByEmail("wm.got@cfo.demo"), location_ids: [] };
    expect(selectableWarehouses(unassigned, locations)).toEqual([]);
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