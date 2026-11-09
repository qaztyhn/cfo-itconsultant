import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { CsOrderDetail, CsOrderPage } from "./allowlist";
import { fetchEtaForecasts, fetchNotifications, fetchOrderDetail, fetchTimeline, searchOrders } from "./api";
import { SEARCH_PLACEHOLDER } from "./constants";
import { OrderLookup } from "./OrderLookup";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    searchOrders: vi.fn(),
    fetchOrderDetail: vi.fn(),
    fetchEtaForecasts: vi.fn(),
    fetchNotifications: vi.fn(),
    fetchTimeline: vi.fn(),
  };
});

const search = vi.mocked(searchOrders);
const getDetail = vi.mocked(fetchOrderDetail);

function pageOf(...orderNos: string[]): CsOrderPage {
  return {
    items: orderNos.map((orderNo, index) => ({
      id: 42 + index,
      orderNo,
      status: "APPROVED",
      customerName: "Anna Svensson",
      committedDate: "2026-11-13",
      promiseEnd: null,
      riskColor: "orange",
    })),
    page: 1,
    pageSize: 20,
    total: orderNos.length,
  };
}

function pagedOf(page: number, total: number, ...orderNos: string[]): CsOrderPage {
  return { ...pageOf(...orderNos), page, total };
}

const detail: CsOrderDetail = {
  id: 42,
  orderNo: "ORD-0042",
  externalRef: "POS-9001",
  status: "APPROVED",
  submittedAt: "2026-11-05T07:12:00Z",
  customerName: "Anna Svensson",
  contact: { name: "Anna Svensson", phone: "+46 •• ••• 12 34", email: null },
  committed: { date: "2026-11-13", promiseStart: "2026-11-13T07:00:00Z", promiseEnd: "2026-11-13T09:00:00Z" },
  risk: { status: "AT_RISK", color: "orange", forecastEta: "2026-11-13T08:40:00Z" },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function renderLookup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderLookup />
    </QueryClientProvider>,
  );
}

async function submit(user: ReturnType<typeof userEvent.setup>, text: string) {
  const input = screen.getByLabelText("Search orders");
  await user.clear(input);
  await user.type(input, text);
  await user.click(screen.getByRole("button", { name: "Search" }));
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchEtaForecasts).mockResolvedValue([]);
  vi.mocked(fetchNotifications).mockResolvedValue([]);
  vi.mocked(fetchTimeline).mockResolvedValue([]);
});

