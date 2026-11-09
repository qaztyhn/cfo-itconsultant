/** Isolated Product Mapping tests: no shared router or global MSW handler changes. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { useAuthStore } from "../../app/store";
import type { AuthUser } from "../../api/contracts/auth";
import { ProductMapping } from "./ProductMapping";

const mocks = vi.hoisted(() => ({
  tasks: vi.fn(), task: vi.fn(), locals: vi.fn(), confirm: vi.fn(), reject: vi.fn(),
}));
vi.mock("./productMappingApi", async original => {
  const real = await original<typeof import("./productMappingApi")>();
  return { ...real, listMappingTasks: mocks.tasks, loadMappingTask: mocks.task,
    listLocalProducts: mocks.locals, confirmMapping: mocks.confirm, rejectMapping: mocks.reject };
});
const admin: AuthUser = {
  id: 1, employee_id: 10, name: null, roles: ["admin"], market: "SE",
  location_ids: [], locale: "en", kpi_scopes: [], owned_location_ids: [],
};
const dispatcher: AuthUser = { ...admin, id: 2, roles: ["dispatcher"] };
const task = {
  id: 12, market: "SE", local_sku: "SE-NEW-77", name: "Synthetic cement",
  category: "Cement", gtin: "7312345678901", sale_unit: "bag",
  mapping_status: "pending", status: "open", blocked_order_count: 2,
  candidates: [{ global_product_id: 123, code: "G-000123", name: "Cement",
    reason: "gtin", score: 1 }],
  resolved_by: null, resolved_at: null, suggested_handling_group: "N3",
};
beforeEach(() => {
  mocks.tasks.mockResolvedValue({ items: [task], total: 1, page: 1, page_size: 20 });
  mocks.task.mockResolvedValue(task);
  mocks.locals.mockResolvedValue({ items: [
    { market: "SE", local_sku: "SE-NEW-77", name: "Synthetic cement",
      category: "Cement", gtin: "7312345678901", sale_unit: "bag",
      units_to_base: "1", unit_price: "10.00", currency: "SEK",
      global_product_id: null, mapping_status: "pending" },
  ], total: 1, page: 1, page_size: 20 });
  mocks.confirm.mockResolvedValue({ task_id: 12, local_sku: "SE-NEW-77", global_product_id: 123, mapping_status: "confirmed" });
  mocks.reject.mockResolvedValue({ task_id: 12, local_sku: "SE-NEW-77", mapping_status: "rejected" });
});
afterEach(() => {
  useAuthStore.getState().clearAuth();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});
function mount(user: AuthUser = admin) {
  useAuthStore.getState().setAuth(
    { access_token: "test-token", token_type: "bearer", expires_in: 28800, user }, "test@cfo.demo");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><ProductMapping /></QueryClientProvider>);
}
async function selectTask() {
  await screen.findByRole("button", { name: /SE-NEW-77 · SE/ });
  fireEvent.click(screen.getByRole("button", { name: /SE-NEW-77 · SE/ }));
  return screen.findByRole("heading", { name: "SKU SE-NEW-77" });
}

describe("US-PRD-01 AC1–AC4 — pending IT mapping queue", () => {
  it("refuses dispatcher role with zero reads or writes", () => {
    mount(dispatcher);
    expect(screen.getByText(/IT administrator access is required/)).toBeInTheDocument();
    expect(mocks.tasks).not.toHaveBeenCalled();
  });
  it("shows server tasks, safe legacy counts and rule evidence without auto-confirming", async () => {
    mount();
    await selectTask();
    expect(screen.getByText(/2 · not a CFO waiting queue/)).toBeInTheDocument();
    expect(screen.getByText(/GTIN match/)).toBeInTheDocument();
    expect(screen.getByText(/whole order ineligible/)).toBeInTheDocument();
    expect(mocks.confirm).not.toHaveBeenCalled();
  });
  it("passes task filters and paginated local-product search to the server", async () => {
    mount();
    await screen.findByRole("heading", { name: "Mapping tasks" });
    fireEvent.change(screen.getByRole("textbox", { name: "Search tasks" }), { target: { value: "NEW" } });
    await waitFor(() => expect(mocks.tasks).toHaveBeenCalledWith(
      expect.objectContaining({ q: "NEW", status: "open" }), expect.anything()));
    fireEvent.change(screen.getByRole("textbox", { name: "Search local products" }), { target: { value: "cement" } });
    await waitFor(() => expect(mocks.locals).toHaveBeenCalledWith(
      expect.objectContaining({ q: "cement", mapping_status: "pending" }), expect.anything()));
  });
  it("shows empty, 403 and retryable error states", async () => {
    mocks.tasks.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mount();
    expect(await screen.findByText(/No mapping tasks match/)).toBeInTheDocument();
  });
  it("handles a 403 from the server without claiming authority", async () => {
    mocks.tasks.mockRejectedValue(new ApiError("FORBIDDEN", "Access denied", "cid403", undefined, 403));
    mount();
    expect(await screen.findByText("You don't have permission to view this.")).toBeInTheDocument();
  });
  it("handles transient API failures with retry and correlation ID", async () => {
    mocks.tasks.mockRejectedValue(new ApiError("UNKNOWN_ERROR", "Service unavailable", "cid500", undefined, 500));
    mount();
    expect(await screen.findByText("Service unavailable")).toBeInTheDocument();
    expect(screen.getByText("cid500")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Retry" }).length).toBeGreaterThan(0);
  });
});

describe("US-PRD-02/03 — explicit confirm, reject and conflict flows", () => {
  it("requires choosing an exact candidate and positive conversion before confirm", async () => {
    mount(); await selectTask();
    expect(screen.getByRole("button", { name: "Confirm mapping on server" })).toBeDisabled();
    fireEvent.click(screen.getByRole("radio"));
    fireEvent.change(screen.getByRole("textbox", { name: "Units to base" }), { target: { value: "40" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /I verified this mapping/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm mapping on server" }));
    await waitFor(() => expect(mocks.confirm).toHaveBeenCalledWith(12, { global_product_id: 123, units_to_base: "40" }));
    expect(await screen.findByText(/confirmed by server for future/)).toBeInTheDocument();
  });
  it("supports manual selection of a different global product, not a fake catalogue lookup", async () => {
    mount(); await selectTask();
    fireEvent.click(screen.getByRole("button", { name: "Choose other" }));
    expect(screen.getByText(/Global catalogue search is unavailable/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Existing global product ID" }), { target: { value: "222" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Units to base" }), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /I verified this mapping/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm mapping on server" }));
    await waitFor(() => expect(mocks.confirm).toHaveBeenCalledWith(12, { global_product_id: 222, units_to_base: "1" }));
  });
  it("prevents empty rejection reasons; only server success closes the task", async () => {
    mount(); await selectTask();
    fireEvent.click(screen.getByRole("button", { name: "Reject mapping" }));
    expect(screen.getByRole("button", { name: "Reject with reason" })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Reason for rejection" }), { target: { value: "Duplicate SKU evidence" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject with reason" }));
    await waitFor(() => expect(mocks.reject).toHaveBeenCalledWith(12, "Duplicate SKU evidence"));
    expect(await screen.findByText(/rejection recorded by server/)).toBeInTheDocument();
  });
  it("blocks N6 FRAGILE and invalid new global product", async () => {
    mount(); await selectTask();
    fireEvent.click(screen.getByRole("button", { name: "Create global" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Handling group" }), { target: { value: "N6" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "FRAGILE" }));
    expect(screen.getByText("N6 may not carry the FRAGILE flag.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm mapping on server" })).toBeDisabled();
  });
  it("fails closed on HTTP 409 conflict and reloads authoritative task", async () => {
    mocks.confirm.mockRejectedValue(new ApiError("VERSION_CONFLICT", "Mapping has changed", "cid409", undefined, 409));
    mount(); await selectTask();
    fireEvent.click(screen.getByRole("radio"));
    fireEvent.change(screen.getByRole("textbox", { name: "Units to base" }), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /I verified this mapping/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm mapping on server" }));
    expect(await screen.findByText(/may have changed concurrently/)).toBeInTheDocument();
    expect(screen.queryByText(/confirmed by server for future/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm mapping on server" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Reload server data" }));
    await waitFor(() => expect(mocks.task.mock.calls.length).toBeGreaterThan(1));
  });
  it("preserves current task when server rejects confirmation", async () => {
    mocks.confirm.mockRejectedValue(new ApiError("VALIDATION_ERROR", "Invalid conversion", "cid422", undefined, 422));
    mount(); await selectTask();
    fireEvent.click(screen.getByRole("radio"));
    fireEvent.change(screen.getByRole("textbox", { name: "Units to base" }), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /I verified this mapping/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm mapping on server" }));
    expect(await screen.findByText("Invalid conversion")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "SKU SE-NEW-77" })).toBeInTheDocument();
  });
  it("uses mobile-safe stacked layout and horizontally scrolling catalog table", async () => {
    mount(); await selectTask();
    expect(screen.getByRole("region", { name: "Mapping task queue" }).className).toContain("space-y-4");
    expect(within(screen.getByRole("region", { name: "Local product catalogue" }))
      .getByRole("table").parentElement?.className).toContain("overflow-x-auto");
  });
});
