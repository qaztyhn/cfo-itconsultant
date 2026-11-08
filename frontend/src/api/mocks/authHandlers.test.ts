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

async function signInAs(email: string): Promise<void> {
  const { access_token } = await login({ email, password: "x" });
  useAuthStore.setState({ token: access_token });
}

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
});

describe("login rate limit — ASM-003 (5 lần/60 giây/IP, kể cả lần thành công)", () => {
  const start = new Date("2026-11-07T10:00:00Z");
  const ok = { email: "dispatcher@cfo.demo", password: "x" };

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(start);
  });

  it("blocks the 6th attempt with 429 AUTH_INVALID even when the first 5 succeeded, then recovers after 60s", async () => {
    for (let i = 0; i < 5; i++) {
      await expect(login(ok)).resolves.toBeDefined();
    }
    await expect(login(ok)).rejects.toMatchObject({
      status: 429,
      code: "AUTH_INVALID",
      message: "Too many login attempts. Try again in a minute.",
    });

    vi.setSystemTime(new Date(start.getTime() + 61_000));
    await expect(login(ok)).resolves.toBeDefined();
  });

  it("counts successful and failed attempts together", async () => {
    for (let i = 0; i < 3; i++) {
      await expect(login({ email: "nobody@cfo.demo", password: "x" })).rejects.toMatchObject({ status: 401 });
    }
    await expect(login(ok)).resolves.toBeDefined();
    await expect(login(ok)).resolves.toBeDefined();
    await expect(login(ok)).rejects.toMatchObject({ status: 429 });
  });

  it("shares one counter across different emails (per IP, not per email)", async () => {
    for (const a of MOCK_ACCOUNTS.slice(0, 5)) {
      await expect(login({ email: a.email, password: "x" })).resolves.toBeDefined();
    }
    await expect(login({ email: MOCK_ACCOUNTS[5].email, password: "x" })).rejects.toMatchObject({ status: 429 });
  });

  it("does not count 422 validation errors toward the limit", async () => {
    for (let i = 0; i < 4; i++) {
      await expect(login(ok)).resolves.toBeDefined();
    }
    await expect(login({ ...ok, password: "" })).rejects.toMatchObject({ status: 422 });
    await expect(login(ok)).resolves.toBeDefined(); // lần thứ 5
    await expect(login(ok)).rejects.toMatchObject({ status: 429 });
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
  beforeEach(() => signInAs("dispatcher@cfo.demo"));
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
  beforeEach(() => signInAs("dispatcher@cfo.demo"));  
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

describe("mock authorization: xác thực, role/scope, lọc trường (docs/06 mục 3, 5.2, 5.3, 9)", () => {
  // Đây là test của MOCK. Nó không chứng minh API thật đã bảo vệ dữ liệu; backend vẫn phải có test 401/403/404 riêng.
  type Row = Record<string, unknown>;
  interface ListBody { items: Row[]; total: number }
  interface CountsBody { all: number; awaiting_approval: number; in_execution: number; delivered_today: number; nav: { exceptions: number } }
  const idsOf = (body: ListBody) => body.items.map((i) => i.id);

  describe("không có token → 401 AUTH_INVALID", () => {
    it.each(["/orders", "/orders/counts", "/orders/123", "/gps/live"])("%s", async (path) => {
      await expect(apiGet(path)).rejects.toMatchObject({ status: 401, code: "AUTH_INVALID" });
    });
  });

  describe("viewer (Business owner / Project lead) → 403 FORBIDDEN trên đơn", () => {
    it.each(["owner@cfo.demo", "projectlead@cfo.demo"])("%s", async (email) => {
      await signInAs(email);
      for (const path of ["/orders", "/orders/counts", "/orders/123"]) {
        await expect(apiGet(path)).rejects.toMatchObject({ status: 403, code: "FORBIDDEN" });
      }
    });
  });

  describe("GET /gps/live chỉ dispatcher", () => {
    it("dispatcher đọc được vị trí", async () => {
      await signInAs("dispatcher@cfo.demo");
      const body = await apiGet<{ positions: unknown[] }>("/gps/live");
      expect(body.positions.length).toBeGreaterThan(0);
    });

    it.each(["admin@cfo.demo", "wm.got@cfo.demo", "sales@cfo.demo", "driver1@cfo.demo", "cs@cfo.demo", "owner@cfo.demo"])(
      "%s bị 403",
      async (email) => {
        await signInAs(email);
        await expect(apiGet("/gps/live")).rejects.toMatchObject({ status: 403, code: "FORBIDDEN" });
      },
    );
  });

  describe("phạm vi đơn theo vai trò (mục 5.2)", () => {
    it.each(["dispatcher@cfo.demo", "admin@cfo.demo", "cs@cfo.demo", "sales@cfo.demo"])("%s thấy cả 9 đơn CFO", async (email) => {
      await signInAs(email);
      expect((await apiGet<ListBody>("/orders")).total).toBe(9);
    });

    it("warehouse chỉ thấy đơn của kho mình (wm.got → kho 1)", async () => {
      await signInAs("wm.got@cfo.demo");
      expect(idsOf(await apiGet<ListBody>("/orders"))).toEqual([118, 160, 123]);
    });

    it("warehouse lọc theo kho ngoài phạm vi → danh sách rỗng", async () => {
      await signInAs("wm.got@cfo.demo");
      const body = await apiGet<ListBody>("/orders", { warehouse_id: "2" });
      expect(body.total).toBe(0);
      expect(body.items).toEqual([]);
    });

    it("driver chỉ thấy đơn trên chuyến của mình", async () => {
      await signInAs("driver1@cfo.demo");
      expect(idsOf(await apiGet<ListBody>("/orders"))).toEqual([129]);
    });

    it("/orders/counts đếm theo phạm vi của người gọi", async () => {
      await signInAs("wm.got@cfo.demo");
      expect(await apiGet<CountsBody>("/orders/counts")).toMatchObject({
        all: 3, awaiting_approval: 2, in_execution: 0, delivered_today: 1, nav: { exceptions: 0 },
      });
    });

    it("/orders/counts của driver chỉ tính đơn của mình", async () => {
      await signInAs("driver1@cfo.demo");
      expect(await apiGet<CountsBody>("/orders/counts")).toMatchObject({ all: 1, in_execution: 1 });
    });

    it("đơn ngoài phạm vi → 404 NOT_FOUND (không lộ sự tồn tại)", async () => {
      await signInAs("wm.got@cfo.demo");
      await expect(apiGet("/orders/141")).rejects.toMatchObject({ status: 404, code: "NOT_FOUND" }); // đơn kho STO
    });

    it("driver mở đơn không thuộc chuyến mình → 404, đơn của mình → 200", async () => {
      await signInAs("driver1@cfo.demo");
      await expect(apiGet("/orders/123")).rejects.toMatchObject({ status: 404, code: "NOT_FOUND" });
      await expect(apiGet("/orders/129")).resolves.toMatchObject({ id: 129 });
    });
  });

  describe("lọc trường theo vai trò: trường bị cấm bị bỏ hẳn, không trả null (mục 5.3, 5.4)", () => {
    const DRIVER_LIST_FORBIDDEN = ["origin_store", "block_reason", "total_amount", "currency", "risk_color", "date_request"];

    it("danh sách: dispatcher có đủ trường, driver thì không", async () => {
      await signInAs("dispatcher@cfo.demo");
      const full = (await apiGet<ListBody>("/orders")).items[0];
      for (const key of DRIVER_LIST_FORBIDDEN) expect(full).toHaveProperty(key);

      useAuthStore.setState({ token: null });
      resetLoginRateLimit();
      await signInAs("driver1@cfo.demo");
      const limited = (await apiGet<ListBody>("/orders")).items[0];
      for (const key of DRIVER_LIST_FORBIDDEN) expect(limited).not.toHaveProperty(key);
      expect(limited).toHaveProperty("customer_name");
    });

    it("chi tiết: dispatcher có approved_plan_id và khối lượng/thể tích", async () => {
      await signInAs("dispatcher@cfo.demo");
      expect(await apiGet<Row>("/orders/129")).toMatchObject({ approved_plan_id: 129, total_kg: 1200, total_m3: 3 });
    });

    it.each(["sales@cfo.demo", "cs@cfo.demo"])("chi tiết: %s không có approved_plan_id, total_kg, total_m3", async (email) => {
      await signInAs(email);
      const detail = await apiGet<Row>("/orders/129");
      for (const key of ["approved_plan_id", "total_kg", "total_m3"]) expect(detail).not.toHaveProperty(key);
      expect(detail).toHaveProperty("customer_name");
    });

    it("chi tiết: driver chỉ còn tên khách, giao hàng và cửa sổ giờ", async () => {
      await signInAs("driver1@cfo.demo");
      const detail = await apiGet<Row>("/orders/129");
      for (const key of ["approved_plan_id", "total_kg", "total_m3", "risk_color", "risk_status", "date_mode", "date_from", "date_to"]) {
        expect(detail).not.toHaveProperty(key);
      }
      expect(detail).toMatchObject({ customer_name: "Privatperson Malmö", window_start: "12:00", window_end: "18:00" });
      expect(detail).toHaveProperty("site_address");
    });
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