import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { POS_URL } from "../api/config";
import { fetchOrderCounts } from "../api/orders";
import { signOut } from "../app/session";
import { signInAs, userByEmail } from "../test/utils";
import { Sidebar } from "./Sidebar";

vi.mock("../api/orders", () => ({ fetchOrderCounts: vi.fn() }));
vi.mock("../app/session", () => ({ signOut: vi.fn() }));
vi.mock("../api/locations", () => ({ fetchLocations: vi.fn().mockResolvedValue([]) }));

const counts = { awaiting_approval: 4, nav: { order_queue: 6, exceptions: 2, tracking_risk: 3 } };

function renderSidebar(email: string, path = "/") {
  signInAs(userByEmail(email));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Sidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(fetchOrderCounts).mockReset();
  vi.mocked(fetchOrderCounts).mockResolvedValue(counts);
  vi.mocked(signOut).mockReset();
});

describe("Sidebar", () => {
  it("shows badges from /orders/counts on the dispatcher items (Plan review = awaiting_approval)", async () => {
    renderSidebar("dispatcher@cfo.demo");

    await waitFor(() => expect(screen.getByRole("link", { name: /Order queue/ })).toHaveTextContent("6"));
    expect(screen.getByRole("link", { name: /Plan review/ })).toHaveTextContent("4");
    expect(screen.getByRole("link", { name: /Exceptions/ })).toHaveTextContent("2");
    expect(screen.getByRole("link", { name: /Tracking & risk/ })).toHaveTextContent("3");
    expect(screen.getByRole("link", { name: "Transfers" })).toBeInTheDocument();
  });

  it("shows no badge before counts load (no fake zero)", () => {
    vi.mocked(fetchOrderCounts).mockReturnValue(new Promise(() => {}));
    renderSidebar("dispatcher@cfo.demo");

    expect(screen.getByRole("link", { name: "Order queue" })).toBeInTheDocument();
  });

  it("hides a badge whose count is 0", async () => {
    vi.mocked(fetchOrderCounts).mockResolvedValue({ ...counts, nav: { ...counts.nav, exceptions: 0 } });
    renderSidebar("dispatcher@cfo.demo");

    await waitFor(() => expect(screen.getByRole("link", { name: /Order queue/ })).toHaveTextContent("6"));
    expect(screen.getByRole("link", { name: "Exceptions" })).toBeInTheDocument();
  });

  it("marks the current route with aria-current", () => {
    renderSidebar("dispatcher@cfo.demo", "/dispatcher/plan-review");

    expect(screen.getByRole("link", { name: /Plan review/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Order queue/ })).not.toHaveAttribute("aria-current");
  });

  it("sales sees New order as an external POS link and never requests counts", () => {
    renderSidebar("sales@cfo.demo");

    const pos = screen.getByRole("link", { name: "New order" });
    expect(pos).toHaveAttribute("href", POS_URL);
    expect(pos).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: "My store orders" })).toBeInTheDocument();
    expect(fetchOrderCounts).not.toHaveBeenCalled();
  });

  it("Business owner sees only Revenue and the role label", () => {
    renderSidebar("owner@cfo.demo");

    expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual(["Revenue"]);
    expect(screen.getByText("Business owner")).toBeInTheDocument();
    expect(fetchOrderCounts).not.toHaveBeenCalled();
  });

  it("shows the user block and signs out", async () => {
    renderSidebar("dispatcher@cfo.demo");

    expect(screen.getByText("Anna Lindqvist")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));
    expect(signOut).toHaveBeenCalledOnce();
  });
});