describe("CS Order Lookup — search", () => {
  it("test_US_CS_01_AC1_initial_state_is_empty_and_placeholder_does_not_mention_phone", () => {
    renderLookup();
    expect(screen.getByText(/Search for an order to see its status/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(SEARCH_PLACEHOLDER)).toBeInTheDocument();
    expect(SEARCH_PLACEHOLDER).not.toMatch(/phone|tel/i);
    expect(search).not.toHaveBeenCalled();
  });

  it("test_US_CS_01_AC1_submit_searches_with_abort_signal_and_lists_results", async () => {
    const user = userEvent.setup();
    search.mockResolvedValueOnce(pageOf("ORD-0042"));
    renderLookup();
    await submit(user, "ORD-0042");
    expect(await screen.findByText("ORD-0042")).toBeInTheDocument();
    expect(search).toHaveBeenCalledWith("ORD-0042", expect.any(AbortSignal), 1);
    expect(screen.getByText(/Showing 1 of 1 order/)).toBeInTheDocument();
  });

  it("test_US_CS_01_AC1_loading_state_is_shown_while_searching", async () => {
    const user = userEvent.setup();
    search.mockReturnValueOnce(new Promise(() => {}));
    renderLookup();
    await submit(user, "ORD-1");
    expect(await screen.findByText("Loading…")).toBeInTheDocument();
  });

  it("test_US_CS_01_AC1_empty_state_does_not_echo_the_query", async () => {
    const user = userEvent.setup();
    search.mockResolvedValueOnce(pageOf());
    renderLookup();
    await submit(user, "+46701231234");
    expect(await screen.findByText("No orders match this search.")).toBeInTheDocument();
    expect(screen.queryByText(/\+46701231234/)).toBeNull();
  });

  it("test_US_CS_01_AC1_forbidden_state_has_no_retry", async () => {
    const user = userEvent.setup();
    search.mockRejectedValueOnce(new ApiError("FORBIDDEN", "No access", "cid-403", undefined, 403));
    renderLookup();
    await submit(user, "ORD-1");
    expect(await screen.findByText("You don't have permission to view this.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("test_US_CS_01_AC1_api_error_shows_correlation_id_and_retry_works", async () => {
    const user = userEvent.setup();
    search.mockRejectedValueOnce(new ApiError("UNKNOWN_ERROR", "Server exploded", "cid-500", undefined, 500));
    search.mockResolvedValueOnce(pageOf("ORD-0042"));
    renderLookup();
    await submit(user, "ORD-0042");
    expect(await screen.findByText("cid-500")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("ORD-0042")).toBeInTheDocument();
    expect(search).toHaveBeenCalledTimes(2);
  });

  it("test_US_CS_01_AC1_old_search_result_never_overwrites_the_newer_one", async () => {
    const user = userEvent.setup();
    const slow = deferred<CsOrderPage>();
    search.mockReturnValueOnce(slow.promise);
    search.mockResolvedValueOnce(pageOf("ORD-B"));
    renderLookup();
    await submit(user, "A");
    await submit(user, "B");
    expect(await screen.findByText("ORD-B")).toBeInTheDocument();
    await act(async () => {
      slow.resolve(pageOf("ORD-A"));
      await slow.promise;
    });
    expect(screen.queryByText("ORD-A")).toBeNull();
    expect(screen.getByText("ORD-B")).toBeInTheDocument();
  });
});

describe("CS Order Lookup — detail", () => {
  it("test_US_CS_01_AC1_detail_shows_masked_contact_and_has_no_reveal_control", async () => {
    const user = userEvent.setup();
    search.mockResolvedValueOnce(pageOf("ORD-0042"));
    getDetail.mockResolvedValueOnce(detail);
    renderLookup();
    await submit(user, "ORD-0042");
    await user.click(await screen.findByRole("button", { name: /ORD-0042/ }));
    const region = screen.getByRole("region", { name: "Order details" });
    expect(await within(region).findByText("+46 •• ••• 12 34")).toBeInTheDocument();
    expect(within(region).getByText("Contact hidden")).toBeInTheDocument();
    expect(within(region).getByText("2026-11-13 07:00 UTC – 2026-11-13 09:00 UTC")).toBeInTheDocument();
    expect(within(region).getByRole("img", { name: "Risk: At risk" })).toBeInTheDocument();
    expect(getDetail).toHaveBeenCalledWith(42, expect.any(AbortSignal));
    expect(screen.queryByRole("button", { name: /reveal|unmask|show (phone|email|number)/i })).toBeNull();
  });

  it("test_US_CS_01_AC1_detail_forbidden_and_error_states", async () => {
    const user = userEvent.setup();
    search.mockResolvedValueOnce(pageOf("ORD-0042"));
    getDetail.mockRejectedValueOnce(new ApiError("FORBIDDEN", "No", "cid-d403", undefined, 403));
    renderLookup();
    await submit(user, "ORD-0042");
    await user.click(await screen.findByRole("button", { name: /ORD-0042/ }));
    const region = screen.getByRole("region", { name: "Order details" });
    expect(await within(region).findByText("You don't have permission to view this.")).toBeInTheDocument();
    await waitFor(() => expect(within(region).queryByRole("button", { name: "Retry" })).toBeNull());
  });

  it("test_US_CS_01_AC1_switching_order_replaces_the_detail", async () => {
    const user = userEvent.setup();
    search.mockResolvedValueOnce(pageOf("ORD-0042", "ORD-0043"));
    getDetail.mockResolvedValueOnce(detail);
    getDetail.mockResolvedValueOnce({
      ...detail,
      id: 43,
      orderNo: "ORD-0043",
      customerName: "Bo Berg",
      contact: { ...detail.contact, name: "Bo Berg" },
    });
    renderLookup();
    await submit(user, "ORD");
    await user.click(await screen.findByRole("button", { name: /ORD-0042/ }));
    const region = screen.getByRole("region", { name: "Order details" });
    expect(await within(region).findByText("ORD-0042")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /ORD-0043/ }));
    expect(await within(region).findByText("ORD-0043")).toBeInTheDocument();
    expect(within(region).queryByText("ORD-0042")).toBeNull();
    expect(within(region).queryByText("Anna Svensson")).toBeNull();
  });

  it("test_US_CS_02_switching_order_discards_the_demo_entries_of_the_previous_order", async () => {
    const user = userEvent.setup();
    search.mockResolvedValueOnce(pageOf("ORD-0042", "ORD-0043"));
    getDetail.mockResolvedValueOnce(detail);
    getDetail.mockResolvedValueOnce({
      ...detail,
      id: 43,
      orderNo: "ORD-0043",
      customerName: "Bo Berg",
      contact: { ...detail.contact, name: "Bo Berg" },
    });
    renderLookup();
    await submit(user, "ORD");
    await user.click(await screen.findByRole("button", { name: /ORD-0042/ }));
    const region = screen.getByRole("region", { name: "Order details" });
    await user.selectOptions(await within(region).findByLabelText("Channel"), "chat");
    await user.selectOptions(within(region).getByLabelText("Reason"), "other");
    await user.type(within(region).getByLabelText("Note (optional)"), "called back");
    await user.click(within(region).getByRole("button", { name: "Add demo entry" }));
    expect(within(region).getByText("called back")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /ORD-0043/ }));
    expect(await within(region).findByText("ORD-0043")).toBeInTheDocument();
    expect(within(region).queryByText("called back")).toBeNull();
  });
});

