/**
 * Test Plan Review (phần trình bày): thứ tự rank, nhiều xe, 5 gate, hold, trạng thái tải/rỗng/lỗi/stale, quyền xem.
 * Mock MSW chỉ mô phỏng hợp đồng docs/06 mục 6; KHÔNG chứng minh backend thật. Owner: Dev 3 (luồng C) — M4–M5.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { API_BASE_URL } from "../../api/config";
import { handlers } from "../../api/mocks/handlers";
import { MOCK_RUN_IDS, resetPlanningMock } from "../../api/mocks/planningHandlers";
import { MOCK_TOKEN_PREFIX } from "../../api/mocks/authHandlers";
import { useAuthStore } from "../../app/store";
import { renderAt, userByEmail } from "../../test/utils";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => resetPlanningMock());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

/** Mock authorize() cần token dạng `mock-jwt.<id>`, nên không dùng signInAs mặc định ("test-token"). */
function signIn(email: string): void {
  const user = userByEmail(email);
  useAuthStore
    .getState()
    .setAuth({ access_token: `${MOCK_TOKEN_PREFIX}${user.id}`, token_type: "bearer", expires_in: 28_800, user }, email);
}

const runUrl = (id: number) => `/dispatcher/plan-review/${id}`;
const planCards = () => screen.getAllByRole("article");
const apiError = (status: number, code: string, message: string, correlationId = "corr-test-1") =>
  HttpResponse.json({ error: { code, message, correlation_id: correlationId } }, { status, headers: { "X-Correlation-ID": correlationId } });

