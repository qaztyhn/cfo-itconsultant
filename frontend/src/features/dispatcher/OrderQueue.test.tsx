import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchLocations } from "../../api/locations";
import { renderAt, signInAs, userByEmail } from "../../test/utils";
import { COUNTS_URL, ORDERS_URL, OVERVIEW_URL, useOrderQueueMsw } from "./orderQueue/testServer";

vi.mock("../../api/locations", () => ({ fetchLocations: vi.fn() }));

const server = useOrderQueueMsw();

beforeEach(() => {
  vi.mocked(fetchLocations).mockReset();
  vi.mocked(fetchLocations).mockResolvedValue([]);
  signInAs(userByEmail("dispatcher@cfo.demo"));
});

const errorBody = (code: string, message: string) => ({ error: { code, message, details: {}, correlation_id: "corr-test" } });

function row(over: Record<string, unknown> = {}) {
  return {
    id: 4021, order_no: "SE-2026-004021", status: "PLANNED", customer_name: "Nordbygg AB", site: "Göteborg",
    warehouse: { id: 7, code: "STO" }, origin_store: { id: 21, code: "GBG-V" },
    date_request: { mode: "latest", date_from: null, date_to: "2026-11-18" },
    committed_date: null, promise_end: null, risk_color: null, block_reason: null,
    total_amount: "48300.00", currency: "SEK", submitted_at: "2026-11-05T07:12:00Z", ...over,
  };
}
const pageOf = (items: unknown[], extra: Record<string, unknown> = {}) => ({ items, page: 1, page_size: 50, total: items.length, ...extra });
const ordersOk = (items: unknown[] = [row()]) => http.get(ORDERS_URL, () => HttpResponse.json(pageOf(items)));
const ordersFail = (status: number, code: string, message: string) =>
  http.get(ORDERS_URL, () => HttpResponse.json(errorBody(code, message), { status }));

const main = () => within(screen.getByRole("main"));

/** Ghi lại query string của mọi lần gọi GET /orders (Sidebar chỉ gọi /orders/counts nên không lẫn vào). */
function recordOrders(items: unknown[] = [row()]) {
  const calls: URLSearchParams[] = [];
  server.use(http.get(ORDERS_URL, ({ request }) => {
    calls.push(new URL(request.url).searchParams);
    return HttpResponse.json(pageOf(items));
  }));
  return calls;
}
const lastOf = (calls: URLSearchParams[]) => calls[calls.length - 1];
const firstCall = (calls: URLSearchParams[]) => waitFor(() => expect(calls.length).toBeGreaterThan(0));

describe("Order queue states", () => {
  it("test_US_ORD_02_AC3_shows_loading_while_orders_are_pending", async () => {
    server.use(http.get(ORDERS_URL, async () => {
      await delay("infinite");
      return HttpResponse.json(pageOf([]));
    }));

    renderAt("/dispatcher/orders");

    expect(await main().findByText("Loading…")).toBeInTheDocument();
  });

  it("test_US_ORD_02_AC3_shows_empty_state_when_queue_has_no_orders", async () => {
    renderAt("/dispatcher/orders");

    expect(await main().findByText("No orders in the queue.")).toBeInTheDocument();
    expect(main().getByText("0 orders")).toBeInTheDocument();
  });

  it("test_US_ORD_02_AC3_empty_state_with_filters_offers_clear_filters", async () => {
    renderAt("/dispatcher/orders?status=PLANNED");

    expect(await main().findByText("No orders match these filters.")).toBeInTheDocument();
    expect(main().getAllByRole("button", { name: "Clear filters" }).length).toBeGreaterThan(0);
  });

  it("test_US_ORD_02_AC3_error_shows_message_and_retry_recovers", async () => {
    server.use(ordersFail(503, "SERVICE_UNAVAILABLE", "Orders service is down"));
    renderAt("/dispatcher/orders");

    expect(await main().findByText("Orders unavailable")).toBeInTheDocument();
    expect(main().getByText("Orders service is down")).toBeInTheDocument();

    server.use(ordersOk());
    await userEvent.setup().click(main().getByRole("button", { name: /retry/i }));

    await waitFor(() => expect(main().getAllByText("SE-2026-004021").length).toBeGreaterThan(0));
    expect(main().queryByText("Orders unavailable")).toBeNull();
  });

  it("test_US_ORD_02_AC3_forbidden_shows_no_data_and_does_not_call_again", async () => {
    let ordersCalls = 0;
    server.use(http.get(ORDERS_URL, () => {
      ordersCalls += 1;
      return HttpResponse.json(errorBody("FORBIDDEN", "Not allowed"), { status: 403 });
    }));

    renderAt("/dispatcher/orders");

    expect(await main().findByText("You do not have access to the order queue")).toBeInTheDocument();
    expect(main().getByText(/No orders were loaded/)).toBeInTheDocument();
    expect(main().queryByRole("table")).toBeNull();
    expect(main().queryByRole("button", { name: /retry/i })).toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(ordersCalls).toBe(1);
  });

  it("test_US_ORD_02_AC3_invalid_response_shows_error_and_no_rows", async () => {
    server.use(http.get(ORDERS_URL, () => HttpResponse.json({ total: 3 })));

    renderAt("/dispatcher/orders");

    expect(await main().findByText(/Invalid order response/)).toBeInTheDocument();
    expect(main().queryByRole("table")).toBeNull();
  });

  it("test_US_ORD_02_AC3_failed_refresh_keeps_last_orders_with_stale_banner", async () => {
    server.use(ordersOk());
    renderAt("/dispatcher/orders");
    await waitFor(() => expect(main().getAllByText("SE-2026-004021").length).toBeGreaterThan(0));
    const refresh = main().getByRole("button", { name: "Refresh" });
    await waitFor(() => expect(refresh).toBeEnabled());

    server.use(ordersFail(503, "SERVICE_UNAVAILABLE", "Orders service is down"));
    await userEvent.setup().click(refresh);

    expect(await main().findByText(/Refresh failed/)).toBeInTheDocument();
    expect(main().getAllByText("SE-2026-004021").length).toBeGreaterThan(0);
    expect(main().queryByText("Orders unavailable")).toBeNull();
  });

  it("test_US_ORD_02_AC3_freshness_is_marked_unknown_when_integration_overview_fails", async () => {
    server.use(ordersOk(), http.get(OVERVIEW_URL, () => HttpResponse.json(errorBody("SERVICE_UNAVAILABLE", "off"), { status: 503 })));

    renderAt("/dispatcher/orders");

    expect(await main().findByText(/Data freshness unknown/)).toBeInTheDocument();
    expect(main().getByText(/Data freshness unknown/).closest("[data-component='DataFreshness']")).toHaveAttribute("data-stale", "true");
    expect(main().getAllByText("SE-2026-004021").length).toBeGreaterThan(0);
  });
});

