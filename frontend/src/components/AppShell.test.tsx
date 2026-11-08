import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchLocations } from "../api/locations";
import { fetchOrderCounts } from "../api/orders";
import { demoContextFor } from "../app/demoContext";
import { currentPath, renderAt, signInAs, userByEmail } from "../test/utils";

vi.mock("../api/orders", () => ({ fetchOrderCounts: vi.fn() }));
vi.mock("../api/locations", () => ({ fetchLocations: vi.fn() }));

const screenName = (container: HTMLElement) => container.querySelector("[data-screen]")?.getAttribute("data-screen");

beforeEach(() => {
  vi.mocked(fetchOrderCounts).mockReset();
  vi.mocked(fetchOrderCounts).mockResolvedValue({ awaiting_approval: 4, nav: { order_queue: 6, exceptions: 2, tracking_risk: 3 } });
  vi.mocked(fetchLocations).mockReset();
  vi.mocked(fetchLocations).mockResolvedValue([]);
});

describe("AppShell", () => {
  it("dispatcher: sidebar, demo banner with the screen context, and the screen inside <main>", async () => {
    signInAs(userByEmail("dispatcher@cfo.demo"));
    const { container } = renderAt("/dispatcher/orders");

    expect(screen.getByRole("complementary", { name: "Sidebar" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("DEMO · SYNTHETIC DATA");
    expect(screen.getByRole("note")).toHaveTextContent(demoContextFor("/dispatcher/orders"));
    expect(screen.getByRole("main")).toContainElement(container.querySelector("[data-screen='OrderQueue']") as HTMLElement);
    await waitFor(() => expect(screen.getByRole("link", { name: /Order queue/ })).toHaveTextContent("6"));
  });

  it("the banner context follows navigation from the sidebar", async () => {
    signInAs(userByEmail("dispatcher@cfo.demo"));
    renderAt("/dispatcher/orders");

    await userEvent.setup().click(screen.getByRole("link", { name: "Notification inbox" }));

    expect(currentPath()).toBe("/notifications");
    expect(screen.getByRole("note")).toHaveTextContent(demoContextFor("/notifications"));
  });

  it("sales lands in the shell with only their two items", () => {
    signInAs(userByEmail("sales@cfo.demo"));
    const { container } = renderAt("/store/orders");

    expect(screenName(container)).toBe("MyStoreOrders");
    expect(screen.getAllByRole("link").map((a) => a.textContent).filter((t) => t !== "Skip to content")).toEqual(["New order", "My store orders"]);
  });

  it("Business owner sees only Revenue and cannot open dispatcher screens", () => {
    signInAs(userByEmail("owner@cfo.demo"));
    renderAt("/dispatcher/orders");

    expect(currentPath()).toBe("/revenue");
    expect(screen.queryByRole("link", { name: /Order queue/ })).toBeNull();
  });

  it("driver gets no AppShell: no sidebar and no banner", () => {
    signInAs(userByEmail("driver1@cfo.demo"));
    renderAt("/driver");

    expect(currentPath()).toBe("/driver");
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("offers a skip link to the main content", () => {
    signInAs(userByEmail("dispatcher@cfo.demo"));
    renderAt("/dispatcher/orders");

    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });
});