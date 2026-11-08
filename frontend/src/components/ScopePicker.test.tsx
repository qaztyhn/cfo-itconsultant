import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchLocations } from "../api/locations";
import { useScopeStore } from "../app/scope";
import { signInAs, userByEmail } from "../test/utils";
import { ScopePicker } from "./ScopePicker";

vi.mock("../api/locations", () => ({ fetchLocations: vi.fn() }));

const locations = [
  { id: 1, code: "GBG", name: "Göteborg DC", type: "warehouse" },
  { id: 2, code: "STO", name: "Stockholm DC", type: "warehouse" },
  { id: 3, code: "MLM", name: "Malmö DC", type: "warehouse" },
  { id: 101, code: "S-GV", name: "Store Göteborg Väst", type: "store" },
];

function renderPicker(email: string) {
  signInAs(userByEmail(email));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ScopePicker />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useScopeStore.setState({ warehouseId: null });
  vi.mocked(fetchLocations).mockReset();
  vi.mocked(fetchLocations).mockResolvedValue(locations);
});

describe("ScopePicker", () => {
  it("dispatcher picks a warehouse from a dropdown that starts on All warehouses", async () => {
    renderPicker("dispatcher@cfo.demo");

    const select = await screen.findByRole("combobox", { name: "Warehouse" });
    expect(select).toHaveValue("");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["All warehouses", "Göteborg DC", "Stockholm DC", "Malmö DC"]);

    await userEvent.setup().selectOptions(select, "Stockholm DC");
    expect(useScopeStore.getState().warehouseId).toBe(2);
  });

  it("a warehouse manager with one warehouse sees a fixed label, not a dropdown", async () => {
    renderPicker("wm.got@cfo.demo");

    expect(await screen.findByText("Göteborg DC")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("shows the market label for everyone", () => {
    renderPicker("owner@cfo.demo");

    expect(screen.getByText("SE")).toBeInTheDocument();
  });

  it("does not request locations for roles without a warehouse scope", () => {
    renderPicker("sales@cfo.demo");

    expect(fetchLocations).not.toHaveBeenCalled();
    expect(screen.queryByRole("combobox")).toBeNull();
  });
});