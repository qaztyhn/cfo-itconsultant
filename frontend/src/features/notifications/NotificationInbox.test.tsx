import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, delay } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../../api/config";
import { fetchLocations } from "../../api/locations";
import { renderAt, signInAs, userByEmail } from "../../test/utils";
import { setupOrderQueueMsw } from "../dispatcher/orderQueue/testServer";

const NOTICES_URL = `${API_BASE_URL}/notifications`;
vi.mock("../../api/locations", () => ({ fetchLocations: vi.fn() }));
const START = "2026-11-10T09:00:00+01:00";
const END = "2026-11-10T11:00:00+01:00";
const summary = {
  id: 77, order_id: 42, order_no: "SE-2026-000042", template: "DELAY", status: "draft",
  recipient_masked: "s***@cfo.test", scheduled_for: "2026-11-09T08:00:00Z",
};
let status = "draft";
let version: number | null = 1;
let listCalls = 0;
let detailCalls = 0;
let sendCalls: { key: string | null; body: unknown }[] = [];
let discardBodies: unknown[] = [];

const server = setupOrderQueueMsw(
  http.get(NOTICES_URL, ({ request }) => {
    listCalls += 1;
    const params = new URL(request.url).searchParams;
    expect(params.get("template")).toBe("DELAY");
    expect(params.get("status")).toBe("draft");
    return HttpResponse.json({ items: status === "draft" ? [summary] : [], total: status === "draft" ? 1 : 0, page: 1, page_size: 50 });
  }),
  http.get(`${NOTICES_URL}/:id`, () => {
    detailCalls += 1;
    return HttpResponse.json({ ...summary, status, market_timezone: "Europe/Stockholm", subject: "Delivery update",
      body_text: "Order SE-2026-000042: Delivery timing has changed.", body_html: null,
      eta_window: { start: START, end: END, version }, suppressed_reason: null });
  }),
  http.post(`${NOTICES_URL}/:id/send`, async ({ request }) => {
    sendCalls.push({ key: request.headers.get("Idempotency-Key"), body: await request.json() });
    status = "queued";
    return HttpResponse.json({ id: 77, status });
  }),
  http.post(`${NOTICES_URL}/:id/discard`, async ({ request }) => {
    discardBodies.push(await request.json());
    status = "suppressed";
    return HttpResponse.json({ id: 77, status });
  }),
);

beforeEach(() => {
  vi.mocked(fetchLocations).mockReset();
  vi.mocked(fetchLocations).mockResolvedValue([]);
  status = "draft";
  version = 1;
  listCalls = 0;
  detailCalls = 0;
  sendCalls = [];
  discardBodies = [];
  signInAs(userByEmail("dispatcher@cfo.demo"));
});

