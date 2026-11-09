/** M2 Data Integration dashboard contract tests (no global MSW modifications). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthUser } from "../../api/contracts/auth";
import { useAuthStore } from "../../app/store";
import { DataIntegration } from "./DataIntegration";
import { CONTRACT_OVERVIEW, CONTRACT_REJECTS, CONTRACT_RUNS } from "./integration/contractPreview";

const ADMIN: AuthUser = {
  id: 100, employee_id: 2, name: "Synthetic IT Admin", roles: ["admin"],
  market: "SE", location_ids: [], locale: "en", kpi_scopes: [],
};
const VIEWER: AuthUser = {
  ...ADMIN, id: 200, roles: ["viewer"], kpi_scopes: ["revenue_all"],
};

type MockReply = { status?: number; body?: unknown };
const good: MockReply = { status: 200, body: CONTRACT_OVERVIEW };
const runsReply: MockReply = { status: 200, body: CONTRACT_RUNS };

function startSession(user: AuthUser): void {
  useAuthStore.getState().setAuth({
    access_token: "synthetic-test-token", token_type: "bearer", expires_in: 3600, user,
  }, "integration-test@synthetic.invalid");
}

function mockApi(replies: {
  overview?: MockReply;
  runs?: MockReply;
  rejects?: MockReply;
} = {}) {
  const calls: { path: string; method: string }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const path = url.pathname;
    const method = init?.method ?? "GET";
    calls.push({ path: path + url.search, method });
    let response: MockReply;
    if (path.endsWith("/integration/overview")) response = replies.overview ?? good;
    else if (path.endsWith("/sync-runs")) response = replies.runs ?? runsReply;
    else if (/\/sync-runs\/\d+\/rejects$/.test(path)) response = replies.rejects ?? { body: CONTRACT_REJECTS };
    else return new Response(null, { status: 404 });
    return new Response(JSON.stringify(response.body ?? {}), {
      status: response.status ?? 200,
      headers: { "Content-Type": "application/json", "X-Correlation-ID": "11111111-2222-3333-4444-555555555555" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
    mutations: { retry: false },
  } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><DataIntegration /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  startSession(ADMIN);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("US-ADM-01 AC1: admin operational dashboard", () => {
  it("shows exactly five sources, source freshness, partial failure and separate unmapped count", async () => {
    mockApi();
    renderDashboard();
    await waitFor(() => expect(document.querySelectorAll('[data-testid^="feed-"]')).toHaveLength(5));
    expect(await screen.findByText("Recent integration runs")).toBeInTheDocument();
    const inbound = screen.getByTestId("feed-inbound");
    const products = screen.getByTestId("feed-products");
    const stock = screen.getByTestId("feed-stock");
    expect(within(inbound).getByText(/PARTIAL · incomplete/)).toBeInTheDocument();
    expect(within(products).getByText(/3 unmapped SKUs/)).toBeInTheDocument();
    expect(within(products).getByText(/0 rejected/)).toBeInTheDocument();
    expect(within(stock).getByText(/BLOCKED/)).toBeInTheDocument();
    expect(within(stock).getByText(/unknown, never zero/)).toBeInTheDocument();
    expect(within(stock).getByText(/Last run result: failed/)).toBeInTheDocument();
    expect(within(stock).getByText(/Data as of: 2026-11-04 09:00 UTC/)).toBeInTheDocument();
    expect(screen.getByText(/Active background worker is not verified/)).toBeInTheDocument();
    expect(screen.getByText(/25/)).toBeInTheDocument();
  });

  it("retrieves allowlisted reject reason details, never raw PII", async () => {
    const { calls } = mockApi();
    const { container } = renderDashboard();
    const inspect = await screen.findAllByRole("button", { name: /Inspect rejects/i });
    await userEvent.click(inspect[2]); // the partial inbound run from the contract fixture
    await waitFor(() => expect(calls.some((entry) =>
      entry.path.includes("/sync-runs/302/rejects"))).toBe(true));
    expect(await screen.findByText("Quantity failed source validation.").catch(() => null)).toBeNull();
    expect(await screen.findByText("Date did not pass validation.")).toBeInTheDocument();
    const html = container.textContent ?? "";
    expect(html).not.toContain("PRIVATE");
    expect(html).not.toContain("redacted@example.test");
    expect(html).not.toContain("PRIVATE-ORDER-REFERENCE");
    expect(html).not.toContain("SENSITIVE: phone and address");
  });

  it("has real loading and empty states, no invented successes", async () => {
    let unblock!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { unblock = resolve; })));
    renderDashboard();
    expect(screen.getAllByText(/Loading…/).length).toBeGreaterThan(0);
    // Pending requests intentionally have no data. Unblock via an explicit retry
    // in a separate test, not by pretending a timeout proves success.
    expect(screen.queryByText(/A sync completed/)).not.toBeInTheDocument();
    expect(typeof unblock).toBe("function");
  });

  it("shows empty recent history without fabricating an OK status", async () => {
    mockApi({ overview: { body: { sources: {} } }, runs: { body: { items: [] } } });
    renderDashboard();
    expect(await screen.findByText("No integration run history is available.")).toBeInTheDocument();
    expect(screen.getByTestId("feed-orders")).toHaveTextContent("UNVERIFIED");
    expect(screen.getByTestId("feed-stock")).toHaveTextContent("BLOCKED");
  });

  it("reports 503 STOCK_UNAVAILABLE without showing zero stock or server error PII", async () => {
    mockApi({ overview: { status: 503, body: {
      error: { code: "STOCK_UNAVAILABLE", message: "PRIVATE CUSTOMER ADDRESS" },
    } } });
    renderDashboard();
    expect(await screen.findByText("Source snapshot unavailable (not zero)")).toBeInTheDocument();
    expect(screen.getByText("Recent integration runs")).toBeInTheDocument();
    expect(screen.getByTestId("feed-stock")).toHaveTextContent("unknown, never zero");
    expect(document.body.textContent).not.toContain("PRIVATE CUSTOMER ADDRESS");
  });

  it("retries unavailable overview with a later successful response", async () => {
    let attempt = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input)).pathname;
      if (path.endsWith("/integration/overview") && ++attempt === 1) {
        return new Response(JSON.stringify({ error: { code: "INTERNAL_ERROR", message: "PRIVATE" } }), { status: 500 });
      }
      return Response.json(path.endsWith("/sync-runs") ? CONTRACT_RUNS : CONTRACT_OVERVIEW);
    }));
    renderDashboard();
    expect(await screen.findByText("Source overview unavailable")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByTestId("feed-orders")).toHaveTextContent("12"));
    expect(screen.queryByText("Source overview unavailable")).not.toBeInTheDocument();
  });
});

describe("US-ADM-01 AC2: read-only monitoring", () => {
  it("never calls the unimplemented sync POST", async () => {
    const { calls } = mockApi();
    renderDashboard();
    await screen.findByText("Recent integration runs");
    expect(screen.queryByRole("button", { name: "Run POS orders sync" })).not.toBeInTheDocument();
    expect(calls.every(({ method }) => method === "GET")).toBe(true);
  });

  it("requires a market before a system admin reads runs", async () => {
    startSession({ ...ADMIN, market: null });
    const { calls } = mockApi({ overview: { body: { markets: [CONTRACT_OVERVIEW] } } });
    renderDashboard();
    expect(await screen.findByText("Select a market to inspect source evidence.")).toBeInTheDocument();
    expect(calls.some(({ path }) => path.endsWith("/sync-runs"))).toBe(false);
    await waitFor(() => expect(screen.getByRole("option", { name: "SE" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Market"), "SE");
    await waitFor(() => expect(calls.some(({ path }) => path.includes("/sync-runs?market=SE"))).toBe(true));
    expect(await screen.findByTestId("feed-stock")).toHaveTextContent("BLOCKED");
  });

  it("prevents an unauthorized direct mount from fetching or syncing", async () => {
    startSession(VIEWER);
    const { calls } = mockApi();
    renderDashboard();
    expect(screen.getByText("Admin access is required. No source data was loaded.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run POS orders sync" })).not.toBeInTheDocument();
    await waitFor(() => expect(calls).toHaveLength(0));
  });
});
