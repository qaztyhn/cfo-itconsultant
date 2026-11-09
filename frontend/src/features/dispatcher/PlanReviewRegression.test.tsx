/**
 * Test hồi quy cho review PR #136: dùng dữ liệu đúng hình dạng backend (gate `passed`, xe chỉ có id, rejected phẳng)
 * và các chốt chặn Approve. Mock MSW chỉ mô phỏng hợp đồng docs/06; KHÔNG chứng minh backend thật.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { API_BASE_URL } from "../../api/config";
import type { PlanningRun } from "../../api/contracts/planning";
import { MOCK_TOKEN_PREFIX } from "../../api/mocks/authHandlers";
import { handlers } from "../../api/mocks/handlers";
import { MOCK_RUN_IDS, resetPlanningMock } from "../../api/mocks/planningHandlers";
import { PATHS } from "../../app/access";
import { useAuthStore } from "../../app/store";
import { renderAt, userByEmail } from "../../test/utils";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  resetPlanningMock();
  const email = "dispatcher@cfo.demo";
  const user = userByEmail(email);
  useAuthStore.getState().setAuth({ access_token: `${MOCK_TOKEN_PREFIX}${user.id}`, token_type: "bearer", expires_in: 28_800, user }, email);
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const runUrl = (id: number) => `${PATHS.dispatcherPlanReview}/${id}`;
const approveButton = (rank: number) => screen.getByRole("button", { name: `Approve #${rank}` });

async function loadRun(id: number): Promise<PlanningRun> {
  return fetch(`${API_BASE_URL}/planning-runs/${id}`, { headers: { Authorization: `Bearer ${MOCK_TOKEN_PREFIX}1` } }).then((r) => r.json());
}
function serveRun(run: PlanningRun): void {
  server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => HttpResponse.json(run)));
}
async function openPlan(runId: number) {
  renderAt(runUrl(runId));
  await screen.findAllByRole("article");
}
const settle = () => new Promise((resolve) => setTimeout(resolve, 150));

interface ApproveCall {
  body: Record<string, unknown>;
}
function recordApprovals(): ApproveCall[] {
  const calls: ApproveCall[] = [];
  server.use(
    http.post(`${API_BASE_URL}/plans/:id/approve`, async ({ request }) => {
      calls.push({ body: (await request.clone().json()) as Record<string, unknown> });
      return undefined;
    }),
  );
  return calls;
}

/** Ép ngày khách yêu cầu của đơn 123 và danh sách thương lượng, rồi báo khi cả hai đã được gọi. */
function serveDates(dateTo: string, negotiations: unknown[]) {
  const seen = { order: false, negotiations: false };
  server.use(
    http.get(`${API_BASE_URL}/orders/123`, () => {
      seen.order = true;
      return HttpResponse.json({ id: 123, date_request: { mode: "exact", date_from: null, date_to: dateTo } });
    }),
    http.get(`${API_BASE_URL}/orders/123/date-negotiations`, () => {
      seen.negotiations = true;
      return HttpResponse.json({ items: negotiations });
    }),
  );
  return seen;
}

