/** T30 US-REV-02 / A16b: real client transport and UI interaction intercepted with MSW.
 * Unlike Revenue.test.tsx these tests do NOT mock the Revenue API client.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { useAuthStore } from "../../app/store";
import type { AuthUser } from "../../api/contracts/auth";
import { API_BASE_URL } from "../../api/config";
import { Revenue } from "./Revenue";
import { getRevenueOrderStatus, getRevenueOrders } from "./revenueApi";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => { server.resetHandlers(); useAuthStore.getState().clearAuth(); });
afterAll(() => server.close());

const admin: AuthUser = {
  id: 10, employee_id: 10, name: null, roles: ["admin"], market: "SE",
  location_ids: [], owned_location_ids: [], locale: "en", kpi_scopes: [],
};
const owner: AuthUser = {
  ...admin, id: 21, employee_id: 21, roles: ["sales"], location_ids: [21],
  owned_location_ids: [21],
};
const business: AuthUser = { ...admin, id: 30, roles: ["viewer"], kpi_scopes: ["revenue_all"] };
const counts = { approved: 30, in_transit: 6, completed: 72, failed: 3, cancelled: 5 };
const amounts = {
  approved: "402100.00", in_transit: "88400.00", completed: "1012600.00",
  failed: "41000.00", cancelled: "25000.00",
};
const keys = ["approved", "in_transit", "completed", "failed", "cancelled"] as const;
const calls: { path: string; params: URLSearchParams }[] = [];
function period(url: URL) {
  return { from: url.searchParams.get("from") ?? "2026-11-01",
    to: url.searchParams.get("to") ?? "2026-11-30" };
}
function spy(url: URL) {
  calls.push({ path: url.pathname, params: new URLSearchParams(url.searchParams) });
}
function stubEndpoints() {
  server.use(
    http.get(`${API_BASE_URL}/revenue/summary`, ({ request }) => {
      const url = new URL(request.url); spy(url);
      return HttpResponse.json({
        period: period(url), view: url.searchParams.get("view"), location_id: Number(url.searchParams.get("location_id")) || null,
        currency: "SEK", recognised: "1284500.00", booked_not_delivered: "214300.00",
        orders_delivered: 41, avg_order_value: "31329.27", share_of_market_pct: 8.4,
      });
    }),
    http.get(`${API_BASE_URL}/revenue/order-status`, ({ request }) => {
      const url = new URL(request.url); spy(url);
      return HttpResponse.json({
        period: period(url), view: url.searchParams.get("view"),
        location_id: Number(url.searchParams.get("location_id")) || null,
        currency: "SEK", total: { orders: 116, amount: "1569100.00" },
        groups: keys.map(key => ({
          key, statuses: [key === "approved" ? "APPROVED" : key.toUpperCase()],
          date_basis: key === "cancelled" ? "cancelled_at" : "committed_date",
          orders: counts[key], amount: amounts[key],
        })),
      });
    }),
    http.get(`${API_BASE_URL}/revenue/daily`, ({ request }) => {
      spy(new URL(request.url));
      return HttpResponse.json({ currency: "SEK", points: [] });
    }),
    http.get(`${API_BASE_URL}/revenue/by-location`, ({ request }) => {
      const url = new URL(request.url); spy(url);
      return HttpResponse.json({
        view: url.searchParams.get("view"), currency: "SEK",
        rows: [{ location_id: 21, code: "ST-021", name: "Store 021", orders_delivered: 41,
          recognised: "1284500.00", booked_not_delivered: "214300.00", share_pct: 8.4 },
          { location_id: 31, code: "WH-031", name: "Warehouse 031", orders_delivered: 0,
            recognised: "0.00", booked_not_delivered: "0.00", share_pct: 0 }],
      });
    }),
    http.get(`${API_BASE_URL}/revenue/orders`, ({ request }) => {
      const url = new URL(request.url); spy(url);
      const key = url.searchParams.get("status_group") as keyof typeof counts | null;
      const page = Number(url.searchParams.get("page") ?? 1);
      return HttpResponse.json({
        items: [{ order_no: `SE-T30-${key ?? "ALL"}-P${page}`,
          delivered_at: null, amount: "300.00", currency: "SEK",
          status: key === "approved" ? "APPROVED" : "DISPATCHED",
          customer_name: "PRIVATE SYNTHETIC CUSTOMER" }],
        page, page_size: 25, total: key ? counts[key] : 116,
      });
    }),
  );
}
function mount(user: AuthUser = admin) {
  useAuthStore.getState().setAuth(
    { access_token: "synthetic-test-token", token_type: "bearer", expires_in: 3600, user }, "synthetic@cfo.test");
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><Revenue /></QueryClientProvider>);
}
function requests(path: string) {
  return calls.filter(c => c.path === `/api/v1/revenue/${path}`);
}
function last(path: string) {
  return requests(path).at(-1)?.params;
}
describe("US-REV-02 AC1–AC6 T30 real transport through MSW", () => {
  afterEach(() => { calls.length = 0; });
  it("API clients send exactly §19.11 filters for status and orders without a synthetic date default", async () => {
    stubEndpoints();
    const value = await getRevenueOrderStatus({ view: "warehouse", from: "2026-11-01", to: "2026-11-30",
      location_id: 31 });
    expect(value.groups).toHaveLength(5);
    expect(last("order-status")?.get("view")).toBe("warehouse");
    expect(last("order-status")?.get("from")).toBe("2026-11-01");
    expect(last("order-status")?.get("to")).toBe("2026-11-30");
    expect(last("order-status")?.get("location_id")).toBe("31");
    const list = await getRevenueOrders(
      { view: "warehouse", location_id: 31, from: value.period.from, to: value.period.to },
      2, undefined, "cancelled",
    );
    expect(list.total).toBe(5);
    expect(last("orders")?.get("status_group")).toBe("cancelled");
    expect(last("orders")?.get("page")).toBe("2");
    expect(last("orders")?.get("page_size")).toBe("25");
    expect(last("orders")?.get("location_id")).toBe("31");
    expect(last("orders")?.get("view")).toBe("warehouse");
  });
  it("uses server recognised and total.orders from distinct APIs, including exact default filters", async () => {
    stubEndpoints();
    mount();
    expect(await screen.findByRole("button", { name: "Đã duyệt: 30 orders" })).toBeInTheDocument();
    expect(screen.getByLabelText("Primary order and revenue metrics").textContent).toContain("116");
    expect(screen.getByLabelText("Primary order and revenue metrics").textContent).toContain("1\u202f284\u202f500 SEK");
    expect(requests("summary")).toHaveLength(1);
    expect(requests("order-status")).toHaveLength(1);
    expect(last("summary")?.get("view")).toBe("store");
    expect(last("order-status")?.has("from")).toBe(false);
    expect(last("order-status")?.has("to")).toBe(false);
    expect(last("order-status")?.has("location_id")).toBe(false);
  });
  it("holds group while all locations; uses backend default period and specific location for paginated API", async () => {
    stubEndpoints(); mount();
    fireEvent.click(await screen.findByRole("button", { name: "Đã duyệt: 30 orders" }));
    expect(screen.getByText(/Chọn một địa điểm được phép/)).toBeInTheDocument();
    expect(requests("orders")).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Location filter"), { target: { value: "21" } });
    await waitFor(() => expect(requests("orders").length).toBeGreaterThan(0));
    expect(last("orders")?.get("status_group")).toBe("approved");
    expect(last("orders")?.get("location_id")).toBe("21");
    expect(last("orders")?.get("from")).toBe("2026-11-01");
    expect(last("orders")?.get("to")).toBe("2026-11-30");
    expect(last("orders")?.get("page")).toBe("1");
    expect(screen.getByRole("heading", { name: /Đã duyệt · store: Store 021/ })).toBeInTheDocument();
    expect(await screen.findByText("SE-T30-approved-P1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(last("orders")?.get("page")).toBe("2"));
    expect(await screen.findByText("SE-T30-approved-P2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Đang vận chuyển: 6 orders" }));
    await waitFor(() => expect(last("orders")?.get("status_group")).toBe("in_transit"));
    expect(last("orders")?.get("page")).toBe("1");
    expect(await screen.findByText("SE-T30-in_transit-P1")).toBeInTheDocument();
    expect(screen.queryByText("SE-T30-approved-P2")).not.toBeInTheDocument();
  });
  it("passes new view/date/location to status API, never mixing warehouse/store scopes", async () => {
    stubEndpoints(); mount();
    await screen.findByRole("button", { name: "Đã duyệt: 30 orders" });
    fireEvent.change(screen.getByLabelText("From date"), { target: { value: "2026-11-05" } });
    fireEvent.change(screen.getByLabelText("To date"), { target: { value: "2026-11-19" } });
    await waitFor(() => expect(last("order-status")?.get("from")).toBe("2026-11-05"));
    await waitFor(() => expect(last("order-status")?.get("to")).toBe("2026-11-19"));
    fireEvent.click(screen.getByRole("button", { name: "By warehouse" }));
    await waitFor(() => expect(last("order-status")?.get("view")).toBe("warehouse"));
    expect(last("order-status")?.has("location_id")).toBe(false);
    fireEvent.change(screen.getByLabelText("Location filter"), { target: { value: "31" } });
    await waitFor(() => expect(last("order-status")?.get("location_id")).toBe("31"));
  });
  it("owner cannot choose other locations; Business owner never renders customer names", async () => {
    stubEndpoints(); mount(owner);
    fireEvent.click(await screen.findByRole("button", { name: "Đã duyệt: 30 orders" }));
    expect(screen.getByLabelText("Location filter")).toBeDisabled();
    await waitFor(() => expect(last("orders")?.get("location_id")).toBe("21"));
    expect(last("order-status")?.get("location_id")).toBe("21");
  });
  it("Business owner hides customer column and values even when API includes customer_name", async () => {
    stubEndpoints(); mount(business);
    fireEvent.click(await screen.findByRole("button", { name: "Đã duyệt: 30 orders" }));
    fireEvent.change(screen.getByLabelText("Location filter"), { target: { value: "21" } });
    expect(await screen.findByText("SE-T30-approved-P1")).toBeInTheDocument();
    expect(screen.queryByText("PRIVATE SYNTHETIC CUSTOMER")).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Customer" })).not.toBeInTheDocument();
  });
});
