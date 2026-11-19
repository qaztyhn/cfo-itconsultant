/** Isolated revenue screen tests: only the feature API is mocked. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { useAuthStore } from "../../app/store";
import type { AuthUser } from "../../api/contracts/auth";
import { Revenue } from "./Revenue";
import { RevenueChart } from "./RevenueChart";

const mocks = vi.hoisted(() => ({
  summary: vi.fn(), status: vi.fn(), daily: vi.fn(), locations: vi.fn(), orders: vi.fn(), exportCsv: vi.fn(),
}));
vi.mock("./revenueApi", async original => {
  const real = await original<typeof import("./revenueApi")>();
  return { ...real, getRevenueSummary: mocks.summary, getRevenueOrderStatus: mocks.status,
    getRevenueDaily: mocks.daily,
    getRevenueLocations: mocks.locations, getRevenueOrders: mocks.orders,
    downloadRevenueCsv: mocks.exportCsv };
});
const admin: AuthUser = { id: 1, employee_id: 10, name: null, roles: ["admin"],
  market: "SE", location_ids: [], locale: "en", kpi_scopes: [], owned_location_ids: [] };
const owner: AuthUser = { ...admin, id: 2, roles: ["sales"], employee_id: 20,
  owned_location_ids: [21], location_ids: [21] };
const business: AuthUser = { ...admin, id: 3, roles: ["viewer"], employee_id: 30,
  kpi_scopes: ["revenue_all"] };
const noAccess: AuthUser = { ...admin, id: 4, roles: ["dispatcher"], kpi_scopes: ["ops"] };
const summary = {
  period: { from: "2026-11-01", to: "2026-11-30" }, view: "store", location_id: null,
  currency: "SEK", recognised: "1284500.00", booked_not_delivered: "214300.00",
  orders_delivered: 41, avg_order_value: "31329.27", share_of_market_pct: 8.4,
};
const status = {
  period: { from: "2026-11-01", to: "2026-11-30" }, view: "store", location_id: null,
  currency: "SEK", total: { orders: 116, amount: "1569100.00" },
  groups: [
    { key: "approved", statuses: ["APPROVED"], date_basis: "committed_date", orders: 30, amount: "402100.00" },
    { key: "in_transit", statuses: ["DISPATCHED"], date_basis: "committed_date", orders: 6, amount: "88400.00" },
    { key: "completed", statuses: ["DELIVERED"], date_basis: "committed_date", orders: 72, amount: "1012600.00" },
    { key: "failed", statuses: ["FAILED"], date_basis: "committed_date", orders: 3, amount: "41000.00" },
    { key: "cancelled", statuses: ["CANCELLED"], date_basis: "cancelled_at", orders: 5, amount: "25000.00" },
  ],
};
const locations = { view: "store", currency: "SEK", rows: [
  { location_id: 21, code: "ST-021", name: "Store 021", orders_delivered: 41,
    recognised: "1284500.00", booked_not_delivered: "214300.00", share_pct: 8.4 },
]};
const daily = { currency: "SEK", points: [
  { day: "2026-11-01", recognised: "200.00", booked: "30.00" },
  { day: "2026-11-02", recognised: "300.00", booked: "50.00" },
]};
beforeEach(() => {
  mocks.summary.mockResolvedValue(summary);
  mocks.status.mockResolvedValue(status);
  mocks.daily.mockResolvedValue(daily);
  mocks.locations.mockResolvedValue(locations);
  mocks.orders.mockResolvedValue({
    items: [{ order_no: "SE-123", delivered_at: "2026-11-01T09:00:00Z", amount: "400.00",
      currency: "SEK", status: "DELIVERED", customer_name: "PRIVATE TEST CUSTOMER" }],
    page: 1, page_size: 25, total: 1,
  });
  mocks.exportCsv.mockResolvedValue(new Blob(["day,view\n"], { type: "text/csv" }));
});
afterEach(() => {
  useAuthStore.getState().clearAuth();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});
function mount(user: AuthUser) {
  useAuthStore.getState().setAuth(
    { access_token: "test-token", token_type: "bearer", expires_in: 28800, user }, "test@cfo.demo");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><Revenue /></QueryClientProvider>);
}
describe("US-REV-01 AC1/AC4/AC9 — role and privacy boundaries", () => {
  it("blocks unauthorised roles without loading any report", () => {
    mount(noAccess);
    expect(screen.getByText("You do not have access to revenue.")).toBeInTheDocument();
    expect(mocks.summary).not.toHaveBeenCalled();
  });
  it("Business owner sees five KPIs and never a customer-name column or value", async () => {
    mount(business);
    expect(await screen.findByText("Recognised revenue")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Revenue KPI cards")).getAllByText(/Share of market/)).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Store 021" }));
    await screen.findByText("SE-123");
    expect(screen.queryByText("PRIVATE TEST CUSTOMER")).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Customer" })).not.toBeInTheDocument();
  });
  it("owner is locked to their own store and does not see market share", async () => {
    mount(owner);
    await screen.findByText("Recognised revenue");
    expect(screen.getByRole("button", { name: "By warehouse" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Location filter" })).toBeDisabled();
    expect(screen.queryByText("Share of market")).not.toBeInTheDocument();
    expect(mocks.summary).toHaveBeenCalledWith(expect.objectContaining({ view: "store", location_id: 21 }), expect.anything());
  });
});
describe("US-REV-01 AC5–AC8 — filters, chart, CSV and errors", () => {
  it("switches views without combining store/warehouse totals", async () => {
    mount(admin);
    await screen.findByText("Recognised revenue");
    fireEvent.click(screen.getByRole("button", { name: "By warehouse" }));
    await waitFor(() => expect(mocks.summary).toHaveBeenCalledWith(
      expect.objectContaining({ view: "warehouse" }), expect.anything()));
    expect(await screen.findByRole("heading", { name: /By warehouse · locations/ })).toBeInTheDocument();
  });
  it("filters dates and blocks invalid ranges locally", async () => {
    mount(admin);
    await screen.findByText("Recognised revenue");
    fireEvent.change(screen.getByLabelText("From date"), { target: { value: "2026-11-30" } });
    fireEvent.change(screen.getByLabelText("To date"), { target: { value: "2026-11-01" } });
    expect(screen.getByText(/Select both dates/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("To date"), { target: { value: "2026-12-02" } });
    await waitFor(() => expect(mocks.summary).toHaveBeenCalledWith(
      expect.objectContaining({ from: "2026-11-30", to: "2026-12-02" }), expect.anything()));
  });
  it("displays no delivered orders and zero-point chart states", async () => {
    mocks.summary.mockResolvedValue({ ...summary, recognised: "0.00", orders_delivered: 0 });
    mocks.daily.mockResolvedValue({ currency: "SEK", points: [] });
    mount(admin);
    expect(await screen.findByText(/No delivered orders in this period/)).toBeInTheDocument();
    expect(screen.getByText("No daily revenue data in this period.")).toBeInTheDocument();
  });
  it("renders 403 and 404 distinctly and prevents sensitive content", async () => {
    mocks.summary.mockRejectedValue(new ApiError("FORBIDDEN", "Denied", "cid403", undefined, 403));
    mount(admin);
    expect(await screen.findByText("You do not have access to revenue.")).toBeInTheDocument();
  });
  it("renders 404 location-not-found state", async () => {
    mocks.summary.mockRejectedValue(new ApiError("NOT_FOUND", "No location", "cid404", undefined, 404));
    mount(admin);
    expect(await screen.findByText(/Location not found or outside/)).toBeInTheDocument();
  });
  it("shows a retryable server error with correlation ID", async () => {
    mocks.summary.mockRejectedValue(new ApiError("INTERNAL_ERROR", "Service unavailable", "cid500", undefined, 500));
    mount(admin);
    expect(await screen.findByText("Service unavailable")).toBeInTheDocument();
    expect(screen.getByText("cid500")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
  it("exports the exact active view through the audited CSV endpoint", async () => {
    mount(admin);
    await screen.findByText("Recognised revenue");
    const createUrl = vi.fn(() => "blob:revenue-test");
    const revokeUrl = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeUrl });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() => expect(mocks.exportCsv).toHaveBeenCalledWith(expect.objectContaining({ view: "store" })));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(revokeUrl).toHaveBeenCalledWith("blob:revenue-test");
  });
  it("uses responsive cards and horizontally scrollable tables", async () => {
    mount(admin);
    await screen.findByText("Recognised revenue");
    expect(screen.getByLabelText("Revenue KPI cards").className).toContain("grid-cols-1");
    expect(screen.getByRole("region", { name: "Location breakdown" }).querySelector(".overflow-x-auto")).not.toBeNull();
  });
  it("gives an accessible chart and text alternative, without totals aggregation", () => {
    render(<RevenueChart data={daily} />);
    expect(screen.getByRole("img", { name: /Recognised daily revenue bars/ })).toBeInTheDocument();
    expect(screen.getByText("Accessible daily figures")).toBeInTheDocument();
  });
  it("US-REV-02 AC1/AC5 renders server total, recognised revenue and five keyed status cards", async () => {
    mount(admin);
    const cards = await screen.findByRole("region", { name: "Order status groups" });
    expect(within(screen.getByLabelText("Primary order and revenue metrics")).getByText("116")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Primary order and revenue metrics"))
      .getByText("Recognised revenue").nextElementSibling?.getAttribute("title"))
      .toBe("1\u202f284\u202f500 SEK");
    expect(within(cards).getAllByRole("button")).toHaveLength(5);
    expect(within(cards).getByRole("button", { name: "Đã duyệt: 30 orders" })).toBeInTheDocument();
    expect(within(cards).getByText(/402 100 SEK/)).toBeInTheDocument();
    expect(screen.getByText(/Đã hủy: 4\.3%/)).toBeInTheDocument();
  });
  it("US-REV-02 AC1 shows five zero cards and no NaN/Infinity in an empty period", async () => {
    mocks.status.mockResolvedValue({
      ...status, total: { orders: 0, amount: "0.00" },
      groups: status.groups.map(group => ({ ...group, orders: 0, amount: "0.00" })),
    });
    mount(admin);
    const cards = await screen.findByRole("region", { name: "Order status groups" });
    expect(within(cards).getAllByRole("button", { name: /: 0 orders$/ })).toHaveLength(5);
    expect(within(cards).getByText(/Không có đơn trong kỳ/)).toBeInTheDocument();
    expect(within(cards).queryByRole("img")).not.toBeInTheDocument();
    expect(cards.textContent).not.toMatch(/NaN|Infinity/);
  });
  it("US-REV-02 AC6 holds group selection while all locations and resets page on group change", async () => {
    mount(admin);
    await screen.findByRole("button", { name: "Đã duyệt: 30 orders" });
    fireEvent.click(screen.getByRole("button", { name: "Đã duyệt: 30 orders" }));
    expect(screen.getByText(/Chọn một địa điểm được phép/)).toBeInTheDocument();
    expect(mocks.orders).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Location filter"), { target: { value: "21" } });
    await waitFor(() => expect(mocks.orders).toHaveBeenCalledWith(
      expect.objectContaining({ location_id: 21, from: "2026-11-01", to: "2026-11-30" }),
      1, expect.anything(), "approved",
    ));
    fireEvent.click(screen.getByRole("button", { name: "Đang vận chuyển: 6 orders" }));
    await waitFor(() => expect(mocks.orders).toHaveBeenCalledWith(
      expect.objectContaining({ location_id: 21 }), 1, expect.anything(), "in_transit",
    ));
  });
});