describe("PlanReview — plans", () => {
  beforeEach(() => signIn("dispatcher@cfo.demo"));

  it("shows plans in the order the API returns them, RECOMMENDED only on rank 1", async () => {
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    await screen.findByRole("heading", { name: /Plan #1/ });
    const cards = planCards();
    expect(cards.map((c) => c.getAttribute("data-rank"))).toEqual(["1", "2", "3"]);
    expect(within(cards[0]).getByText("RECOMMENDED")).toBeInTheDocument();
    expect(within(cards[1]).queryByText("RECOMMENDED")).not.toBeInTheDocument();
    expect(within(cards[0]).getByText("0.26")).toBeInTheDocument();
    expect(screen.getAllByText(/lower is better/i).length).toBeGreaterThan(0);
  });

  it("does not re-sort plans when the API returns a different order", async () => {
    const original = await fetch(`${API_BASE_URL}/planning-runs/${MOCK_RUN_IDS.normal}`, {
      headers: { Authorization: `Bearer ${MOCK_TOKEN_PREFIX}1` },
    }).then((r) => r.json());
    const swapped = { ...original, plans: [original.plans[1], original.plans[0], original.plans[2]] };
    server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => HttpResponse.json(swapped)));

    renderAt(runUrl(MOCK_RUN_IDS.normal));

    await screen.findAllByRole("article");
    expect(planCards().map((c) => c.getAttribute("data-rank"))).toEqual(["2", "1", "3"]);
  });

  it("shows at most 3 plans", async () => {
    const original = await fetch(`${API_BASE_URL}/planning-runs/${MOCK_RUN_IDS.normal}`, {
      headers: { Authorization: `Bearer ${MOCK_TOKEN_PREFIX}1` },
    }).then((r) => r.json());
    const extra = { ...original.plans[2], id: 9999, rank: 4 };
    server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => HttpResponse.json({ ...original, plans: [...original.plans, extra] })));

    renderAt(runUrl(MOCK_RUN_IDS.normal));

    await screen.findAllByRole("article");
    expect(planCards()).toHaveLength(3);
  });

  it("lists every vehicle of a multi-vehicle plan with a total summary", async () => {
    renderAt(runUrl(MOCK_RUN_IDS.multiVehicle));

    await screen.findAllByRole("article");
    const first = planCards()[0];
    expect(within(first).getByText(/2 trucks/)).toBeInTheDocument();
    expect(within(first).getByText("GBG-12-03")).toBeInTheDocument();
    expect(within(first).getByText("GBG-18-01")).toBeInTheDocument();
  });

  it("shows all 5 feasibility gates with text, not colour alone", async () => {
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    await screen.findAllByRole("article");
    const gates = within(planCards()[0]).getByRole("group", { name: "Feasibility gates" });
    for (const name of ["Stock", "Preparation", "Truck", "Site/Date", "Safety"]) {
      expect(within(gates).getByLabelText(`${name}: passed`)).toHaveTextContent(name);
    }
  });

  it("renders a failed gate with its code and a ✕ marker", async () => {
    const original = await fetch(`${API_BASE_URL}/planning-runs/${MOCK_RUN_IDS.normal}`, {
      headers: { Authorization: `Bearer ${MOCK_TOKEN_PREFIX}1` },
    }).then((r) => r.json());
    original.plans[0].checks.truck = { passed: false, code: "TRUCK_BUSY" };
    server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => HttpResponse.json(original)));

    renderAt(runUrl(MOCK_RUN_IDS.normal));

    await screen.findAllByRole("article");
    const chip = within(planCards()[0]).getByLabelText("Truck: failed");
    expect(chip).toHaveTextContent("✕");
    expect(within(planCards()[0]).getByText("TRUCK_BUSY")).toBeInTheDocument();
  });

  it("never shows money or cost", async () => {
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    await screen.findAllByRole("article");
    expect(document.body.textContent).not.toMatch(/\$|€|\bSEK\b|\bkr\b|\bcost\b|\bprice\b/i);
  });

  it("shows the driver name to a dispatcher", async () => {
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    await screen.findAllByRole("article");
    expect(within(planCards()[0]).getByText(/Driver #71/)).toBeInTheDocument();
  });

  it("explains why other candidates were rejected", async () => {
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    const table = await screen.findByRole("table", { name: /not ranked/i });
    expect(within(table).getByText("OUTSIDE_RECEIVING_HOURS")).toBeInTheDocument();
    expect(within(table).getAllByRole("row")).toHaveLength(5); // header + 4 candidates
  });

  it("shows an empty state with failed gate and earliest date for an infeasible run", async () => {
    renderAt(runUrl(MOCK_RUN_IDS.infeasible));

    expect(await screen.findByText(/No feasible plan for this order/)).toHaveTextContent(/Failed gate: Truck/);
    expect(screen.getByText(/Earliest feasible date 2026-11-12/)).toBeInTheDocument();
    expect(screen.queryAllByRole("article")).toHaveLength(0);
  });
});

describe("PlanReview — hold", () => {
  beforeEach(() => signIn("dispatcher@cfo.demo"));

  it("shows a countdown timer while the hold is active", async () => {
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    const timer = await screen.findByRole("timer");
    expect(timer).toHaveAccessibleName(/Hold expires in 1\d:\d\d|Hold expires in 0\d:\d\d/);
    expect(screen.getByText("Extended 0 of 2")).toBeInTheDocument();
  });

  it("shows an expired alert (text + ⌛) and no timer for an expired hold", async () => {
    renderAt(runUrl(MOCK_RUN_IDS.expired));

    const countdown = await waitFor(() => {
      const el = document.querySelector("[data-component=HoldCountdown]");
      expect(el).toHaveAttribute("data-expired", "true");
      return el as HTMLElement;
    });
    expect(within(countdown).getByRole("alert")).toHaveTextContent(/⌛.*Hold expired/);
    expect(screen.queryByRole("timer")).not.toBeInTheDocument();
  });

  it("switches to expired when the countdown reaches zero", async () => {
    const original = await fetch(`${API_BASE_URL}/planning-runs/${MOCK_RUN_IDS.normal}`, {
      headers: { Authorization: `Bearer ${MOCK_TOKEN_PREFIX}1` },
    }).then((r) => r.json());
    const soon = { ...original, hold_expires_at: new Date(Date.now() + 1500).toISOString() };
    server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => HttpResponse.json(soon)));

    renderAt(runUrl(MOCK_RUN_IDS.normal));

    await screen.findByRole("timer");
    await waitFor(() => expect(document.querySelector("[data-component=HoldCountdown]")).toHaveAttribute("data-expired", "true"), { timeout: 4000 });
    expect(screen.queryByRole("timer")).not.toBeInTheDocument();
  });
});

