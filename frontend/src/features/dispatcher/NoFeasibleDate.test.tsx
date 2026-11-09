/** Feature-local contract tests. No shared MSW/router changes. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { AuthUser } from "../../api/contracts/auth";
import { useAuthStore } from "../../app/store";
import { NoFeasibleDate } from "./NoFeasibleDate";

const mock = vi.hoisted(() => ({
  run: vi.fn(), transfers: vi.fn(), history: vi.fn(), record: vi.fn(),
  overview: vi.fn(),
}));
vi.mock("./noFeasibleDateApi", async importOriginal => {
  const actual = await importOriginal<typeof import("./noFeasibleDateApi")>();
  return { ...actual, fetchInfeasibleRun: mock.run, fetchVerifiedTransfers: mock.transfers,
    fetchNegotiations: mock.history, recordNegotiation: mock.record };
});
vi.mock("../../api/integration", async importOriginal => {
  const actual = await importOriginal<typeof import("../../api/integration")>();
  return { ...actual, fetchIntegrationOverview: mock.overview };
});
const dispatcher: AuthUser = {
  id: 1, employee_id: 1, name: null, roles: ["dispatcher"], market: "SE",
  location_ids: [], locale: "en", kpi_scopes: [], owned_location_ids: [],
};
const run = {
  id: 701, order_id: 42, run_no: 1, kind: "initial", result: "infeasible",
  reserve_class: null, hold_expires_at: null, hold_extensions: 0, plans: [],
  failed_check: "stock", earliest_feasible_date: "2026-11-12",
  rejected_candidates: [{ warehouse_id: 3, failed_check: "stock", code: "STOCK_SHORT",
    detail: { message: "No confirmed goods by the requested date." } }],
};
beforeEach(() => {
  mock.run.mockResolvedValue(run);
  mock.transfers.mockResolvedValue({ items: [] });
  mock.history.mockResolvedValue({ items: [] });
  mock.record.mockResolvedValue({ id: 84 });
  mock.overview.mockResolvedValue({ sources: [{ name: "WMS", data_as_of: new Date().toISOString() }], stale: false });
});
afterEach(() => {
  useAuthStore.getState().clearAuth();
  vi.clearAllMocks();
});
function mount(user: AuthUser = dispatcher) {
  useAuthStore.getState().setAuth({
    access_token: "synthetic-test-token", token_type: "bearer", expires_in: 28000, user,
  }, "test@example.invalid");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<MemoryRouter initialEntries={["/dispatcher/exceptions/701"]}>
    <QueryClientProvider client={client}>
      <Routes><Route path="/dispatcher/exceptions/:runId" element={<NoFeasibleDate />} /></Routes>
    </QueryClientProvider>
  </MemoryRouter>);
}

describe("US-PLN-07 AC1/2 — No Feasible Date diagnostics", () => {
  it("refuses a Sales role before any API read or write", () => {
    mount({ ...dispatcher, roles: ["sales"] });
    expect(screen.getByRole("alert")).toHaveTextContent("Dispatcher access required.");
    expect(mock.run).not.toHaveBeenCalled();
  });
  it("renders earliest date only when supplied and checks missing gates as UNKNOWN", async () => {
    mount();
    expect(await screen.findByText("2026-11-12")).toBeInTheDocument();
    const table = within(screen.getByRole("region", { name: "Warehouse feasibility checks" })).getByRole("table");
    expect(within(table).getByRole("row", { name: /Warehouse #3/ })).toHaveTextContent("✕ FAIL");
    expect(within(table).getAllByText(/UNKNOWN/)).toHaveLength(4);
    expect(screen.getByText(/Stock and shortage are UNKNOWN/)).toBeInTheDocument();
    expect(screen.getByText(/Search horizon cannot be verified/)).toBeInTheDocument();
    expect(mock.record).not.toHaveBeenCalled();
  });
  it("renders verified dates, all five API checks, stock and shortage, transfers without execution", async () => {
    mock.run.mockResolvedValue({
      ...run, dates_searched: [{ date: "2026-11-09", result: "requested" },
        { date: "2026-11-12", result: "first_feasible" }],
      per_warehouse_checks: [{ warehouse: "Malmö DC", stock: { passed: false, code: "STOCK_SHORT" },
        preparation: { passed: true, code: "PREP_OK" }, truck: null, site_date: null, safety: null }],
      stock_matrix: { date: "2026-11-09", lines: [{
        local_sku: "S-25", name: "Synthetic bag", unit: "bag",
        needed: 80, usable: { MLM: 30, GBG: null },
        inbound: { MLM: [{ qty: 100, eta: "2026-11-11" }] },
      }] },
    });
    mock.transfers.mockResolvedValue({ items: [{ from_warehouse_id: 1, to_warehouse_id: 2,
      lead_days: 2, distance_km: 19, lines: [{ global_product_id: 4, qty: "50" }] }] });
    mount();
    expect(await screen.findByText("Malmö DC")).toBeInTheDocument();
    expect(screen.getByText("First feasible")).toBeInTheDocument();
    expect(screen.getByText("Short 50")).toBeInTheDocument();
    expect(screen.getByText("GBG: Unknown")).toBeInTheDocument();
    expect(await screen.findByText(/Source: Warehouse #1/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve transfer/ })).not.toBeInTheDocument();
  });
  it("does not invent earliest feasible date on unverified response", async () => {
    mock.run.mockResolvedValue({ ...run, earliest_feasible_date: null, rejected_candidates: [] });
    mount();
    expect(await screen.findByText("Not verified within the search horizon")).toBeInTheDocument();
    expect(screen.getByText("Per-warehouse feasibility evidence is unavailable.")).toBeInTheDocument();
  });
  it("shows stale warning when freshness is unavailable but still shows verified run diagnostics", async () => {
    mock.overview.mockRejectedValue(new ApiError("NOT_FOUND", "Unavailable", "fresh-404", undefined, 404));
    mount();
    expect(await screen.findByText(/Data freshness unknown or stale/)).toBeInTheDocument();
    expect(screen.getByText("2026-11-12")).toBeInTheDocument();
  });
  it("shows loading and correlatable API errors with Retry", async () => {
    mock.run.mockRejectedValue(new ApiError("SERVER_ERROR", "Planning unavailable", "cid-500", undefined, 500));
    mount();
    expect(await screen.findByText("Planning unavailable")).toBeInTheDocument();
    expect(screen.getByText("cid-500")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
  it("renders a skeleton while the planning request is loading", async () => {
    mock.run.mockImplementation(() => new Promise(() => undefined));
    mount();
    expect(screen.getByRole("status", { busy: true })).toBeInTheDocument();
    expect(screen.queryByText("2026-11-12")).not.toBeInTheDocument();
  });
  it("renders an empty, non-actionable state when the run is now feasible", async () => {
    mock.run.mockResolvedValue({ ...run, result: "feasible", plans: [] });
    mount();
    expect(await screen.findByText("This planning run is not an infeasible result.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record customer outcome" })).not.toBeInTheDocument();
  });
  it("does not allow retry on server 403", async () => {
    mock.run.mockRejectedValue(new ApiError("FORBIDDEN", "denied", "cid-403", undefined, 403));
    mount();
    expect(await screen.findByText("You don't have permission to view this.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});
describe("US-PLN-07 AC2–AC5 — explicit customer agreement", () => {
  it("blocks empty reason, date or contact; records a real agreement without automatically changing the order", async () => {
    mount();
    await screen.findByText("2026-11-12");
    const submit = screen.getByRole("button", { name: "Record customer outcome" });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Actual contact time"), { target: { value: "2026-11-08T12:30" } });
    fireEvent.change(screen.getByLabelText("Negotiation reason / contact note"), { target: { value: "Customer explicitly agreed" } });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    await waitFor(() => expect(mock.record).toHaveBeenCalledWith(42, expect.objectContaining({
      proposed_date: "2026-11-12", outcome: "agreed", channel: "phone", note: "Customer explicitly agreed",
    })));
    expect(await screen.findByText(/Customer outcome recorded by server: agreed/)).toBeInTheDocument();
    expect(screen.getByText(/original order date remains unchanged/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run new plan for agreed date" })).not.toBeInTheDocument();
  });
  it("records declined or unreachable without replanning or cancellation", async () => {
    mount();
    await screen.findByText("2026-11-12");
    fireEvent.change(screen.getByLabelText("Customer outcome"), { target: { value: "unreachable" } });
    fireEvent.change(screen.getByLabelText("Actual contact time"), { target: { value: "2026-11-08T12:30" } });
    fireEvent.change(screen.getByLabelText("Negotiation reason / contact note"), { target: { value: "No response" } });
    fireEvent.click(screen.getByRole("button", { name: "Record customer outcome" }));
    expect(await screen.findByText(/Follow-up reminder is server-managed/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run new plan for agreed date" })).not.toBeInTheDocument();
  });
  it("keeps the negotiation form on API failure, without a false success", async () => {
    mock.record.mockRejectedValue(new ApiError("VERSION_CONFLICT", "Order changed", "cid-409", undefined, 409));
    mount();
    await screen.findByText("2026-11-12");
    fireEvent.change(screen.getByLabelText("Actual contact time"), { target: { value: "2026-11-08T12:30" } });
    fireEvent.change(screen.getByLabelText("Negotiation reason / contact note"), { target: { value: "Discussed" } });
    fireEvent.click(screen.getByRole("button", { name: "Record customer outcome" }));
    expect(await screen.findByText("Order changed")).toBeInTheDocument();
    expect(screen.queryByText(/Customer outcome recorded by server/)).not.toBeInTheDocument();
  });
});
