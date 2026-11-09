import { describe, expect, it } from "vitest";
import { isDateRangeInvalid, parseQueueState, toQueueQuery, updateParams } from "./queueState";

const parse = (query: string) => parseQueueState(new URLSearchParams(query));

describe("order queue state", () => {
  it("test_US_ORD_02_AC3_defaults_to_open_bucket_with_server_fifo", () => {
    const state = parse("");
    expect(state).toEqual({ bucket: "active", status: null, risk: null, from: null, to: null, sort: null, desc: false, page: 1, pageSize: 50 });
    const query = toQueueQuery(state);
    expect(query.sort).toBeUndefined();
    expect(query.status).toBe("SUBMITTED,PLANNED,NO_FEASIBLE_DATE,APPROVED,PREPARING,GOODS_READY,LOADED,DISPATCHED,FAILED");
  });

  it("test_US_ORD_02_AC3_invalid_url_values_fall_back_to_defaults", () => {
    const state = parse("bucket=evil&status=BLOCKED_UNMAPPED_SKU&risk=purple&from=2026-02-31&to=nope&sort=password&desc=1&page=-3&page_size=7");
    expect(state).toEqual(parse(""));
  });

  it("test_US_ORD_02_AC3_legacy_status_is_never_requested", () => {
    expect(toQueueQuery(parse("status=BLOCKED_UNMAPPED_SKU")).status).not.toContain("BLOCKED");
    expect(toQueueQuery(parse("")).status).not.toContain("BLOCKED");
  });

  it("test_US_ORD_02_AC3_bucket_maps_to_exact_server_statuses", () => {
    expect(toQueueQuery(parse("bucket=needs_plan")).status).toBe("SUBMITTED");
    expect(toQueueQuery(parse("bucket=awaiting_approval")).status).toBe("PLANNED");
    expect(toQueueQuery(parse("bucket=in_execution")).status).toBe("APPROVED,PREPARING,GOODS_READY,LOADED,DISPATCHED");
  });

  it("test_US_ORD_02_AC3_status_and_risk_filter_combine", () => {
    const query = toQueueQuery(parse("bucket=in_execution&status=PREPARING&risk=orange"));
    expect(query).toMatchObject({ status: "PREPARING", riskColor: "orange" });
  });

  it("test_US_ORD_02_AC3_explicit_sort_and_direction_are_forwarded", () => {
    expect(toQueueQuery(parse("sort=promise_end&desc=1"))).toMatchObject({ sort: "promise_end", descending: true });
  });

  it("test_US_ORD_02_AC3_inverted_date_range_is_not_sent", () => {
    const state = parse("from=2026-12-01&to=2026-11-01");
    expect(isDateRangeInvalid(state)).toBe(true);
    const query = toQueueQuery(state);
    expect(query.committedFrom).toBeUndefined();
    expect(query.committedTo).toBeUndefined();
  });

  it("test_US_ORD_02_AC3_valid_date_range_is_sent", () => {
    expect(toQueueQuery(parse("from=2026-11-01&to=2026-11-30"))).toMatchObject({ committedFrom: "2026-11-01", committedTo: "2026-11-30" });
  });

  it("test_US_ORD_02_AC3_search_text_is_trimmed_and_capped_and_not_in_url_state", () => {
    expect(toQueueQuery(parse(""), "  abc  ").q).toBe("abc");
    expect(toQueueQuery(parse(""), "a".repeat(150)).q).toHaveLength(100);
    expect(toQueueQuery(parse("q=secret")).q).toBeUndefined();
  });

  it("test_US_ORD_02_AC3_changing_a_filter_resets_page_but_explicit_page_is_kept", () => {
    const filtered = updateParams(new URLSearchParams("page=3&bucket=needs_plan"), { risk: "red" });
    expect(filtered.get("page")).toBeNull();
    expect(filtered.get("risk")).toBe("red");
    expect(filtered.get("bucket")).toBe("needs_plan");
    expect(updateParams(new URLSearchParams(), { page: "3" }).get("page")).toBe("3");
  });

  it("test_US_ORD_02_AC3_status_and_bucket_are_mutually_exclusive_and_defaults_are_dropped", () => {
    const byStatus = updateParams(new URLSearchParams("bucket=needs_plan"), { status: "PREPARING" });
    expect(byStatus.get("status")).toBe("PREPARING");
    expect(byStatus.get("bucket")).toBeNull();
    const byBucket = updateParams(new URLSearchParams("status=PREPARING"), { bucket: "in_execution" });
    expect(byBucket.get("status")).toBeNull();
    expect(byBucket.get("bucket")).toBe("in_execution");
    expect(updateParams(new URLSearchParams("bucket=needs_plan"), { bucket: "active" }).toString()).toBe("");
  });
});