describe("Order queue request parameters", () => {
  it("test_US_ORD_02_AC3_default_request_is_fifo_open_orders_with_blocked_false", async () => {
    const calls = recordOrders();
    renderAt("/dispatcher/orders");
    await firstCall(calls);

    const params = calls[0];
    expect(params.get("sort")).toBeNull();
    expect(params.get("blocked")).toBe("false");
    expect(params.get("status")).toBe("SUBMITTED,PLANNED,NO_FEASIBLE_DATE,APPROVED,PREPARING,GOODS_READY,LOADED,DISPATCHED,FAILED");
    expect(params.get("status")).not.toContain("BLOCKED_UNMAPPED_SKU");
    expect(params.get("page")).toBe("1");
    expect(params.get("page_size")).toBe("50");
    expect(params.get("risk_color")).toBeNull();
    expect(params.get("committed_date_from")).toBeNull();
    expect(params.get("committed_date_to")).toBeNull();
    expect(params.get("q")).toBeNull();
  });

  it("test_US_ORD_02_AC3_url_filters_are_sent_to_the_server", async () => {
    const calls = recordOrders();
    renderAt("/dispatcher/orders?status=PLANNED&risk=red&from=2026-11-01&to=2026-11-30&page=2&page_size=25&sort=committed_date&desc=1");
    await firstCall(calls);

    const params = calls[0];
    expect(params.get("status")).toBe("PLANNED");
    expect(params.get("risk_color")).toBe("red");
    expect(params.get("committed_date_from")).toBe("2026-11-01");
    expect(params.get("committed_date_to")).toBe("2026-11-30");
    expect(params.get("page")).toBe("2");
    expect(params.get("page_size")).toBe("25");
    expect(params.get("sort")).toBe("-committed_date");
    expect(params.get("blocked")).toBe("false");
  });

  it("test_US_ORD_02_AC3_inverted_date_range_is_not_sent_and_user_is_told", async () => {
    const calls = recordOrders();
    renderAt("/dispatcher/orders?from=2026-11-30&to=2026-11-01");
    await firstCall(calls);

    expect(calls[0].get("committed_date_from")).toBeNull();
    expect(calls[0].get("committed_date_to")).toBeNull();
    expect(await main().findByText(/date filter is not applied/)).toBeInTheDocument();
  });

  it("test_US_ORD_02_AC3_changing_risk_and_bucket_sends_new_server_query", async () => {
    const calls = recordOrders();
    const user = userEvent.setup();
    renderAt("/dispatcher/orders?page=3");
    await firstCall(calls);

    await user.selectOptions(main().getByLabelText("Risk"), "red");
    await waitFor(() => expect(lastOf(calls).get("risk_color")).toBe("red"));
    expect(lastOf(calls).get("page")).toBe("1");

    await user.click(main().getByRole("button", { name: /^Needs plan/ }));
    await waitFor(() => expect(lastOf(calls).get("status")).toBe("SUBMITTED"));
  });

  it("test_US_ORD_02_AC3_search_text_is_sent_as_q_and_never_logged", async () => {
    const spies = (["log", "info", "debug"] as const).map((method) => vi.spyOn(console, method).mockImplementation(() => {}));
    const calls = recordOrders();
    renderAt("/dispatcher/orders");
    await firstCall(calls);
    expect(calls[0].get("q")).toBeNull();

    await userEvent.setup().type(main().getByLabelText("Search"), "070123");

    await waitFor(() => expect(calls.some((p) => p.get("q") === "070123")).toBe(true), { timeout: 2000 });
    spies.forEach((spy) => {
      expect(spy).not.toHaveBeenCalled();
      spy.mockRestore();
    });
  });
});

