import { describe, expect, it } from "vitest";
import type { AuthUser } from "../api/contracts/auth";
import { MOCK_ACCOUNTS } from "../api/mocks/authHandlers";
import { PATHS, ROUTE_RULES, canAccessPath, landingPath, resolvePostLoginPath } from "./access";
import { buildMenu, badgeValue } from "./menu";
import { userByEmail } from "../test/utils";

const base: AuthUser = { id: 99, employee_id: 999, name: "Multi", roles: [], market: "SE", location_ids: [], locale: "en", kpi_scopes: [] };

describe("landing path by role (docs/07 mục 18)", () => {
  it.each([
    ["dispatcher@cfo.demo", "/dispatcher/orders"],
    ["wm.got@cfo.demo", "/warehouse/prep"],
    ["sales@cfo.demo", "/store/orders"],
    ["driver1@cfo.demo", "/driver"],
    ["admin@cfo.demo", "/it/integration"],
    ["cs@cfo.demo", "/cs/orders"],
    ["owner@cfo.demo", "/revenue"],
    ["projectlead@cfo.demo", "/kpi"],
  ])("test_US_EMP_03_AC1_%s lands on %s", (email, expected) => {
    expect(landingPath(userByEmail(email))).toBe(expected);
  });

  it("every account lands on a screen it is allowed to open", () => {
    for (const { user } of MOCK_ACCOUNTS) {
      const target = landingPath(user);
      expect(target).not.toBeNull();
      expect(canAccessPath(user, target ?? "")).toBe(true);
    }
  });

  it("uses the documented priority when roles overlap (ASM-B)", () => {
    expect(landingPath({ ...base, roles: ["warehouse", "dispatcher"], kpi_scopes: ["ops", "revenue_all"] })).toBe(PATHS.dispatcherOrders);
    expect(landingPath({ ...base, roles: ["viewer"], kpi_scopes: ["ops", "revenue_all"] })).toBe(PATHS.revenue);
  });

  it("returns null for an account with no workspace", () => {
    expect(landingPath({ ...base, roles: ["viewer"] })).toBeNull();
    expect(resolvePostLoginPath({ ...base, roles: ["viewer"] })).toBe(PATHS.noAccess);
  });
});

describe("route access rules", () => {
  it.each([
    ["dispatcher@cfo.demo", PATHS.dispatcherOrders, true],
    ["dispatcher@cfo.demo", PATHS.itUsers, false],
    ["dispatcher@cfo.demo", PATHS.revenue, false],
    ["dispatcher@cfo.demo", PATHS.notifications, true],
    ["wm.got@cfo.demo", PATHS.warehouseTransfers, true],
    ["wm.got@cfo.demo", PATHS.dispatcherOrders, false],
    ["sales@cfo.demo", PATHS.storeOrders, true],
    ["sales@cfo.demo", PATHS.revenue, false],
    ["sales@cfo.demo", PATHS.kpi, false],
    ["owner@cfo.demo", PATHS.revenue, true],
    ["owner@cfo.demo", PATHS.kpi, false], // revenue_all không kéo theo KPI vận hành
    ["projectlead@cfo.demo", PATHS.kpi, true],
    ["projectlead@cfo.demo", PATHS.revenue, false], // ops không kéo theo doanh thu
    ["admin@cfo.demo", PATHS.itUsers, true],
    ["admin@cfo.demo", PATHS.revenue, true],
    ["cs@cfo.demo", PATHS.csOrders, true],
    ["cs@cfo.demo", PATHS.notifications, true],
    ["cs@cfo.demo", PATHS.itUsers, false],
    ["driver1@cfo.demo", PATHS.driver, true],
    ["driver1@cfo.demo", "/driver/trips/7", true],
    ["driver1@cfo.demo", PATHS.dispatcherOrders, false],
  ])("%s → %s allowed=%s", (email, path, allowed) => {
    expect(canAccessPath(userByEmail(email), path)).toBe(allowed);
  });

  it("denies unknown paths and ignores query strings and trailing slashes", () => {
    const dispatcher = userByEmail("dispatcher@cfo.demo");
    expect(canAccessPath(dispatcher, "/nope")).toBe(false);
    expect(canAccessPath(dispatcher, "/dispatcher/orders/?status=PLANNED")).toBe(true);
    expect(canAccessPath(dispatcher, "/dispatcher/ordersX")).toBe(false);
  });
});

describe("post-login redirect", () => {
  const dispatcher = userByEmail("dispatcher@cfo.demo");

  it("returns to the page the user was heading to when allowed", () => {
    expect(resolvePostLoginPath(dispatcher, "/kpi")).toBe("/kpi");
  });

  it("falls back to the landing page when the target is forbidden, unknown, or not a plain internal path", () => {
    expect(resolvePostLoginPath(dispatcher, "/it/users")).toBe("/dispatcher/orders");
    expect(resolvePostLoginPath(dispatcher, "/")).toBe("/dispatcher/orders");
    expect(resolvePostLoginPath(dispatcher, "//evil.example/kpi")).toBe("/dispatcher/orders");
    expect(resolvePostLoginPath(dispatcher, "https://evil.example")).toBe("/dispatcher/orders");
    expect(resolvePostLoginPath(dispatcher, null)).toBe("/dispatcher/orders");
  });
});

