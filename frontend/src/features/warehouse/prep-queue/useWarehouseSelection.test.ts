import { describe, expect, it } from "vitest";
import { chooseWarehouse } from "./useWarehouseSelection";

const gbg = { id: 1, code: "GBG", name: "Göteborg DC", type: "warehouse" };
const sto = { id: 2, code: "STO", name: "Stockholm DC", type: "warehouse" };

describe("chooseWarehouse", () => {
  it("returns none when the user has no selectable warehouse", () => {
    expect(chooseWarehouse([], null)).toEqual({ status: "none" });
    expect(chooseWarehouse([], 1)).toEqual({ status: "none" });
  });

  it("uses the only warehouse when the sidebar shows All warehouses", () => {
    expect(chooseWarehouse([gbg], null)).toEqual({ status: "selected", warehouse: gbg });
  });

  it("asks the user to choose when several warehouses are allowed and none is picked", () => {
    expect(chooseWarehouse([gbg, sto], null)).toEqual({ status: "choose" });
  });

  it("uses the warehouse picked in the sidebar", () => {
    expect(chooseWarehouse([gbg, sto], 2)).toEqual({ status: "selected", warehouse: sto });
  });

  it("never shows a warehouse outside the allowed list", () => {
    expect(chooseWarehouse([gbg], 2)).toEqual({ status: "none" });
  });
});