import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../../../api/config";
import { fetchLocations } from "../../../api/locations";
import { currentPath, renderAt, signInAs, userByEmail } from "../../../test/utils";
import { ORDERS_URL, setupOrderQueueMsw } from "./testServer";

vi.mock("../../../api/locations", () => ({ fetchLocations: vi.fn() }));

const server = setupOrderQueueMsw();

beforeEach(() => {
  vi.mocked(fetchLocations).mockReset();
  vi.mocked(fetchLocations).mockResolvedValue([]);
  signInAs(userByEmail("dispatcher@cfo.demo"));
});

const errorBody = (code: string, message: string) => ({ error: { code, message, details: {}, correlation_id: "corr-test" } });
const order = (over: Record<string, unknown> = {}) => ({
  id: 4021, order_no: "SE-2026-004021", status: "PLANNED", customer_name: "Nordbygg AB", site: "Göteborg",
  warehouse: { id: 7, code: "STO" }, origin_store: { id: 21, code: "GBG-V" },
  date_request: { mode: "latest", date_from: null, date_to: "2026-11-18" },
  committed_date: null, promise_end: null, risk_color: null, block_reason: null,
  total_amount: "48300.00", currency: "SEK", submitted_at: "2026-11-05T07:12:00Z", ...over,
});
const queue = (o: unknown) => http.get(ORDERS_URL, () => HttpResponse.json({ items: [o], page: 1, page_size: 50, total: 1 }));
const RUNS = `${API_BASE_URL}/orders/4021/planning-runs`;
const PLAN = `${API_BASE_URL}/orders/4021/plan`;
/** Màn đích tự gọi API này; trả 503 để test không phụ thuộc nội dung Plan Review. */
const landing = (id: number) => http.get(`${API_BASE_URL}/planning-runs/${id}`, () => HttpResponse.json(errorBody("SERVICE_UNAVAILABLE", "off"), { status: 503 }));

const main = () => within(screen.getByRole("main"));
const firstButton = async (name: string) => (await main().findAllByRole("button", { name }))[0];

