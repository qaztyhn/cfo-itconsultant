import { describe, expect, it } from "vitest";
import { projectCounts, projectPage } from "./model";

function item(over: Record<string, unknown> = {}) {
  return {
    id: 4021, order_no: "SE-2026-004021", status: "PLANNED", customer_name: "Nordbygg AB", site: "Göteborg",
    warehouse: { id: 7, code: "STO" }, origin_store: { id: 21, code: "GBG-V" },
    date_request: { mode: "latest", date_from: null, date_to: "2026-11-18" },
    committed_date: null, promise_end: null, risk_color: null, block_reason: null,
    total_amount: "48300.00", currency: "SEK", submitted_at: "2026-11-05T07:12:00Z", ...over,
  };
}
const page = (items: unknown[], extra: Record<string, unknown> = {}) => ({ items, page: 1, page_size: 50, total: items.length, ...extra });

describe("order queue model", () => {
  it("test_US_ORD_02_AC3_keeps_server_order_and_combines_customer_site", () => {
    const result = projectPage(page([item({ id: 2, order_no: "B" }), item({ id: 1, order_no: "A" })]), 1, 50);
    expect(result.items.map(row => row.orderNo)).toEqual(["B", "A"]);
    expect(result.items[0]).toMatchObject({ customer: "Nordbygg AB", site: "Göteborg", warehouse: { id: 7, code: "STO" } });
    expect(result.invalid).toBe(false);
  });

  it("test_US_ORD_02_AC3_hides_legacy_blocked_orders_from_queue", () => {
    const result = projectPage(page([item(), item({ id: 9, status: "BLOCKED_UNMAPPED_SKU" })]), 1, 50);
    expect(result.items.map(row => row.id)).toEqual([4021]);
    expect(result.hiddenLegacy).toBe(1);
  });

  it("test_US_ORD_02_AC3_unknown_values_become_null_not_inferred", () => {
    const [row] = projectPage(page([item({ risk_color: "purple", status: "WEIRD", warehouse: null, committed_date: "2026-13-40" })]), 1, 50).items;
    expect(row.riskColor).toBeNull();
    expect(row.status).toBe("UNKNOWN");
    expect(row.warehouse).toBeNull();
    expect(row.committedDate).toBeNull();
  });

  it("test_US_ORD_02_AC3_malformed_items_are_skipped_and_counted", () => {
    const result = projectPage(page([item({ id: "x" }), item()]), 1, 50);
    expect(result.items).toHaveLength(1);
    expect(result.skipped).toBe(1);
  });

  it("test_US_ORD_02_AC3_response_without_items_array_is_invalid", () => {
    expect(projectPage({ total: 3 }, 2, 50)).toMatchObject({ invalid: true, items: [], page: 2 });
  });

  it("test_US_ORD_02_AC3_counts_require_every_bucket", () => {
    const counts = { all: 34, needs_plan: 6, awaiting_approval: 4, no_feasible_date: 1, in_execution: 12,
      replan_suggested: 1, delivered_today: 9, nav: { order_queue: 6, exceptions: 1, tracking_risk: 2 } };
    expect(projectCounts(counts)).toMatchObject({ all: 34, needsPlan: 6, nav: { orderQueue: 6, trackingRisk: 2 } });
    expect(projectCounts({ ...counts, needs_plan: undefined })).toBeNull();
    expect(projectCounts({ ...counts, nav: { order_queue: -1, exceptions: 1, tracking_risk: 2 } })).toBeNull();
  });
});