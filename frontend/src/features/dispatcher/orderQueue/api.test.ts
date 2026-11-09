import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/client", async importOriginal => ({
  ...(await importOriginal<typeof import("../../../api/client")>()),
  apiGet: vi.fn(),
}));

import { apiGet } from "../../../api/client";
import { buildQueueParams, fetchOrderQueue, fetchQueueCounts } from "./api";

const mocked = vi.mocked(apiGet);
beforeEach(() => mocked.mockReset());

describe("order queue api", () => {
  it("test_US_ORD_02_AC3_default_query_leaves_sort_to_server_fifo_and_excludes_legacy", () => {
    const params = buildQueueParams({ page: 1, pageSize: 50 });
    expect(params.sort).toBeUndefined();
    expect(params.blocked).toBe(false);
    expect(params).toMatchObject({ page: 1, page_size: 50 });
  });

  it("test_US_ORD_02_AC3_filters_and_explicit_sort_are_sent_to_server", () => {
    const params = buildQueueParams({
      q: "  Nordbygg  ", status: "PREPARING", riskColor: "orange", committedFrom: "2026-11-01", committedTo: "2026-11-30",
      warehouseId: 7, sort: "promise_end", descending: true, page: 2, pageSize: 25,
    });
    expect(params).toEqual({
      status: "PREPARING", risk_color: "orange", committed_date_from: "2026-11-01", committed_date_to: "2026-11-30",
      warehouse_id: 7, q: "Nordbygg", sort: "-promise_end", page: 2, page_size: 25, blocked: false,
    });
  });

  it("test_US_ORD_02_AC3_blank_search_is_not_sent", () => {
    expect(buildQueueParams({ q: "   ", page: 1, pageSize: 50 }).q).toBeUndefined();
  });

  it("test_US_ORD_02_AC3_fetch_orders_calls_orders_and_projects_page", async () => {
    mocked.mockResolvedValue({ items: [], page: 1, page_size: 50, total: 0 });
    const signal = new AbortController().signal;
    const page = await fetchOrderQueue({ page: 1, pageSize: 50 }, signal);
    expect(mocked).toHaveBeenCalledWith("/orders", expect.objectContaining({ blocked: false }), signal);
    expect(page).toMatchObject({ items: [], total: 0, invalid: false });
  });

  it("test_US_ORD_02_AC3_fetch_counts_returns_null_for_bad_payload", async () => {
    mocked.mockResolvedValue({ all: 1 });
    expect(await fetchQueueCounts()).toBeNull();
    expect(mocked).toHaveBeenCalledWith("/orders/counts", undefined, undefined);
  });
});