describe("CS Order Lookup — pagination and polling", () => {
  it("test_US_CS_01_AC1_pager_is_hidden_when_all_results_fit_on_one_page", async () => {
    const user = userEvent.setup();
    search.mockResolvedValueOnce(pageOf("ORD-0042"));
    renderLookup();
    await submit(user, "ORD-0042");
    expect(await screen.findByText("ORD-0042")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Search results pages" })).toBeNull();
  });

  it("test_US_CS_01_AC1_next_and_previous_request_the_adjacent_page_of_the_same_query", async () => {
    const user = userEvent.setup();
    search.mockResolvedValueOnce(pagedOf(1, 45, "ORD-0001", "ORD-0002"));
    search.mockResolvedValueOnce(pagedOf(2, 45, "ORD-0021", "ORD-0022"));
    search.mockResolvedValueOnce(pagedOf(1, 45, "ORD-0001", "ORD-0002"));
    renderLookup();
    await submit(user, "Anna");
    expect(await screen.findByText("ORD-0001")).toBeInTheDocument();
    expect(screen.getByText(/Showing 1–2 of 45 orders/)).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("ORD-0021")).toBeInTheDocument();
    await waitFor(() => expect(search).toHaveBeenLastCalledWith("Anna", expect.any(AbortSignal), 2));
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
    expect(screen.getByText(/Showing 21–22 of 45 orders/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    await waitFor(() => expect(search).toHaveBeenLastCalledWith("Anna", expect.any(AbortSignal), 1));
  });

  it("test_US_CS_01_AC1_pager_buttons_stay_focusable_and_do_nothing_at_the_first_page", async () => {
    const user = userEvent.setup();
    search.mockResolvedValueOnce(pagedOf(1, 45, "ORD-0001"));
    renderLookup();
    await submit(user, "Anna");
    await screen.findByText("ORD-0001");
    const previous = screen.getByRole("button", { name: "Previous" });
    expect(previous).toHaveAttribute("aria-disabled", "true");
    expect(previous).not.toBeDisabled();
    await user.click(previous);
    expect(search).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
  });

  it("test_US_CS_01_AC1_current_page_stays_visible_and_consistent_while_the_next_page_loads", async () => {
    const user = userEvent.setup();
    const next = deferred<CsOrderPage>();
    search.mockResolvedValueOnce(pagedOf(1, 45, "ORD-0001"));
    search.mockReturnValueOnce(next.promise);
    renderLookup();
    await submit(user, "Anna");
    await screen.findByText("ORD-0001");

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("ORD-0001")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();

    act(() => next.resolve(pagedOf(2, 45, "ORD-0021")));
    expect(await screen.findByText("ORD-0021")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  });

  it("test_US_CS_01_AC1_a_new_search_starts_from_page_one", async () => {
    const user = userEvent.setup();
    search.mockResolvedValueOnce(pagedOf(1, 45, "ORD-0001"));
    search.mockResolvedValueOnce(pagedOf(2, 45, "ORD-0021"));
    search.mockResolvedValueOnce(pagedOf(1, 1, "ORD-0900"));
    renderLookup();
    await submit(user, "Anna");
    await screen.findByText("ORD-0001");
    await user.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("ORD-0021");

    await submit(user, "Bob");
    expect(await screen.findByText("ORD-0900")).toBeInTheDocument();
    expect(search).toHaveBeenLastCalledWith("Bob", expect.any(AbortSignal), 1);
  });

  it("test_CS_queries_do_not_poll_even_when_the_app_default_sets_a_refetch_interval", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
      search.mockResolvedValue(pageOf("ORD-0042"));
      getDetail.mockResolvedValue(detail);
      const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchInterval: 20_000 } } });
      render(
        <QueryClientProvider client={client}>
          <OrderLookup />
        </QueryClientProvider>,
      );
      await submit(user, "ORD-0042");
      await user.click(await screen.findByRole("button", { name: /ORD-0042/ }));
      const mocks = [search, getDetail, vi.mocked(fetchEtaForecasts), vi.mocked(fetchNotifications), vi.mocked(fetchTimeline)];
      await waitFor(() => mocks.forEach((mock) => expect(mock).toHaveBeenCalled()));

      const before = mocks.map((mock) => mock.mock.calls.length);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(65_000);
      });
      expect(mocks.map((mock) => mock.mock.calls.length)).toEqual(before);
    } finally {
      vi.useRealTimers();
    }
  });
});