describe("sidebar menu by role (docs/03 mục 3.2)", () => {
  const labels = (email: string) => buildMenu(userByEmail(email)).flatMap((g) => g.items.map((i) => i.label));
  const groups = (email: string) => buildMenu(userByEmail(email)).map((g) => g.label);

  it("dispatcher sees DISPATCHER items and the notification inbox", () => {
    expect(labels("dispatcher@cfo.demo")).toEqual([
      "Order queue", "Plan review", "Exceptions", "Tracking & risk", "Transfers", "KPIs & decision log", "Notification inbox",
    ]);
  });

  it("Project lead sees only KPIs & decision log; Business owner only Revenue", () => {
    expect(labels("projectlead@cfo.demo")).toEqual(["KPIs & decision log"]);
    expect(labels("owner@cfo.demo")).toEqual(["Revenue"]);
  });

  it("sales sees New order (external POS) and My store orders", () => {
    const items = buildMenu(userByEmail("sales@cfo.demo")).flatMap((g) => g.items);
    expect(items.map((i) => i.label)).toEqual(["New order", "My store orders"]);
    expect(items[0]).toMatchObject({ external: "pos" });
    expect(items[0].to).toBeUndefined();
  });

  it("driver has no sidebar", () => {
    expect(buildMenu(userByEmail("driver1@cfo.demo"))).toEqual([]);
  });

  it("customer service sees Order lookup, Contact log and the notification inbox", () => {
    expect(labels("cs@cfo.demo")).toEqual(["Order lookup", "Contact log", "Notification inbox"]);
  });

  it("admin sees REVENUE, KPIs, CUSTOMER-facing admin items but not dispatcher or warehouse operations", () => {
    expect(groups("admin@cfo.demo")).toEqual(["DISPATCHER", "REVENUE", "ADMIN"]);
    expect(labels("admin@cfo.demo")).toContain("Users");
    expect(labels("admin@cfo.demo")).not.toContain("Order queue");
  });

  it("combines groups for multi-role accounts so the user can switch between workspaces (ASM-B)", () => {
    const multi: AuthUser = { ...base, roles: ["dispatcher", "warehouse"], kpi_scopes: ["revenue_all"] };
    expect(buildMenu(multi).map((g) => g.label)).toEqual(["DISPATCHER", "REVENUE", "WAREHOUSE", "ADMIN"]);
  });

  it("never shows an item whose route the same user cannot open (menu and guard share one rule set)", () => {
    for (const { user } of MOCK_ACCOUNTS) {
      for (const item of buildMenu(user).flatMap((g) => g.items)) {
        if (item.to) {
          expect(canAccessPath(user, item.to), `${user.roles.join()} → ${item.to}`).toBe(true);
        }
      }
    }
  });

  it("registers a rule for every menu route and vice versa", () => {
    const rulePaths = ROUTE_RULES.map((r) => r.path);
    expect(new Set(rulePaths).size).toBe(rulePaths.length);
  });

  describe("Revenue · my location (docs/06 mục 3.1, ASM-E)", () => {
    const revenueLabel = (u: AuthUser) =>
      buildMenu(u)
        .flatMap((g) => g.items)
        .find((i) => i.to === PATHS.revenue)?.label;
    const storeOwner: AuthUser = { ...base, roles: ["sales"], location_ids: [21], owned_location_ids: [21] };
    const warehouseOwner: AuthUser = { ...base, roles: ["warehouse"], location_ids: [7], kpi_scopes: ["ops"], owned_location_ids: [7] };

    it("opens Revenue for a store or warehouse owner and labels it 'Revenue · my location'", () => {
      for (const owner of [storeOwner, warehouseOwner]) {
        expect(canAccessPath(owner, PATHS.revenue)).toBe(true);
        expect(revenueLabel(owner)).toBe("Revenue · my location");
      }
    });

    it("keeps the plain 'Revenue' label for admin and Business owner, even if they also own a location", () => {
      const admin: AuthUser = { ...base, roles: ["admin"] };
      const businessOwner: AuthUser = { ...base, roles: ["viewer"], kpi_scopes: ["revenue_all"], owned_location_ids: [21] };

      expect(revenueLabel(admin)).toBe("Revenue");
      expect(revenueLabel(businessOwner)).toBe("Revenue");
    });

    it("does not infer ownership from roles or location_ids; empty or missing owned_location_ids is not an owner", () => {
      const storeStaff: AuthUser = { ...base, roles: ["sales"], location_ids: [21] };
      const warehouseStaff: AuthUser = { ...base, roles: ["warehouse"], location_ids: [7], kpi_scopes: ["ops"], owned_location_ids: [] };

      expect(canAccessPath(storeStaff, PATHS.revenue)).toBe(false);
      expect(canAccessPath(warehouseStaff, PATHS.revenue)).toBe(false);
      expect(revenueLabel(storeStaff)).toBeUndefined();
    });

    it("keeps the owner's role workspace as the landing path", () => {
      expect(landingPath(storeOwner)).toBe(PATHS.storeOrders);
      expect(landingPath(warehouseOwner)).toBe(PATHS.warehousePrep);
    });
  });

});

describe("badges (docs/06 mục 5)", () => {
  const counts = { awaiting_approval: 4, nav: { order_queue: 6, exceptions: 2, tracking_risk: 3 } };

  it("maps nav keys directly and Plan review to awaiting_approval", () => {
    expect(badgeValue(counts, "order_queue")).toBe(6);
    expect(badgeValue(counts, "plan_review")).toBe(4);
    expect(badgeValue(counts, "exceptions")).toBe(2);
    expect(badgeValue(counts, "tracking_risk")).toBe(3);
  });

  it("shows no number until counts have loaded", () => {
    expect(badgeValue(undefined, "order_queue")).toBeUndefined();
  });
});