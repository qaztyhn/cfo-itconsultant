/**
 * Test tương tác của Plan Review: gia hạn hold, Plan Again, luồng duyệt (lý do bắt buộc, Idempotency-Key, 409).
 * Mock MSW chỉ mô phỏng hợp đồng docs/06 mục 6; KHÔNG chứng minh backend thật duyệt được (T16 vẫn fail-closed).
 * Owner: Dev 3 (luồng C) — M4–M5.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { API_BASE_URL } from "../../api/config";
import { MOCK_TOKEN_PREFIX } from "../../api/mocks/authHandlers";
import { handlers } from "../../api/mocks/handlers";
import { MOCK_RUN_IDS, resetPlanningMock } from "../../api/mocks/planningHandlers";
import { PATHS } from "../../app/access";
import { useAuthStore } from "../../app/store";
import { currentPath, renderAt, userByEmail } from "../../test/utils";

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
const approveUrl = `${API_BASE_URL}/plans/:id/approve`;

function apiError(status: number, code: string, message: string, details?: unknown) {
  return HttpResponse.json({ error: { code, message, details, correlation_id: "corr-test-9" } }, { status, headers: { "X-Correlation-ID": "corr-test-9" } });
}

interface ApproveCall {
  planId: string;
  key: string | null;
  body: Record<string, unknown>;
}

/** Ghi lại mọi lời gọi approve rồi để handler mock mặc định trả lời (trả undefined = cho đi tiếp). */
function recordApprovals(): ApproveCall[] {
  const calls: ApproveCall[] = [];
  server.use(
    http.post(approveUrl, async ({ request, params }) => {
      calls.push({ planId: String(params.id), key: request.headers.get("Idempotency-Key"), body: (await request.clone().json()) as Record<string, unknown> });
      return undefined;
    }),
  );
  return calls;
}

const approveButton = (rank: number) => screen.getByRole("button", { name: `Approve #${rank}` });
const extendButton = () => screen.getByRole("button", { name: /Extend hold/ });

async function openPlan(runId: number) {
  renderAt(runUrl(runId));
  await screen.findAllByRole("article");
}

