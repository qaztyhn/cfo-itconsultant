import { act, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "./store";
import { currentPath, currentState, renderAt, signInAs, userByEmail } from "../test/utils";

const screenOf = (name: string) => document.querySelector(`[data-screen="${name}"]`);

async function expectPath(path: string) {
  await waitFor(() => expect(currentPath()).toBe(path));
}

afterEach(() => {
  vi.useRealTimers();
});

describe("RequireAuth", () => {
  it("sends a signed-out visitor to /login and remembers where they were going", async () => {
    renderAt("/dispatcher/orders?status=PLANNED");

    await expectPath("/login");
    expect(currentState()).toEqual({ from: "/dispatcher/orders?status=PLANNED" });
  });

  it("redirects an expired session to /login and clears it", async () => {
    signInAs(userByEmail("dispatcher@cfo.demo"), -1);
    renderAt("/kpi");

    await expectPath("/login");
    expect(useAuthStore.getState().token).toBeNull();
  });

  it("signs the user out when the session expires while the app is open", async () => {
    vi.useFakeTimers();
    signInAs(userByEmail("dispatcher@cfo.demo"), 60);
    renderAt("/dispatcher/orders");
    expect(currentPath()).toBe("/dispatcher/orders");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000);
    });

    await vi.waitFor(() => expect(currentPath()).toBe("/login"));
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("bounces to /login when the session is cleared (e.g. after a 401 handled by client.ts)", async () => {
    signInAs(userByEmail("dispatcher@cfo.demo"));
    renderAt("/dispatcher/orders");

    await act(async () => {
      useAuthStore.getState().clearAuth();
    });

    await expectPath("/login");
  });
});

describe("landing redirect", () => {
  it.each([
    ["dispatcher@cfo.demo", "/dispatcher/orders", "OrderQueue"],
    ["wm.got@cfo.demo", "/warehouse/prep", "PrepQueue"],
    ["cs@cfo.demo", "/cs/orders", "OrderLookup"],
    ["owner@cfo.demo", "/revenue", "Revenue"],
    ["projectlead@cfo.demo", "/kpi", "KpiDashboard"],
    ["admin@cfo.demo", "/it/integration", "DataIntegration"],
    ["sales@cfo.demo", "/store/orders", "MyStoreOrders"],
    ["driver1@cfo.demo", "/driver", "TodaysTrips"],
  ])("test_US_EMP_03_AC1_%s opens %s from /", async (email, path, screenName) => {
    signInAs(userByEmail(email));
    renderAt("/");

    await expectPath(path);
    await waitFor(() => expect(screenOf(screenName)).toBeInTheDocument());
  });
});

describe("RequireAccess", () => {
  it("redirects a role to its own landing page instead of a forbidden screen", async () => {
    signInAs(userByEmail("wm.got@cfo.demo"));
    renderAt("/dispatcher/orders");

    await expectPath("/warehouse/prep");
    expect(screenOf("OrderQueue")).toBeNull();
    expect(currentState()).toEqual({ denied: "/dispatcher/orders" });
  });

  it("keeps revenue away from Project lead", async () => {
    signInAs(userByEmail("projectlead@cfo.demo"));
    renderAt("/revenue");
    await expectPath("/kpi");
  });

  it("keeps KPIs away from Business owner", async () => {
    signInAs(userByEmail("owner@cfo.demo"));
    renderAt("/kpi");
    await expectPath("/revenue");
  });

  it("renders an explanation, not a blank page, for an account with no workspace", async () => {
    signInAs({ ...userByEmail("owner@cfo.demo"), kpi_scopes: [] });
    renderAt("/");

    expect(await screen.findByRole("heading", { name: /no workspace/i })).toBeInTheDocument();
  });

  it("sends unknown URLs back through the landing redirect", async () => {
    signInAs(userByEmail("dispatcher@cfo.demo"));
    renderAt("/does-not-exist");
    await expectPath("/dispatcher/orders");
  });
});

describe("GuestOnly /login", () => {
  it("shows the sign-in screen to visitors", async () => {
    renderAt("/login");

    await expectPath("/login");
    await waitFor(() => expect(screenOf("SignIn")).toBeInTheDocument());
  });

  it("test_US_EMP_03_AC1_sends an already signed-in user to their landing page", async () => {
    signInAs(userByEmail("dispatcher@cfo.demo"));
    renderAt("/login");
    await expectPath("/dispatcher/orders");
  });
});

describe("route table", () => {
  it.each([
    ["/it/users", "Users"],
    ["/it/vehicles", "Vehicles"],
    ["/notifications", "NotificationInbox"],
    ["/revenue", "Revenue"],
    ["/kpi", "KpiDashboard"],
  ])("opens %s for an admin", async (path, screenName) => {
    signInAs(userByEmail("admin@cfo.demo"));
    renderAt(path);

    await waitFor(() => expect(screenOf(screenName)).toBeInTheDocument());
  });
});