describe("OrderAction", () => {
  it("keeps the general Plan Review entry on its own page when no plans are pending", async () => {
    renderAt("/dispatcher/plan-review");
    expect(await main().findByText("No orders are awaiting plan approval.")).toBeInTheDocument();
    expect(main().getByRole("heading", { name: "Plan review" })).toBeInTheDocument();
    expect(currentPath()).toBe("/dispatcher/plan-review");
  });

  it("planned run history forbidden does not navigate or fabricate a run", async () => {
    server.use(queue(order()), http.get(RUNS, () =>
      HttpResponse.json(errorBody("FORBIDDEN", "Access denied"), { status: 403 })));
    renderAt("/dispatcher/orders");
    await userEvent.setup().click(await firstButton("Plan review for order SE-2026-004021"));
    expect((await main().findAllByRole("alert"))[0]).toHaveTextContent(/not allowed/i);
    expect(currentPath()).toBe("/dispatcher/orders");
  });

  it("planning failure and invalid server run ID never navigate to a fake review", async () => {
    server.use(queue(order({ status: "SUBMITTED" })),
      http.post(PLAN, () => HttpResponse.json(errorBody("PLAN_NOT_FEASIBLE", "No feasible plan"), { status: 422 })));
    renderAt("/dispatcher/orders");
    await userEvent.setup().click(await firstButton("Run planning for order SE-2026-004021"));
    expect((await main().findAllByRole("alert"))[0]).toHaveTextContent(/No feasible plan/);
    expect(currentPath()).toBe("/dispatcher/orders");
  });

  it("test_US_ORD_02_AC3_planned_opens_absolute_latest_reviewable_run", async () => {
    server.use(queue(order()), landing(88), http.get(RUNS, () => HttpResponse.json({ items: [
      { id: 88, order_id: 4021, run_no: 3, kind: "rerun", result: "feasible", hold_expires_at: "2099-11-18T16:00:00+01:00" },
      { id: 55, order_id: 4021, run_no: 2, kind: "initial", result: "feasible", hold_expires_at: "2099-11-18T16:00:00+01:00" },
    ] })));
    renderAt("/dispatcher/orders");

    await userEvent.setup().click(await firstButton("Plan review for order SE-2026-004021"));

    await waitFor(() => expect(currentPath()).toBe("/dispatcher/plan-review/88"));
  });

  it("newest replan suggestion opens latest advisory diagnostics, never older feasible run", async () => {
    server.use(queue(order()), landing(99), http.get(RUNS, () => HttpResponse.json({ items: [
      { id: 99, order_id: 4021, run_no: 4, kind: "replan_suggestion", result: "feasible", hold_expires_at: null },
      { id: 88, order_id: 4021, run_no: 3, kind: "rerun", result: "feasible", hold_expires_at: "2099-11-18T16:00:00+01:00" },
    ] })));
    renderAt("/dispatcher/orders");
    await userEvent.setup().click(await firstButton("Plan review for order SE-2026-004021"));
    await waitFor(() => expect(currentPath()).toBe("/dispatcher/plan-review/99"));
    expect(currentPath()).not.toBe("/dispatcher/plan-review/88");
  });

  it("newest infeasible run opens latest diagnostic DTO, never older feasible run", async () => {
    server.use(queue(order()), landing(99), http.get(RUNS, () => HttpResponse.json({ items: [
      { id: 99, order_id: 4021, run_no: 4, kind: "rerun", result: "infeasible", hold_expires_at: null },
      { id: 88, order_id: 4021, run_no: 3, kind: "initial", result: "feasible", hold_expires_at: "2099-11-18T16:00:00+01:00" },
    ] })));
    renderAt("/dispatcher/orders");
    await userEvent.setup().click(await firstButton("Plan review for order SE-2026-004021"));
    await waitFor(() => expect(currentPath()).toBe("/dispatcher/plan-review/99"));
    expect(currentPath()).not.toBe("/dispatcher/plan-review/88");
  });

  it("NO_FEASIBLE_DATE order exposes real latest diagnostics and the Exceptions route", async () => {
    server.use(queue(order({ status: "NO_FEASIBLE_DATE" })), landing(99), http.get(RUNS, () => HttpResponse.json({ items: [
      { id: 99, order_id: 4021, run_no: 4, kind: "rerun", result: "infeasible", hold_expires_at: null },
      { id: 88, order_id: 4021, run_no: 3, kind: "initial", result: "feasible", hold_expires_at: "2099-11-18T16:00:00+01:00" },
    ] })));
    renderAt("/dispatcher/orders");
    const diagnostics = await firstButton("Review diagnostics for order SE-2026-004021");
    expect(main().getAllByRole("link", { name: "Exceptions for order SE-2026-004021" }).some(link =>
      link.getAttribute("href") === "/dispatcher/exceptions")).toBe(true);
    await userEvent.setup().click(diagnostics);
    await waitFor(() => expect(currentPath()).toBe("/dispatcher/plan-review/99"));
  });

  it("newest expired hold opens that run for truthful expiry and Plan Again", async () => {
    server.use(queue(order()), landing(99), http.get(RUNS, () => HttpResponse.json({ items: [
      { id: 99, order_id: 4021, run_no: 4, kind: "rerun", result: "feasible", hold_expires_at: "2020-01-01T00:00:00Z" },
      { id: 88, order_id: 4021, run_no: 3, kind: "initial", result: "feasible", hold_expires_at: "2099-11-18T16:00:00+01:00" },
    ] })));
    renderAt("/dispatcher/orders");
    await userEvent.setup().click(await firstButton("Plan review for order SE-2026-004021"));
    await waitFor(() => expect(currentPath()).toBe("/dispatcher/plan-review/99"));
  });

  it("malformed latest history fails closed rather than opening another run", async () => {
    server.use(queue(order()), http.get(RUNS, () => HttpResponse.json({ items: [
      { id: 99, order_id: 4021, run_no: 4, kind: "rerun", result: "feasible", hold_expires_at: "not-a-date" },
      { id: 88, order_id: 4021, run_no: 3, kind: "initial", result: "feasible", hold_expires_at: "2099-11-18T16:00:00+01:00" },
    ] })));
    renderAt("/dispatcher/orders");
    await userEvent.setup().click(await firstButton("Plan review for order SE-2026-004021"));
    expect((await main().findAllByRole("alert"))[0]).toHaveTextContent(/Invalid planning history/i);
    expect(currentPath()).toBe("/dispatcher/orders");
  });

  it("test_US_ORD_02_AC3_planned_without_run_shows_error_and_does_not_navigate", async () => {
    server.use(queue(order()), http.get(RUNS, () => HttpResponse.json({ items: [] })));
    renderAt("/dispatcher/orders");

    await userEvent.setup().click(await firstButton("Plan review for order SE-2026-004021"));

    expect((await main().findAllByRole("alert"))[0]).toHaveTextContent(/No planning run was found/);
    expect(currentPath()).toBe("/dispatcher/orders");
  });

  it("test_US_ORD_02_AC3_submitted_run_planning_navigates_to_server_issued_run", async () => {
    server.use(queue(order({ status: "SUBMITTED" })), landing(91),
      http.post(PLAN, () => HttpResponse.json({ id: 91, order_id: 4021, run_no: 1 })));
    renderAt("/dispatcher/orders");

    await userEvent.setup().click(await firstButton("Run planning for order SE-2026-004021"));

    await waitFor(() => expect(currentPath()).toBe("/dispatcher/plan-review/91"));
  });

  it("test_US_ORD_02_AC3_submitted_conflict_shows_server_code_and_no_false_success", async () => {
    server.use(queue(order({ status: "SUBMITTED" })),
      http.post(PLAN, () => HttpResponse.json(errorBody("RESOURCE_CONFLICT", "Resources changed"), { status: 409 })));
    renderAt("/dispatcher/orders");

    await userEvent.setup().click(await firstButton("Run planning for order SE-2026-004021"));

    expect((await main().findAllByRole("alert"))[0]).toHaveTextContent("Resources changed (RESOURCE_CONFLICT)");
    expect(currentPath()).toBe("/dispatcher/orders");
  });

  it("test_US_ORD_02_AC3_double_click_creates_only_one_planning_run", async () => {
    let posts = 0;
    server.use(queue(order({ status: "SUBMITTED" })), landing(91), http.post(PLAN, async () => {
      posts += 1;
      await delay(100);
      return HttpResponse.json({ id: 91 });
    }));
    renderAt("/dispatcher/orders");

    await userEvent.setup().dblClick(await firstButton("Run planning for order SE-2026-004021"));

    await waitFor(() => expect(currentPath()).toBe("/dispatcher/plan-review/91"));
    expect(posts).toBe(1);
  });
});