describe("PlanReview — states", () => {
  beforeEach(() => signIn("dispatcher@cfo.demo"));

  it("shows a loading state before data arrives", async () => {
    server.use(
      http.get(`${API_BASE_URL}/planning-runs/:id`, async () => {
        await delay(150);
        return HttpResponse.json({});
      }),
    );
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    expect(await screen.findByText("Loading…")).toBeInTheDocument();
    expect(screen.getByRole("status", { busy: true })).toBeInTheDocument();
  });

  it("shows 'not found' for a non-numeric run id without calling the API", async () => {
    renderAt("/dispatcher/plan-review/abc");

    expect(await screen.findByText("Planning run not found.")).toBeInTheDocument();
  });

  it("shows an error with the correlation ID and Retry, and recovers on Retry", async () => {
    server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => apiError(500, "INTERNAL_ERROR", "Planning service failed.", "corr-retry-42"), { once: true }));
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    expect(await screen.findByRole("alert")).toHaveTextContent("Planning service failed.");
    expect(screen.getByText("corr-retry-42")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findAllByRole("article")).toHaveLength(3);
  });

  it("shows permission denied without a Retry button on 403", async () => {
    server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => apiError(403, "FORBIDDEN", "Your role cannot access this resource.")));
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    expect(await screen.findByText("You don't have permission to view this.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("shows fresh data without a warning when the integration overview is fresh", async () => {
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    const freshness = await screen.findByText(/Data as of/);
    expect(freshness.closest("[data-component=DataFreshness]")).toHaveAttribute("data-stale", "false");
  });

  it("warns when the server flags the data as stale", async () => {
    server.use(
      http.get(`${API_BASE_URL}/integration/overview`, () =>
        HttpResponse.json({ sources: [{ name: "WMS stock", data_as_of: "2026-11-04T08:00:00+01:00" }], next_sync_at: null, stale: true }),
      ),
    );
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    const warning = await screen.findByText(/Stale data/);
    expect(warning.closest("[data-component=DataFreshness]")).toHaveAttribute("data-stale", "true");
    expect(warning.closest("[data-component=DataFreshness]")).toHaveTextContent("⚠");
  });

  it("treats a failing integration overview as 'freshness unknown' and still shows plans", async () => {
    server.use(http.get(`${API_BASE_URL}/integration/overview`, () => apiError(404, "NOT_FOUND", "Not found.")));
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    expect(await screen.findByText(/Data freshness unknown/)).toBeInTheDocument();
    expect(screen.getByText(/Verify before approving/)).toBeInTheDocument();
    expect(await screen.findAllByRole("article")).toHaveLength(3);
  });
});

describe("PlanReview — access", () => {
  it("blocks a sales user from the page", async () => {
    signIn("sales@cfo.demo");
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    await waitFor(() => expect(screen.queryAllByRole("article")).toHaveLength(0));
    expect(screen.queryByText(/Driver /)).not.toBeInTheDocument();
    expect(screen.queryByText("0.26")).not.toBeInTheDocument();
  });

  it("hides driver names for a non-dispatcher even when the API returns them (admin)", async () => {
    signIn("admin@cfo.demo");
    renderAt(runUrl(MOCK_RUN_IDS.normal));

    await new Promise((resolve) => setTimeout(resolve, 300));expect(screen.queryByText(/Driver #71/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Driver #71/)).not.toBeInTheDocument();
  });
});