describe("US-NOT-02 dispatcher DELAY inbox", () => {
  it("test_US_NOT_02_AC2_opens_masked_server_preview_without_sending", async () => {
    renderAt("/notifications?order_id=42");
    expect(await screen.findByText("Saved preview window:", { exact: false })).toBeInTheDocument();
    expect(screen.getAllByText("SE-2026-000042").length).toBeGreaterThan(0);
    expect(screen.getByText(/To: s\*\*\*@cfo\.test/)).toBeInTheDocument();
    expect(screen.getByText(/Times in Europe\/Stockholm/)).toBeInTheDocument();
    expect(screen.getByText(/Order SE-2026-000042: Delivery timing has changed/)).toBeInTheDocument();
    expect(sendCalls).toHaveLength(0);
    expect(discardBodies).toHaveLength(0);
    expect(listCalls).toBeGreaterThan(0);
    expect(detailCalls).toBeGreaterThan(0);
  });

  it("test_US_NOT_02_AC2_sends_edited_offset_aware_window_with_new_version_once", async () => {
    renderAt("/notifications");
    const user = userEvent.setup();
    const end = await screen.findByRole("textbox", { name: /Proposed end/ });
    await user.clear(end);
    await user.type(end, "2026-11-10T12:00:00+01:00");
    expect(screen.getByText(/Proposed window:/)).toBeInTheDocument();
    expect(sendCalls).toHaveLength(0);
    await user.dblClick(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(sendCalls).toHaveLength(1));
    expect(sendCalls[0].key).toMatch(/^[0-9a-f-]{36}$/i);
    expect(sendCalls[0].body).toEqual({
      eta_window: { start: START, end: "2026-11-10T12:00:00+01:00" },
      version: 2, reason_code: "PREDICTED_LATE",
    });
    expect(await screen.findByText(/Queued for delivery/)).toBeInTheDocument();
    expect(screen.queryByText("Sent to customer")).toBeNull();
  });

  it("test_US_NOT_02_AC2_blocks_reversed_window_and_unagreed_date", async () => {
    renderAt("/notifications");
    const user = userEvent.setup();
    const end = await screen.findByRole("textbox", { name: /Proposed end/ });
    await user.clear(end);
    await user.type(end, START);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await user.clear(end);
    await user.type(end, "2026-11-11T11:00:00+01:00");
    const start = screen.getByRole("textbox", { name: /Proposed start/ });
    await user.clear(start);
    await user.type(start, "2026-11-11T09:00:00+01:00");
    expect(screen.getByText(/recorded customer date agreement is required/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /Agreed date negotiation ID/ }), "19");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(sendCalls).toHaveLength(1));
    expect(sendCalls[0].body).toMatchObject({ version: 2, date_negotiation_id: 19 });
  });

  it("test_US_NOT_02_AC3_discard_requires_reason_and_refreshes_status", async () => {
    renderAt("/notifications");
    const user = userEvent.setup();
    const discard = await screen.findByRole("button", { name: "Discard" });
    expect(discard).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /Discard reason/ }), "Customer requested a call");
    await user.click(discard);
    await waitFor(() => expect(discardBodies).toEqual([{ reason_text: "Customer requested a call" }]));
    expect(await screen.findByText(/Server status: suppressed/)).toBeInTheDocument();
    expect(sendCalls).toHaveLength(0);
  });

  it("test_US_NOT_02_AC2_retries_uncertain_send_with_identical_key_and_payload", async () => {
    let first = true;
    server.use(http.post(`${NOTICES_URL}/:id/send`, async ({ request }) => {
      sendCalls.push({ key: request.headers.get("Idempotency-Key"), body: await request.json() });
      if (first) { first = false; return HttpResponse.error(); }
      status = "queued";
      return HttpResponse.json({ id: 77, status });
    }));
    renderAt("/notifications");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Send" }));
    expect(await screen.findByRole("button", { name: "Retry same request" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry same request" }));
    await waitFor(() => expect(sendCalls).toHaveLength(2));
    expect(sendCalls[1]).toEqual(sendCalls[0]);
    expect(await screen.findByText(/Queued for delivery/)).toBeInTheDocument();
  });

  it("test_US_NOT_02_AC2_conflict_reloads_and_missing_version_blocks_send", async () => {
    server.use(http.post(`${NOTICES_URL}/:id/send`, () => {
      version = 2;
      return HttpResponse.json({ error: { code: "ILLEGAL_TRANSITION", message: "Draft changed", correlation_id: "test-ref" } }, { status: 409 });
    }));
    renderAt("/notifications");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Send" }));
    expect(await screen.findByText(/draft changed. Review the refreshed version/)).toBeInTheDocument();
    await waitFor(() => expect(detailCalls).toBeGreaterThan(1));
    expect(sendCalls).toHaveLength(0);
    version = null;
    await user.click(screen.getByRole("button", { name: "Reload draft" }));
    expect(await screen.findByText(/Approved ETA version is missing/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("test_US_NOT_02_AC5_read_only_for_cs_and_admin", async () => {
    signInAs(userByEmail("cs@cfo.demo"));
    renderAt("/notifications");
    expect(await screen.findByText(/Saved preview window/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Discard" })).toBeNull();
  });

  it("test_US_NOT_02_AC2_empty_and_error_states_have_reload", async () => {
    status = "queued";
    renderAt("/notifications");
    expect(await screen.findByText(/No DELAY drafts/)).toBeInTheDocument();
    server.use(http.get(NOTICES_URL, async () => { await delay(10); return HttpResponse.json({ error: { code: "INTERNAL_ERROR", message: "Unavailable", correlation_id: "ref" } }, { status: 503 }); }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Reload" }));
    expect(await screen.findByText("Drafts unavailable")).toBeInTheDocument();
  });
});
