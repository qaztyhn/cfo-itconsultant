/**
 * Test hợp đồng xác thực giữa client thật và mock (docs/06 mục 4). Đây là test MOCK, không phải tích hợp backend thật.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../app/store";
import { fetchMe, login, logout } from "../auth";
import { apiGet } from "../client";
import { MOCK_ACCOUNTS, resetLoginRateLimit } from "./authHandlers";
import { handlers } from "./handlers";
import { API_BASE_URL } from "../config";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  useAuthStore.setState({ token: null, user: null });
  resetLoginRateLimit();
});
afterEach(() => {
  server.resetHandlers();
  vi.useRealTimers();
});
afterAll(() => server.close());

describe("login (US-EMP-03)", () => {
  it("test_US_EMP_03_AC1_valid_login_returns_8h_token_with_roles_and_location_ids", async () => {
    const result = await login({ email: "dispatcher@cfo.demo", password: "anything" });

    expect(result.token_type).toBe("bearer");
    expect(result.access_token).toEqual(expect.any(String));
    expect(result.expires_in).toBe(28_800);
    expect(result.user.roles).toEqual(["dispatcher"]);
    expect(result.user.location_ids).toEqual([4]);
    expect(result.user.kpi_scopes).toEqual(["ops"]);
  });

  it.each(MOCK_ACCOUNTS.map((a) => [a.email, a.user.roles, a.user.kpi_scopes] as const))(
    "%s signs in and returns the docs/06 user shape (roles %j, scopes %j)",
    async (email, roles, scopes) => {
        const { user } = await login({ email: email.toUpperCase(), password: "x" }); // email không phân biệt hoa thường

        const expectedKeys = ["id", "employee_id", "name", "roles", "market", "location_ids", "locale", "kpi_scopes", "owned_location_ids"];
        expect(Object.keys(user).sort()).toEqual([...expectedKeys].sort());
        expect(user.roles).toEqual(roles);
        expect(user.kpi_scopes).toEqual(scopes);
        expect(user.owned_location_ids).toEqual([]);
    },
  );

  it("distinguishes Business owner (revenue_all) from Project lead (ops) by kpi_scopes, both viewer (docs/06 mục 3.1)", async () => {
    const owner = (await login({ email: "owner@cfo.demo", password: "x" })).user;
    const lead = (await login({ email: "projectlead@cfo.demo", password: "x" })).user;

    expect(owner).toMatchObject({ roles: ["viewer"], kpi_scopes: ["revenue_all"] });
    expect(lead).toMatchObject({ roles: ["viewer"], kpi_scopes: ["ops"] });
  });

  it("rejects an unknown account with 401 AUTH_INVALID and a correlation id", async () => {
    await expect(login({ email: "nobody@cfo.demo", password: "x" })).rejects.toMatchObject({
      code: "AUTH_INVALID",
      status: 401,
      correlationId: expect.any(String),
    });
  });

  it("rejects an empty password with 422 VALIDATION_ERROR", async () => {
    await expect(login({ email: "dispatcher@cfo.demo", password: "" })).rejects.toMatchObject({ code: "VALIDATION_ERROR", status: 422 });
  });

  it("answers 429 after 5 failed attempts within a minute and recovers afterwards", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const start = new Date("2026-11-07T10:00:00Z");
    vi.setSystemTime(start);

    for (let i = 0; i < 5; i++) {
      await expect(login({ email: "nobody@cfo.demo", password: "x" })).rejects.toMatchObject({ status: 401 });
    }
    await expect(login({ email: "nobody@cfo.demo", password: "x" })).rejects.toMatchObject({ status: 429 });

    vi.setSystemTime(new Date(start.getTime() + 61_000));
    await expect(login({ email: "nobody@cfo.demo", password: "x" })).rejects.toMatchObject({ status: 401 });
  });

  it("does not rate-limit a known account", async () => {
    for (let i = 0; i < 7; i++) {
      await expect(login({ email: "dispatcher@cfo.demo", password: "x" })).resolves.toBeDefined();
    }
  });
});

describe("session endpoints", () => {
  it("returns the signed-in user from /auth/me (assumed same shape as login.user)", async () => {
    const { access_token, user } = await login({ email: "wm.got@cfo.demo", password: "x" });
    useAuthStore.setState({ token: access_token });

    await expect(fetchMe()).resolves.toEqual(user);
  });

  it("answers 401 on /auth/me without a token, and the client keeps no session", async () => {
    await expect(fetchMe()).rejects.toMatchObject({ code: "AUTH_INVALID", status: 401 });
    expect(useAuthStore.getState().token).toBeNull();
  });

  it("logs out with 204", async () => {
    await expect(logout()).resolves.toBeUndefined();
  });

  it("echoes X-Correlation-ID like the real API (docs/06 mục 1)", async () => {
    const res = await fetch(`${API_BASE_URL}/auth/me`, { headers: { "X-Correlation-ID": "abc-123" } });
    expect(res.headers.get("X-Correlation-ID")).toBe("abc-123");
  });
});

describe("GET /orders/counts follows docs/06 mục 5.4", () => {
  interface Counts {
    all: number;
    needs_plan: number;
    awaiting_approval: number;
    no_feasible_date: number;
    in_execution: number;
    replan_suggested: number;
    delivered_today: number;
    nav: { order_queue: number; exceptions: number; tracking_risk: number };
  }
  interface OrderList {
    total: number;
    items: { status: string; risk_color: string | null }[];
  }
  interface AlertList {
    items: { type: string; resolved_at?: string | null }[];
  }

  it("returns the v1.4 shape: `all`, the bucket counts and `nav` (no `total`)", async () => {
    const counts = await apiGet<Counts>("/orders/counts");

    expect(counts).not.toHaveProperty("total");
    expect(Object.keys(counts).sort()).toEqual(
      ["all", "awaiting_approval", "delivered_today", "in_execution", "nav", "needs_plan", "no_feasible_date", "replan_suggested"],
    );
    expect(Object.keys(counts.nav).sort()).toEqual(["exceptions", "order_queue", "tracking_risk"]);
  });

  it("matches the demo seed bucket by bucket (APPROVED in in_execution, delivered today only)", async () => {
    const counts = await apiGet<Counts>("/orders/counts");

    expect(counts).toEqual({
      all: 9,
      needs_plan: 0,
      awaiting_approval: 2,
      no_feasible_date: 2,
      in_execution: 4,
      replan_suggested: 0,
      delivered_today: 1,
      nav: { order_queue: 4, exceptions: 2, tracking_risk: 1 },
    });
  });

  it("derives nav.exceptions from open EXCEPTION / REPLAN_SUGGESTED alerts, not from order status", async () => {
    const counts = await apiGet<Counts>("/orders/counts");
    const alerts = await apiGet<AlertList>("/alerts");
    const open = alerts.items.filter((a) => ["EXCEPTION", "REPLAN_SUGGESTED"].includes(a.type) && !a.resolved_at);

    expect(counts.nav.exceptions).toBe(open.length);
  });

  it("keeps legacy BLOCKED_UNMAPPED_SKU orders out of the CFO list, detail and counts (DEC-ROUTING-002)", async () => {
    const orders = await apiGet<OrderList>("/orders");
    const filtered = await apiGet<OrderList>("/orders", { status: "BLOCKED_UNMAPPED_SKU" });
    const counts = await apiGet<Counts>("/orders/counts");

    expect(orders.items.some((o) => o.status === "BLOCKED_UNMAPPED_SKU")).toBe(false);
    expect(filtered.total).toBe(0);
    expect(counts.all).toBe(orders.items.length); // seed không có đơn đóng trước hôm nay, nên all = số đơn CFO
  });

  it("returns 404 for the legacy order detail instead of serving it as a CFO order", async () => {
    await expect(apiGet("/orders/156")).rejects.toMatchObject({ status: 404, code: "NOT_FOUND" });
  });
});

describe("GET /orders follows docs/06 mục 5.4", () => {
  interface ListBody {
    items: { id: number; [key: string]: unknown }[];
    page: number;
    page_size: number;
    total: number;
  }
  const idsOf = (body: ListBody) => body.items.map((i) => i.id);

  it("returns {items, page, page_size, total}, default order = submitted_at ASC, id ASC", async () => {
    const body = await apiGet<ListBody>("/orders");

    expect(body).toMatchObject({ page: 1, page_size: 50, total: 9 });
    expect(idsOf(body)).toEqual([118, 131, 141, 138, 129, 144, 160, 123, 137]);
  });

  it("items have the v1.4 fields (no legacy site_name/date_from/created_at)", async () => {
    const body = await apiGet<ListBody>("/orders");

    expect(Object.keys(body.items[0]).sort()).toEqual([
      "block_reason", "committed_date", "currency", "customer_name", "date_request", "id", "order_no", "origin_store",
      "promise_end", "risk_color", "site", "status", "submitted_at", "total_amount", "warehouse",
    ]);
  });

  it("paginates with page and page_size", async () => {
    const body = await apiGet<ListBody>("/orders", { page: "2", page_size: "2" });

    expect(body).toMatchObject({ page: 2, page_size: 2, total: 9 });
    expect(idsOf(body)).toEqual([141, 138]);
  });

  it("filters by warehouse_id and q (order_no, external_ref, customer)", async () => {
    expect(idsOf(await apiGet<ListBody>("/orders", { warehouse_id: "1" }))).toEqual([118, 160, 123]);
    expect(idsOf(await apiGet<ListBody>("/orders", { q: "pos-141" }))).toEqual([141]);
  });

  it("rejects invalid paging/sort with 422 VALIDATION_ERROR", async () => {
    await expect(apiGet("/orders", { page_size: "201" })).rejects.toMatchObject({ status: 422, code: "VALIDATION_ERROR" });
    await expect(apiGet("/orders", { sort: "customer_name" })).rejects.toMatchObject({ status: 422, code: "VALIDATION_ERROR" });
  });
});

describe("no password literals in mock sources (docs/09 bất biến 25)", () => {
  const sources = import.meta.glob("./*.ts", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

  it.each(Object.entries(sources).filter(([path]) => !path.includes(".test.")))("%s", (_path, source) => {
    expect(source).not.toMatch(/\bpassword\s*:\s*["'`][^"'`]+["'`]/i);
  });
});

describe("mock sources use the shared API_BASE_URL", () => {
  const sources = import.meta.glob("./*.ts", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

  it.each(Object.entries(sources).filter(([path]) => !path.includes(".test.")))("%s has no hardcoded host", (_path, source) => {
    expect(source).not.toMatch(/localhost:\d+/);
  });
});