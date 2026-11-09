import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet, apiPost, isApiError, ApiError } from "../../api/client";
import { fetchEtaForecasts, fetchNotifications, fetchOrderDetail, fetchTimeline, searchOrders } from "./api";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, apiGet: vi.fn(), apiPost: vi.fn() };
});

const get = vi.mocked(apiGet);
const post = vi.mocked(apiPost);

const RAW_PHONE = "+46 70 123 12 34";

beforeEach(() => vi.clearAllMocks());

describe("CS api boundary", () => {
  it("test_US_CS_01_AC1_search_calls_orders_q_and_forwards_abort_signal", async () => {
    get.mockResolvedValueOnce({ items: [], page: 1, page_size: 20, total: 0 });
    const controller = new AbortController();
    await searchOrders("  ORD-0042 ", controller.signal);
    expect(get).toHaveBeenCalledWith("/orders", { q: "ORD-0042", page: 1, page_size: 20 }, controller.signal);
  });

  it("test_US_CS_01_AC1_search_requests_the_given_page", async () => {
    get.mockResolvedValueOnce({ items: [], page: 3, page_size: 20, total: 50 });
    await searchOrders("Anna", undefined, 3);
    expect(get).toHaveBeenCalledWith("/orders", { q: "Anna", page: 3, page_size: 20 }, undefined);
  });

  it("test_US_CS_01_AC1_blank_search_sends_no_request", async () => {
    const page = await searchOrders("   ");
    expect(get).not.toHaveBeenCalled();
    expect(page.items).toEqual([]);
  });

  it("test_US_CS_01_AC1_search_result_is_projected_and_never_exposes_raw_phone", async () => {
    get.mockResolvedValueOnce({
      items: [{ id: 1, order_no: "ORD-1", customer_name: "Anna", status: "APPROVED", phone: RAW_PHONE, lat: 59.3 }],
      page: 1,
      page_size: 20,
      total: 1,
    });
    const page = await searchOrders("Anna");
    expect(JSON.stringify(page)).not.toContain(RAW_PHONE);
    expect(JSON.stringify(page)).not.toContain("59.3");
    expect(page.items[0]?.orderNo).toBe("ORD-1");
  });

  it("test_US_CS_01_AC1_detail_is_projected_and_signal_forwarded", async () => {
    get.mockResolvedValueOnce({
      id: 42,
      order_no: "ORD-0042",
      contact: { name: "Anna", phone: RAW_PHONE, phone_masked: "+46 •• ••• 12 34" },
      delivery: { lat: 59.3293, lon: 18.0686, receiving_restrictions: "GATE-7731" },
    });
    const controller = new AbortController();
    const detail = await fetchOrderDetail(42, controller.signal);
    expect(get).toHaveBeenCalledWith("/orders/42", undefined, controller.signal);
    const json = JSON.stringify(detail);
    for (const value of [RAW_PHONE, "59.3293", "GATE-7731"]) expect(json).not.toContain(value);
    expect(detail.contact.phone).toBe("+46 •• ••• 12 34");
  });

  it("test_US_CS_01_AC1_unreadable_detail_throws_api_error", async () => {
    get.mockResolvedValueOnce({ nope: true });
    await expect(fetchOrderDetail(42)).rejects.toSatisfy((e) => isApiError(e) && e.code === "INVALID_RESPONSE");
  });

  it("test_US_CS_02_backend_errors_propagate_unchanged_for_the_error_state", async () => {
    const forbidden = new ApiError("FORBIDDEN", "No access", "cid-1", undefined, 403);
    get.mockRejectedValueOnce(forbidden);
    await expect(searchOrders("x")).rejects.toBe(forbidden);
    const stub = new ApiError("UNKNOWN_ERROR", "HTTP 500", "cid-2", undefined, 500);
    get.mockRejectedValueOnce(stub);
    await expect(fetchNotifications(42)).rejects.toBe(stub);
    get.mockRejectedValueOnce(stub);
    await expect(fetchEtaForecasts(42)).rejects.toBe(stub);
  });

  it("test_US_CS_01_AC1_timeline_is_filtered_and_no_write_call_is_ever_made", async () => {
    get.mockResolvedValueOnce({
      items: [
        { at: "2026-11-05T07:12:00Z", kind: "order_submitted" },
        { at: "2026-11-05T07:13:00Z", kind: "decision", detail: { reason_text: "secret" } },
      ],
    });
    const items = await fetchTimeline(42);
    expect(items).toEqual([{ kind: "order_submitted", at: "2026-11-05T07:12:00Z" }]);
    expect(post).not.toHaveBeenCalled();
  });
});