describe("Extend hold", () => {
  it("extends the hold and shows the new count and the remaining extensions", async () => {
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    expect(extendButton()).toHaveTextContent("2 left");
    await user.click(extendButton());

    expect(await screen.findByText("Extended 1 of 2")).toBeInTheDocument();
    expect(extendButton()).toHaveTextContent("1 left");
  });

  it("disables the button after the second extension", async () => {
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(extendButton());
    await screen.findByText("Extended 1 of 2");
    await user.click(extendButton());
    await screen.findByText("Extended 2 of 2");

    expect(extendButton()).toBeDisabled();
    expect(extendButton()).toHaveTextContent("No extensions left");
  });

  it("shows the server's HOLD_EXTENSION_LIMIT answer with a reference", async () => {
    server.use(http.post(`${API_BASE_URL}/planning-runs/:id/extend`, () => apiError(409, "HOLD_EXTENSION_LIMIT", "Hold can be extended at most twice.")));
    await openPlan(MOCK_RUN_IDS.normal);

    await userEvent.setup().click(extendButton());

    const alert = await screen.findByText(/already extended twice/);
    expect(alert.closest("[role=alert]")).toHaveTextContent("Ref corr-test-9");
  });

  it("shows a HOLD_EXPIRED answer from the server", async () => {
    server.use(http.post(`${API_BASE_URL}/planning-runs/:id/extend`, () => apiError(409, "HOLD_EXPIRED", "Planning hold expired. Plan Again.")));
    await openPlan(MOCK_RUN_IDS.normal);

    await userEvent.setup().click(extendButton());

    expect(await screen.findByText("The hold has expired. Use Plan Again.")).toBeInTheDocument();
  });

  it("cannot extend an expired hold but can still Plan Again", async () => {
    await openPlan(MOCK_RUN_IDS.expired);

    expect(extendButton()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Plan Again" })).toBeEnabled();
  });
});

describe("Plan Again", () => {
  it("requires a reason before it can be confirmed", async () => {
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Plan Again" }));
    const dialog = await screen.findByRole("dialog", { name: "Plan Again" });
    const confirm = within(dialog).getByRole("button", { name: "Plan Again" });
    expect(confirm).toBeDisabled();

    await user.selectOptions(within(dialog).getByLabelText("Reason"), "criteria_change");
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Why are you planning again?"), "Customer moved the date");
    expect(confirm).toBeEnabled();
  });

  it("creates a NEW run on the same order and opens it, leaving the old run untouched", async () => {
    await openPlan(MOCK_RUN_IDS.expired);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Plan Again" }));
    const dialog = await screen.findByRole("dialog", { name: "Plan Again" });
    await user.selectOptions(within(dialog).getByLabelText("Reason"), "hold_expired");
    await user.type(within(dialog).getByLabelText("Why are you planning again?"), "Hold ran out");
    await user.click(within(dialog).getByRole("button", { name: "Plan Again" }));

    await waitFor(() => expect(currentPath()).toBe(runUrl(500)));
    expect(await screen.findByText(/RUN 2 · RERUN/)).toBeInTheDocument();
    expect(await screen.findByRole("timer")).toBeInTheDocument();

    const oldRun = await fetch(`${API_BASE_URL}/planning-runs/${MOCK_RUN_IDS.expired}`, { headers: { Authorization: `Bearer ${MOCK_TOKEN_PREFIX}1` } }).then((r) => r.json());
    expect(new Date(oldRun.hold_expires_at).getTime()).toBeLessThan(Date.now());
  });

  it("keeps the dialog open and shows the server error when Plan Again fails", async () => {
    server.use(http.post(`${API_BASE_URL}/orders/:id/plan`, () => apiError(409, "PLAN_NOT_APPROVABLE", "Order is no longer plannable.")));
    await openPlan(MOCK_RUN_IDS.expired);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Plan Again" }));
    const dialog = await screen.findByRole("dialog", { name: "Plan Again" });
    await user.selectOptions(within(dialog).getByLabelText("Reason"), "other");
    await user.type(within(dialog).getByLabelText("Why are you planning again?"), "Try again");
    await user.click(within(dialog).getByRole("button", { name: "Plan Again" }));

    expect(await within(dialog).findByText("Order is no longer plannable.")).toBeInTheDocument();
    expect(currentPath()).toBe(runUrl(MOCK_RUN_IDS.expired));
  });
});

describe("Approval", () => {
  async function backendRun() {
    return fetch(`${API_BASE_URL}/planning-runs/${MOCK_RUN_IDS.normal}`, {
      headers: { Authorization: `Bearer ${MOCK_TOKEN_PREFIX}1` },
    }).then((response) => response.json());
  }

  it("test_US_APR_01_AC1_blocks_approval_when_a_stored_gate_fails_or_is_missing", async () => {
    const run = await backendRun();
    run.plans[0].checks.safety = { passed: false, code: "SAFETY_UNKNOWN" };
    delete run.plans[1].checks.stock;
    server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => HttpResponse.json(run)));
    const calls = recordApprovals();
    await openPlan(MOCK_RUN_IDS.normal);
    expect(approveButton(1)).toBeDisabled();
    expect(screen.getByText(/All five planning gates/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Select plan #2" }));
    expect(approveButton(2)).toBeDisabled();
    expect(calls).toHaveLength(0);
  });

  it("test_US_APR_01_AC1_blocks_unheld_replan_suggestion", async () => {
    const run = await backendRun();
    server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => HttpResponse.json({ ...run, kind: "replan_suggestion", hold_expires_at: null })));
    await openPlan(MOCK_RUN_IDS.normal);
    expect(approveButton(1)).toBeDisabled();
    expect(screen.getByText(/separate dispatcher decision/)).toBeInTheDocument();
  });

  it.each([
    ["missing hold", (run: Record<string, unknown>) => ({ ...run, hold_expires_at: null })],
    ["non-proposed plan", (run: Record<string, unknown>) => ({ ...run, plans: [{ ...(run.plans as Record<string, unknown>[])[0], status: "approved" }] })],
  ])("test_US_APR_01_AC1_blocks_%s_before_sending_approval", async (_label, change) => {
    const run = await backendRun();
    server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => HttpResponse.json(change(run))));
    const calls = recordApprovals();
    await openPlan(MOCK_RUN_IDS.normal);
    expect(approveButton(1)).toBeDisabled();
    expect(calls).toHaveLength(0);
  });

  it("test_US_APR_01_AC1_requires_explicit_tight_reserve_acceptance", async () => {
    const run = await backendRun();
    server.use(http.get(`${API_BASE_URL}/planning-runs/:id`, () => HttpResponse.json({ ...run, reserve_class: "tight" })));
    await openPlan(MOCK_RUN_IDS.normal);
    expect(approveButton(1)).toBeDisabled();
    await userEvent.setup().click(screen.getByLabelText("I accept the tight schedule"));
    expect(approveButton(1)).toBeEnabled();
  });

  it("test_US_PLN_07_AC3_sends_only_matching_agreed_date", async () => {
    const run = await backendRun();
    run.plans[0].target_date = "2026-11-11";
    server.use(
      http.get(`${API_BASE_URL}/planning-runs/:id`, () => HttpResponse.json(run)),
      http.get(`${API_BASE_URL}/orders/:id/date-negotiations`, () => HttpResponse.json({ items: [
        { id: 17, proposed_date: "2026-11-12", outcome: "agreed", channel: "phone", contacted_at: "2026-11-09T10:00:00Z", remind_at: null },
        { id: 18, proposed_date: "2026-11-11", outcome: "pending", channel: "phone", contacted_at: "2026-11-09T11:00:00Z", remind_at: null },
        { id: 19, proposed_date: "2026-11-11", outcome: "agreed", channel: "phone", contacted_at: "2026-11-09T12:00:00Z", remind_at: null },
      ] })),
    );
    const calls = recordApprovals();
    await openPlan(MOCK_RUN_IDS.normal);
    expect(approveButton(1)).toBeDisabled();
    expect(screen.queryByRole("option", { name: /Agreement #17/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Agreement #18/ })).not.toBeInTheDocument();
    await screen.findByRole("option", { name: /Agreement #19/ });
    await userEvent.setup().selectOptions(screen.getByLabelText(/Customer agreement for/), "19");
    await userEvent.setup().click(approveButton(1));
    await userEvent.setup().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));
    await screen.findByText(/Approved · order status APPROVED/);
    expect(calls[0].body).toEqual({ date_negotiation_id: 19 });
  });

  it("test_US_PLN_07_AC2_shows_DATE_AGREEMENT_REQUIRED_without_approval", async () => {
    server.use(http.post(approveUrl, () => apiError(409, "DATE_AGREEMENT_REQUIRED", "Customer agreement required.")));
    await openPlan(MOCK_RUN_IDS.normal);
    await userEvent.setup().click(approveButton(1));
    await userEvent.setup().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));
    expect(await screen.findByText("Customer date agreement required")).toBeInTheDocument();
    expect(screen.queryByText(/Approved · order status/)).not.toBeInTheDocument();
  });

  it("does not call approve until the user confirms in the dialog", async () => {
    const calls = recordApprovals();
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(approveButton(1));
    const dialog = await screen.findByRole("dialog", { name: "Approve plan #1" });
    expect(calls).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("summarises the resources that will be committed (with driver for a dispatcher, no money)", async () => {
    await openPlan(MOCK_RUN_IDS.multiVehicle);
    await screen.findByRole("option", { name: /Agreement #1601/ });
    await userEvent.setup().selectOptions(screen.getByLabelText(/Customer agreement for/), "1601");
    await userEvent.setup().click(approveButton(1));

    const dialog = await screen.findByRole("dialog", { name: "Approve plan #1" });
    expect(dialog).toHaveAccessibleDescription(/GBG-12-03.*driver #71.*GBG-18-01.*driver #73/);
    expect(dialog).toHaveAccessibleDescription(/2 vehicles/);
    expect(dialog.textContent).not.toMatch(/\$|€|\bSEK\b|\bkr\b/);
  });

  it("approves rank 1 with an Idempotency-Key and only reports success when status is APPROVED", async () => {
    const calls = recordApprovals();
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(approveButton(1));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));

    expect(await screen.findByText(/Approved · order status APPROVED/)).toBeInTheDocument();
    expect(calls).toHaveLength(1);
    expect(calls[0].planId).toBe("4121");
    expect(calls[0].key).toMatch(/^[\w-]{8,}$/);
    expect(calls[0].body).toEqual({});
    expect(approveButton(1)).toBeDisabled();
    expect(screen.getByText("Plan approved.")).toBeInTheDocument();
  });

  it("requires a reason code and a note for rank 2 and sends both", async () => {
    const calls = recordApprovals();
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Select plan #2" }));
    await user.click(approveButton(2));
    const dialog = await screen.findByRole("dialog", { name: "Approve plan #2" });
    const confirm = within(dialog).getByRole("button", { name: "Approve #2" });
    expect(confirm).toBeDisabled();

    await user.selectOptions(within(dialog).getByLabelText("Reason"), "closest_to_customer");
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Why this plan instead of #1?"), "Customer site is nearer Malmö");
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    expect(await screen.findByText(/Approved · order status APPROVED/)).toBeInTheDocument();
    expect(calls[0].planId).toBe("4122");
    expect(calls[0].body).toEqual({ reason_code: "closest_to_customer", reason_text: "Customer site is nearer Malmö" });
  });

  it("requires a reason for rank 3 as well", async () => {
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Select plan #3" }));
    await user.click(approveButton(3));

    const dialog = await screen.findByRole("dialog", { name: "Approve plan #3" });
    expect(within(dialog).getByRole("button", { name: "Approve #3" })).toBeDisabled();
    expect(within(dialog).getByLabelText("Reason")).toBeInTheDocument();
  });

  it("reuses the same Idempotency-Key when retrying the same request after a failure", async () => {
    // server.use xếp handler mới lên đầu: đăng ký handler lỗi trước, bộ ghi sau để bộ ghi thấy cả lần lỗi.
    server.use(http.post(approveUrl, () => apiError(500, "INTERNAL_ERROR", "Temporary failure."), { once: true }));
    const calls = recordApprovals();
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(approveButton(1));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Approve #1" }));
    expect(await within(dialog).findByText("Temporary failure.")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Approve #1" }));
    await screen.findByText(/Approved · order status APPROVED/);

    expect(calls).toHaveLength(2);
    expect(calls[0].key).toBeTruthy();
    expect(calls[1].key).toBe(calls[0].key);
  });

  it("locks Approve and shows why when the hold is expired", async () => {
    const calls = recordApprovals();
    await openPlan(MOCK_RUN_IDS.expired);

    expect(approveButton(1)).toBeDisabled();
    expect(screen.getByText("Hold expired. Use Plan Again to continue.")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("shows the real backend's fail-closed PLAN_NOT_APPROVABLE verbatim, with no bypass and no success", async () => {
    server.use(
      http.post(approveUrl, () => apiError(409, "PLAN_NOT_APPROVABLE", "Fresh five-gate approval recheck is not connected")),
    );
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(approveButton(1));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));

    const panel = await screen.findByText("This plan cannot be approved");
    const alert = panel.closest("[role=alert]") as HTMLElement;
    expect(alert).toHaveTextContent("Fresh five-gate approval recheck is not connected");
    expect(alert).toHaveTextContent("PLAN_NOT_APPROVABLE · Ref corr-test-9");
    expect(screen.queryByText(/Approved/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /anyway|override|bypass|force/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it.each([
    ["vehicle", "A selected vehicle is no longer available."],
    ["driver", "A selected driver is no longer available."],
    ["stock", "Stock is no longer sufficient."],
    ["labour", "Warehouse preparation capacity is no longer sufficient."],
    ["five_gates", "The five-gate recheck failed against current data."],
  ])("explains RESOURCE_CONFLICT caused by %s and points to Plan Again", async (conflict, message) => {
    server.use(http.post(approveUrl, () => apiError(409, "RESOURCE_CONFLICT", "Conflict.", { conflict })));
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(approveButton(1));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));

    const alert = (await screen.findByText(/Resource conflict/)).closest("[role=alert]") as HTMLElement;
    expect(alert).toHaveTextContent(message);
    expect(alert).toHaveTextContent("Use Plan Again");
    expect(alert).toHaveTextContent("RESOURCE_CONFLICT");
    expect(screen.queryByText(/Approved/)).not.toBeInTheDocument();
  });

  it("shows a fixed panel on HOLD_EXPIRED from the server", async () => {
    server.use(http.post(approveUrl, () => apiError(409, "HOLD_EXPIRED", "Planning hold expired. Plan Again.")));
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(approveButton(1));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));

    const alert = (await screen.findAllByRole("alert")).find((a) => a.textContent?.includes("HOLD_EXPIRED"));
    expect(alert).toBeDefined();
    expect(alert).toHaveTextContent("Use Plan Again to create a new plan");
  });

  it("shows permission denied on a 403 from approve", async () => {
    server.use(http.post(approveUrl, () => apiError(403, "FORBIDDEN", "Your role cannot access this resource.")));
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(approveButton(1));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));

    expect(await screen.findByText("Permission denied")).toBeInTheDocument();
    expect(screen.getByText("Your role is not allowed to approve this plan.")).toBeInTheDocument();
  });

  it("does NOT report success when the backend answers 200 without order.status APPROVED", async () => {
    server.use(
      http.post(approveUrl, () =>
        HttpResponse.json({ order: { status: "PLANNED" }, plan: { id: 4121, status: "proposed" }, trip_ids: [], notifications: [] }),
      ),
    );
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();

    await user.click(approveButton(1));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));

    expect(await screen.findByText("Approval not confirmed")).toBeInTheDocument();
    expect(screen.queryByText(/Approved · order status/)).not.toBeInTheDocument();
    expect(screen.queryByText("Plan approved.")).not.toBeInTheDocument();
    expect(approveButton(1)).toBeEnabled();
  });

  it("lets the dispatcher approve only once: a second attempt from the server gives PLAN_NOT_APPROVABLE", async () => {
    await openPlan(MOCK_RUN_IDS.normal);
    const user = userEvent.setup();
    await user.click(approveButton(1));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve #1" }));
    await screen.findByText(/Approved · order status APPROVED/);

    const second = await fetch(`${API_BASE_URL}/plans/4122/approve`, {
      method: "POST",
      headers: { Authorization: `Bearer ${MOCK_TOKEN_PREFIX}1`, "Content-Type": "application/json", "Idempotency-Key": "second-attempt-key" },
      body: JSON.stringify({ reason_code: "other", reason_text: "again" }),
    });
    expect(second.status).toBe(409);
    expect((await second.json()).error.code).toBe("PLAN_NOT_APPROVABLE");
  });
});
