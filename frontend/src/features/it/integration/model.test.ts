/** M2 contract safety and source accounting regression tests. */
import { describe, expect, it } from "vitest";
import { CONTRACT_OVERVIEW, CONTRACT_REJECTS, CONTRACT_RUNS } from "./contractPreview";
import {
  normalizeMatrix, normalizeRejects, normalizeRuns, normalizeScheduler,
  normalizeSources, safeCount, timestamp,
} from "./model";

describe("US-INT-01 AC3/AC4 source status and reject projection", () => {
  it("never promotes a partial or failed run to a successful sync", () => {
    const runs = normalizeRuns(CONTRACT_RUNS);
    const sources = normalizeSources(CONTRACT_OVERVIEW, runs);
    const inbound = sources.find((source) => source.entity === "inbound")!;
    const fleet = sources.find((source) => source.entity === "fleet")!;
    expect(inbound.status).toBe("partial");
    expect(inbound.lastSuccessfulAt).toBeNull();
    expect(fleet.status).toBe("failed");
    expect(fleet.lastSuccessfulAt).toBe("2026-11-04 08:00 UTC");
    expect(fleet.lastRunAt).toBe("2026-11-04 08:54 UTC");
    expect(fleet.latestStatus).toBe("failed");
  });

  it("never overrides a latest partial run with an older OK overview chip", () => {
    const sources = normalizeSources({ sources: { inbound: { status: "ok" } } }, normalizeRuns({ items: [
      { id: 4, entity: "inbound", status: "partial", started_at: "2026-11-04T10:00:00Z" },
    ] }));
    expect(sources.find((source) => source.entity === "inbound")?.status).toBe("partial");
  });

  it("separates unmapped SKUs from rejected product records", () => {
    const sources = normalizeSources(CONTRACT_OVERVIEW, normalizeRuns(CONTRACT_RUNS));
    const products = sources.find((source) => source.entity === "products")!;
    expect(products.unmapped).toBe(3);
    expect(products.rejected).toBe(0);
    expect(products.status).toBe("ok");
    expect(sources.filter((source) => source.unmapped !== null)).toHaveLength(1);
  });

  it("never treats a blocked stock feed or 503 as zero inventory", () => {
    const sources = normalizeSources(CONTRACT_OVERVIEW, normalizeRuns(CONTRACT_RUNS));
    const stock = sources.find((source) => source.entity === "stock")!;
    expect(stock.status).toBe("blocked");
    expect(stock.rows).toBeNull();
    expect(stock.dataAsOf).toBe("2026-11-04 09:00 UTC");
    expect(stock.latestStatus).toBe("failed");
    expect(stock.availability).toBe("unconfigured");
    expect(safeCount(null)).toBeNull();
    expect(safeCount(undefined)).toBeNull();
    expect(safeCount(-1)).toBeNull();
  });

  it("test_US_INT_01_AC3_uses_persisted_overview_without_promoting_failed_run", () => {
    const sources = normalizeSources({ sources: {
      orders: { availability: "supported", status: "failed", last_run_status: "failed",
        last_run_at: "2026-11-09T08:00:00Z", last_successful_at: "2026-11-08T08:00:00Z",
        data_as_of: "2026-11-08T07:55:00Z", rows: 2, rejected: 2 },
    } }, []);
    expect(sources.find((source) => source.entity === "orders")).toMatchObject({
      status: "failed", lastSuccessfulAt: "2026-11-08 08:00 UTC", dataAsOf: "2026-11-08 07:55 UTC",
    });
  });

  it("never renders untrusted reject text, external keys or raw payloads", () => {
    const rejects = normalizeRejects(CONTRACT_REJECTS);
    const safe = JSON.stringify(rejects);
    expect(rejects.map((row) => row.reasonCode)).toEqual(["BAD_DATE", "UNKNOWN_SKU"]);
    expect(safe).not.toContain("PRIVATE");
    expect(safe).not.toContain("redacted@example.test");
    expect(normalizeRejects({ items: [{
      id: 2, reason_code: "JOHN.DOE@EXAMPLE.COM", reason: "PRIVATE PHONE", raw: { pii: "PRIVATE" },
    }] })[0].reasonCode).toBe("UNCLASSIFIED");
  });

  it("drops unknown feed statuses, negative counts and timezone-free timestamps", () => {
    const sources = normalizeSources({
      sources: { orders: { status: "REALTIME", rows: -100, rejected: 0, data_as_of: "2026-11-04" } },
    }, []);
    expect(sources.find((source) => source.entity === "orders")).toMatchObject({
      status: "unknown", rows: null, dataAsOf: null, rejected: 0,
    });
    expect(timestamp("2026-11-04T09:00:00")).toBeNull();
    expect(timestamp("2026-11-04T09:00:00+01:00")).toBe("2026-11-04 08:00 UTC");
  });

  it("shows reported matrix facts but no inferred scheduler or background worker", () => {
    expect(normalizeMatrix(CONTRACT_OVERVIEW)).toMatchObject({ pairs: 25, fallbackPairs: 2 });
    expect(normalizeScheduler(CONTRACT_OVERVIEW)).toMatchObject({
      lastTickAt: null, lastTickStatus: null, reportedIntervalMin: null, jobs: [],
    });
    expect(normalizeRuns({ items: [
      { id: 1, entity: "orders", kind: "csv", file_name: "PRIVATE_CUSTOMER_PHONE.csv", status: "failed" },
    ] })[0]).not.toHaveProperty("file_name");
  });
});