describe("Dữ liệu đúng hình dạng backend", () => {
  it("renders vehicles that only have vehicle_id and driver_employee_id (no vehicle object) without crashing", async () => {
    const run = await loadRun(MOCK_RUN_IDS.normal);
    run.plans = run.plans.map((p) => ({
      ...p,
      vehicles: p.vehicles.map(({ seq, vehicle, driver_employee_id, load_kg, load_m3, loading_start_at, depart_at, eta_at }) => ({
        seq, vehicle_id: vehicle?.id, driver_employee_id, load_kg, load_m3, loading_start_at, depart_at, eta_at,
      })),
    }));
    serveRun(run);

    await openPlan(MOCK_RUN_IDS.normal);

    expect(within(screen.getAllByRole("article")[0]).getByText("#15")).toBeInTheDocument();
    expect(within(screen.getAllByRole("article")[0]).getByText(/Driver #71/)).toBeInTheDocument();
  });

  it("shows rejected candidates with the warehouse id and vehicle code from the backend", async () => {
    await openPlan(MOCK_RUN_IDS.normal);

    expect(screen.getAllByText("Warehouse #2").length).toBeGreaterThan(0);
    expect(screen.getByText("STO-12-04")).toBeInTheDocument();
  });
});

describe("Chốt chặn Approve", () => {
  it("disables Approve for a replan_suggestion even if a hold is present", async () => {
    serveRun({ ...(await loadRun(MOCK_RUN_IDS.normal)), kind: "replan_suggestion" });
    await openPlan(MOCK_RUN_IDS.normal);

    expect(approveButton(1)).toBeDisabled();
    expect(screen.getByText(/replan suggestion and cannot be approved/i)).toBeInTheDocument();
  });

  it("disables Approve when the run has no hold", async () => {
    serveRun({ ...(await loadRun(MOCK_RUN_IDS.normal)), hold_expires_at: null });
    await openPlan(MOCK_RUN_IDS.normal);

    expect(approveButton(1)).toBeDisabled();
    expect(screen.getByText(/No active hold on this run/i)).toBeInTheDocument();
  });

  it("disables Approve when the selected plan is no longer proposed", async () => {
    const run = await loadRun(MOCK_RUN_IDS.normal);
    run.plans[0].status = "approved";
    serveRun(run);
    await openPlan(MOCK_RUN_IDS.normal);

    expect(approveButton(1)).toBeDisabled();
    expect(screen.getByText(/no longer proposed/i)).toBeInTheDocument();
  });
});

describe("Run không khả thi", () => {
  it("offers Plan Again and the rejected candidates, but no Extend hold", async () => {
    await openPlan(MOCK_RUN_IDS.infeasible).catch(() => undefined);
    // Run infeasible không có thẻ phương án (article), nên chờ thông điệp thay vì article.
    await screen.findByText(/No feasible plan for this order/);

    expect(screen.getByRole("button", { name: "Plan Again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Extend hold/ })).not.toBeInTheDocument();
    expect(screen.getByText("Why other candidates were not ranked")).toBeInTheDocument();
  });
});

describe("Ngày giao khác ngày khách yêu cầu", () => {
  it("sends date_negotiation_id when an agreed negotiation matches the plan date", async () => {
    const calls = recordApprovals();
    const seen = serveDates("2026-11-12", [
      { id: 55, proposed_date: "2026-11-10", outcome: "agreed", channel: "phone", contacted_at: "2026-11-04T09:40:00Z", remind_at: null },
    ]);
    await openPlan(MOCK_RUN_IDS.normal);
    await waitFor(() => expect(seen.order && seen.negotiations).toBe(true));
    await settle();
    const user = userEvent.setup();

    await user.click(approveButton(1));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));

    expect(await screen.findByText(/Approved · order status APPROVED/)).toBeInTheDocument();
    expect(calls[0].body).toEqual({ date_negotiation_id: 55 });
  });

  it("blocks Approve and explains why when there is no agreement for the plan date", async () => {
    serveDates("2026-11-12", [
      { id: 56, proposed_date: "2026-11-11", outcome: "agreed", channel: "phone", contacted_at: "2026-11-04T09:40:00Z", remind_at: null },
    ]);
    await openPlan(MOCK_RUN_IDS.normal);

    await waitFor(() => expect(approveButton(1)).toBeDisabled());
    expect(screen.getByText(/differs from the customer's requested date/i)).toBeInTheDocument();
  });

  it("does not send date_negotiation_id when the plan date matches the requested date", async () => {
    const calls = recordApprovals();
    const seen = serveDates("2026-11-10", []);
    await openPlan(MOCK_RUN_IDS.normal);
    await waitFor(() => expect(seen.order && seen.negotiations).toBe(true));
    await settle();
    const user = userEvent.setup();

    await user.click(approveButton(1));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));

    expect(await screen.findByText(/Approved · order status APPROVED/)).toBeInTheDocument();
    expect(calls[0].body).toEqual({});
  });
});

describe("Tight schedule", () => {
  it("requires the tick before Approve and resets it when another plan is selected", async () => {
    serveRun({ ...(await loadRun(MOCK_RUN_IDS.normal)), reserve_class: "tight" });
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();
    const tick = screen.getByRole("checkbox", { name: "I accept the tight schedule" });

    expect(approveButton(1)).toBeDisabled();
    await user.click(tick);
    expect(approveButton(1)).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Select plan #2" }));
    expect(tick).not.toBeChecked();
    expect(approveButton(2)).toBeDisabled();
  });

  it("shows no tick for a safe run", async () => {
    await openPlan(MOCK_RUN_IDS.normal);

    expect(screen.queryByRole("checkbox", { name: "I accept the tight schedule" })).not.toBeInTheDocument();
  });
});