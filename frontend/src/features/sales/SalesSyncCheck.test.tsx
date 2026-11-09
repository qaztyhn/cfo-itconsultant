/** Contract-based component tests; no shared handler or POS source modifications. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { AuthUser } from "../../api/contracts/auth";
import { useAuthStore } from "../../app/store";
import { SalesSyncCheck } from "./SalesSyncCheck";

const mock = vi.hoisted(() => ({
  sync: vi.fn(), plan: vi.fn(), confirm: vi.fn(), ack: vi.fn(), key: vi.fn(),
}));
vi.mock("./salesSyncApi", async importOriginal => {
  const actual = await importOriginal<typeof import("./salesSyncApi")>();
  return { ...actual, syncAndCheck: mock.sync, requestDefaultPlan: mock.plan,
    confirmStandardPlan: mock.confirm, acknowledgeRouting: mock.ack, newRetryKey: mock.key };
});
const sales: AuthUser = {
  id: 12, employee_id: 14, name: null, roles: ["sales"], market: "SE",
  locale: "en", location_ids: [21], kpi_scopes: [], owned_location_ids: [],
};
const syncResult = { external_ref: "POS-123", routing_status: "cfo", order_id: 44,
  sync_status: "synced", source_version: 2, already_decided: false };
const checks = {
  stock: { passed: true, code: "STOCK_OK" }, preparation: { passed: true, code: "PREP_OK" },
  truck: { passed: true, code: "TRUCK_OK" }, site_date: { passed: true, code: "DATE_OK" },
  safety: { passed: true, code: "SAFETY_OK" },
};
const run = {
  id: 500, order_id: 44, run_no: 1, kind: "initial", result: "feasible",
  reserve_class: "safe", hold_expires_at: "2027-11-30T14:00:00Z", hold_extensions: 0, sales_approvable: true,
  plans: [{ id: 55, rank: 1, status: "proposed", target_date: "2027-11-30", eta_at: "2027-11-30T09:00:00Z",
    vehicle_count: 1, vehicles: [{ seq: 1, vehicle: { id: 1, code: "TRK", name: "Truck",
      capacity_kg: "6000", capacity_m3: "30" }, load_kg: "500", load_m3: "3",
      loading_start_at: "2027-11-30T06:00:00Z", depart_at: "2027-11-30T07:00:00Z",
      eta_at: "2027-11-30T09:00:00Z" }], checks }],
};
beforeEach(() => {
  mock.sync.mockResolvedValue(syncResult);
  mock.plan.mockResolvedValue(run);
  mock.ack.mockResolvedValue({ status: "recorded" });
  mock.confirm.mockResolvedValue({ order: { status: "APPROVED" },
    plan: { id: 55, status: "approved" }, trip_ids: [], notifications: [] });
  let n = 0;
  mock.key.mockImplementation(() => `test-idempotency-${++n}`);
});
afterEach(() => { useAuthStore.getState().clearAuth(); vi.clearAllMocks(); });
function mount(user: AuthUser = sales) {
  useAuthStore.getState().setAuth({
    access_token: "synthetic-test", token_type: "bearer", expires_in: 28_800, user,
  }, "test@example.invalid");
  return render(<MemoryRouter><QueryClientProvider client={new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })}><SalesSyncCheck /></QueryClientProvider></MemoryRouter>);
}
function search(ref = "POS-123") {
  fireEvent.change(screen.getByRole("textbox", { name: "External POS order reference" }), { target: { value: ref } });
  fireEvent.click(screen.getByRole("button", { name: "Sync & check routing" }));
}
async function eligibleFlow() {
  search();
  await screen.findByText("Synced · CFO routing confirmed.");
  fireEvent.click(screen.getByRole("button", { name: "Check feasibility" }));
  await screen.findByRole("heading", { name: "Feasible — not confirmed" });
}
describe("US-SRC/Sales — Sync & check workflow", () => {
  it("blocks non-sales role, with no network operations", () => {
    mount({ ...sales, roles: ["dispatcher"] });
    expect(screen.getByRole("alert")).toHaveTextContent("Sales access required");
    expect(mock.sync).not.toHaveBeenCalled();
  });
  it("starts empty with a disabled action and meaningful field label", () => {
    mount();
    expect(screen.getByRole("heading", { name: "Sync & confirm delivery" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync & check routing" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "External POS order reference" })).toHaveAttribute("autocomplete", "off");
  });
  it("sends only a POS reference and does not automatically plan or approve", async () => {
    mount();
    search();
    expect(await screen.findByText("Synced · CFO routing confirmed.")).toBeInTheDocument();
    expect(mock.sync).toHaveBeenCalledWith("POS-123", "test-idempotency-1");
    expect(mock.plan).not.toHaveBeenCalled();
    expect(mock.confirm).not.toHaveBeenCalled();
  });
  it("shows syncing and disables duplicate submission", async () => {
    mock.sync.mockImplementation(() => new Promise(() => undefined));
    mount();
    search();
    expect(screen.getByRole("button", { name: "Syncing and checking…" })).toBeDisabled();
    expect(screen.getByRole("status", { busy: true })).toBeInTheDocument();
  });
  it("legacy remains immutable, displays SKU evidence and never calls planning", async () => {
    mock.sync.mockResolvedValue({ ...syncResult, routing_status: "legacy", already_decided: true,
      missing_confirmed_skus: [{ local_sku: "SE-UNMAPPED-1", status: "pending" }] });
    mount(); search();
    expect(await screen.findByText(/Legacy routing —/)).toBeInTheDocument();
    expect(screen.getByText(/Already decided/)).toBeInTheDocument();
    expect(screen.getByText(/SE-UNMAPPED-1/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check feasibility" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge legacy handover" }));
    await waitFor(() => expect(mock.ack).toHaveBeenCalledWith("POS-123", "legacy_acknowledged", undefined));
    expect(mock.plan).not.toHaveBeenCalled();
  });
  it("unresolved does not default to legacy or CFO and allows retry", async () => {
    mock.sync.mockResolvedValue({ ...syncResult, routing_status: "unresolved", order_id: null, retry_after_s: 15 });
    mount(); search();
    expect(await screen.findByText(/Unresolved —/)).toBeInTheDocument();
    expect(screen.getByText("Server retry guidance: 15 seconds")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check feasibility" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry sync & check" }));
    await waitFor(() => expect(mock.sync).toHaveBeenCalledTimes(2));
    expect(mock.sync.mock.calls[0][1]).toBe(mock.sync.mock.calls[1][1]);
  });
  it("fails closed when any one of five checks is absent despite sales_approvable", async () => {
    mock.plan.mockResolvedValue({ ...run, plans: [{ ...run.plans[0], checks: { ...checks, safety: undefined } }] });
    mount(); await eligibleFlow();
    expect(screen.getByText(/Not eligible for Sales confirmation/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm standard delivery plan" })).not.toBeInTheDocument();
    expect(mock.confirm).not.toHaveBeenCalled();
  });
  it("requires deliberate confirm and reports WMS ACK not yet verified", async () => {
    mount(); await eligibleFlow();
    expect(mock.confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm standard delivery plan" }));
    await waitFor(() => expect(mock.confirm).toHaveBeenCalledWith(55, "test-idempotency-2"));
    expect(await screen.findByText(/CFO approval recorded by the server/)).toBeInTheDocument();
    expect(screen.getByText(/CFO approval recorded by the server/)).toHaveTextContent("WMS reservation ACK");
  });
  it("never shows confirmed on an invalid approval response", async () => {
    mock.confirm.mockResolvedValue({ order: { status: "PLANNED" }, plan: { id: 55, status: "proposed" } });
    mount(); await eligibleFlow();
    fireEvent.click(screen.getByRole("button", { name: "Confirm standard delivery plan" }));
    expect(await screen.findByText(/Confirmation response was not an approved-plan commit/)).toBeInTheDocument();
    expect(screen.queryByText(/CFO approval recorded by the server/)).not.toBeInTheDocument();
  });
  it("records manual-start exceptions with mandatory reason and does not flip routing", async () => {
    mount(); search(); await screen.findByText("Synced · CFO routing confirmed.");
    expect(screen.getByRole("button", { name: "Report manual fulfilment started" })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Manual fulfilment reason" }), {
      target: { value: "Manual packing began before CFO check" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Report manual fulfilment started" }));
    await waitFor(() => expect(mock.ack).toHaveBeenCalledWith("POS-123", "manual_started",
      "Manual packing began before CFO check"));
    expect(mock.plan).not.toHaveBeenCalled();
  });
  it("handles 403 404 409 422 and 503 without inventing a routing outcome", async () => {
    for (const status of [403, 404, 409, 422, 503]) {
      mock.sync.mockRejectedValueOnce(new ApiError(status === 403 ? "FORBIDDEN" : "SYNC_ERROR",
        "Operation could not be completed", `cid-${status}`, undefined, status));
      const view = mount();
      search();
      expect(await screen.findByRole("heading", { name: status === 403 ? "Permission denied" : status === 404 ? "Order not found or outside your store" : status === 409 ? "Conflict — refresh before proceeding" : status === 422 ? "Invalid order or request" : "Source or CFO unavailable" })).toBeInTheDocument();
      expect(screen.getByText(`cid-${status}`)).toBeInTheDocument();
      expect(screen.queryByText("Synced · CFO routing confirmed.")).not.toBeInTheDocument();
      expect(screen.queryByText(/Delivery confirmed/)).not.toBeInTheDocument();
      view.unmount();
      useAuthStore.getState().clearAuth();
    }
  });
  it("reuses the same Idempotency-Key on a failed sync retry", async () => {
    mock.sync.mockRejectedValueOnce(new ApiError("SYNC_IN_PROGRESS", "Still syncing", "cid", undefined, 409));
    mount(); search();
    expect(await screen.findByRole("heading", { name: "Conflict — refresh before proceeding" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mock.sync).toHaveBeenCalledTimes(2));
    expect(mock.sync.mock.calls[0][1]).toEqual(mock.sync.mock.calls[1][1]);
  });
  it("reuses the approve Idempotency-Key on a 409 retried approval", async () => {
    mock.confirm.mockRejectedValueOnce(new ApiError("RESOURCE_CONFLICT", "Resource conflict", "cid", undefined, 409));
    mount(); await eligibleFlow();
    fireEvent.click(screen.getByRole("button", { name: "Confirm standard delivery plan" }));
    expect(await screen.findByRole("heading", { name: "Conflict — refresh before proceeding" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mock.confirm).toHaveBeenCalledTimes(2));
    expect(mock.confirm.mock.calls[0][1]).toBe(mock.confirm.mock.calls[1][1]);
  });
});