describe("Order queue rows and counts", () => {
  it("test_US_ORD_02_AC3_legacy_blocked_orders_are_hidden_and_reported", async () => {
    server.use(ordersOk([row(), row({ id: 9, order_no: "SE-LEGACY-9", status: "BLOCKED_UNMAPPED_SKU" })]));
    renderAt("/dispatcher/orders");

    await waitFor(() => expect(main().getAllByText("SE-2026-004021").length).toBeGreaterThan(0));
    expect(main().queryByText("SE-LEGACY-9")).toBeNull();
    expect(main().getByText(/1 legacy order\(s\) hidden/)).toBeInTheDocument();
  });

  it("test_US_ORD_02_AC3_chip_counts_come_from_orders_counts_endpoint", async () => {
    server.use(http.get(COUNTS_URL, () => HttpResponse.json({
      all: 34, needs_plan: 6, awaiting_approval: 4, no_feasible_date: 1, in_execution: 12,
      replan_suggested: 1, delivered_today: 9, nav: { order_queue: 6, exceptions: 1, tracking_risk: 2 },
    })));
    renderAt("/dispatcher/orders");

    expect(await main().findByRole("button", { name: "Needs plan, 6 orders" })).toBeInTheDocument();
    expect(main().getByRole("button", { name: "Awaiting approval, 4 orders" })).toBeInTheDocument();
    expect(main().getByRole("button", { name: "No feasible date, 1 orders" })).toBeInTheDocument();
    expect(main().getByRole("button", { name: "In execution, 12 orders" })).toBeInTheDocument();
    expect(main().getByRole("button", { name: "Open" })).toBeInTheDocument();
    expect(main().queryByRole("button", { name: /^Open, / })).toBeNull();
    expect(main().getByText("Replan suggested 1 · Delivered today 9")).toBeInTheDocument();
  });

  it("test_US_ORD_02_AC3_counts_failure_keeps_rows_and_shows_notice", async () => {
    server.use(ordersOk(), http.get(COUNTS_URL, () => HttpResponse.json(errorBody("SERVICE_UNAVAILABLE", "off"), { status: 503 })));
    renderAt("/dispatcher/orders");

    expect(await main().findByText("Counts are unavailable right now.")).toBeInTheDocument();
    expect(main().getAllByText("SE-2026-004021").length).toBeGreaterThan(0);
  });
});

describe("Order queue navigation and layouts", () => {
  const link = (name: string) => main().getAllByRole("link", { name })[0];

  it("test_US_ORD_02_AC3_row_actions_match_order_status", async () => {
    server.use(ordersOk([
      row({ id: 1, order_no: "SE-A1", status: "PLANNED" }),
      row({ id: 2, order_no: "SE-A2", status: "NO_FEASIBLE_DATE" }),
      row({ id: 3, order_no: "SE-A3", status: "DISPATCHED" }),
      row({ id: 4, order_no: "SE-A4", status: "SUBMITTED" }),
      row({ id: 5, order_no: "SE-A5", status: "FAILED" }),
    ]));
    renderAt("/dispatcher/orders");

    await waitFor(() => expect(main().getAllByText("SE-A1").length).toBeGreaterThan(0));
    expect(main().getAllByRole("button", { name: "Plan review for order SE-A1" }).length).toBeGreaterThan(0);
    expect(link("Exceptions for order SE-A2")).toHaveAttribute("href", "/dispatcher/exceptions");
    expect(link("Tracking for order SE-A3")).toHaveAttribute("href", "/dispatcher/tracking");
    expect(main().getAllByRole("button", { name: "Run planning for order SE-A4" }).length).toBeGreaterThan(0);
    expect(main().queryAllByRole("link", { name: /for order SE-A5/ })).toHaveLength(0);
    expect(main().queryAllByRole("button", { name: /for order SE-A5/ })).toHaveLength(0);
  });

  it("test_US_ORD_02_AC3_renders_both_table_and_card_layouts", async () => {
    server.use(ordersOk([row({ risk_color: "red", block_reason: "MISSING_STOCK" })]));
    renderAt("/dispatcher/orders");

    const table = await main().findByRole("table");
    const cards = main().getByRole("list", { name: "Orders" });
    expect(within(table).getByText("SE-2026-004021")).toBeInTheDocument();
    expect(within(table).getByText("Nordbygg AB")).toBeInTheDocument();
    expect(within(cards).getByText("SE-2026-004021")).toBeInTheDocument();
    expect(within(cards).getByText("Nordbygg AB")).toBeInTheDocument();
    expect(within(cards).getAllByRole("listitem")).toHaveLength(1);
    expect(within(table).getByText("Blocked: MISSING_STOCK")).toBeInTheDocument();
    expect(within(cards).getByText("Blocked: MISSING_STOCK")).toBeInTheDocument();
  });
});