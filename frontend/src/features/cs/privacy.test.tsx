import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet, apiPost } from "../../api/client";
import { OrderLookup } from "./OrderLookup";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, apiGet: vi.fn(), apiPost: vi.fn() };
});

const get = vi.mocked(apiGet);
const post = vi.mocked(apiPost);
const fetchMock = vi.fn();

const RAW_PHONE = "+46 70 123 12 34";
const RAW_EMAIL = "anna.raw@example.com";

/** Mọi giá trị dưới đây là dữ liệu CS không được phép thấy; chúng không được xuất hiện trong DOM. */
const FORBIDDEN = [
  RAW_PHONE,
  "70 123 12 34",
  RAW_EMAIL,
  "59.3293",
  "18.0686",
  "GATE-7731",
  "Storgatan",
  "HG-FRAGILE",
  "913791",
  "424242",
  "777001",
  "888002",
  "secret plan",
  "secret reason",
  "Dispatcher X",
  "MLM-12-02",
  "SUBJ-SECRET",
  "BODY-SECRET",
  "TITLE-PLAN-RUN",
  "TITLE-DECISION",
  "TITLE-PING",
  "TITLE-MILESTONE",
  "TITLE-NOTIF",
];

let contact: Record<string, unknown>;

function route(path: string): unknown {
  switch (path) {
    case "/orders":
      return {
        items: [
          {
            id: 42,
            order_no: "ORD-0042",
            customer_name: "Anna Svensson",
            status: "APPROVED",
            risk_color: "orange",
            phone: RAW_PHONE,
            email: RAW_EMAIL,
            lat: 59.3293,
            handling_group: "HG-FRAGILE",
          },
        ],
        page: 1,
        page_size: 20,
        total: 1,
      };
    case "/orders/42":
      return {
        id: 42,
        order_no: "ORD-0042",
        external_ref: "POS-9001",
        status: "APPROVED",
        submitted_at: "2026-11-05T07:12:00Z",
        customer: { name: "Anna Svensson" },
        contact,
        delivery: { address_line: "Storgatan 1", lat: 59.3293, lon: 18.0686, receiving_restrictions: "GATE-7731" },
        committed: { date: "2026-11-13", promise_start: "2026-11-13T07:00:00Z", promise_end: "2026-11-13T09:00:00Z" },
        risk: { status: "AT_RISK", color: "orange", forecast_eta: "2026-11-13T08:40:00Z", consumption_pct: 913791, slack_min: 424242 },
        approved_plan_id: 777001,
        latest_run_id: 888002,
        lines: [{ handling_group: "HG-FRAGILE", flags: ["fragile"] }],
      };
    case "/orders/42/eta-forecasts":
      return {
        items: [
          { version: 2, forecast_eta: "2026-11-13T08:40:00Z", risk_status: "AT_RISK", slack_min: 424242, consumption_pct: 913791 },
        ],
      };
    case "/orders/42/notifications":
      return {
        items: [
          {
            id: 77,
            template: "CONFIRMED",
            channel: "email",
            status: "sent",
            sent_at: "2026-11-05T08:00:00Z",
            recipient: RAW_EMAIL,
            subject: "SUBJ-SECRET",
            body_html: "<p>BODY-SECRET</p>",
          },
        ],
      };
    case "/orders/42/timeline":
      return {
        items: [
          { at: "2026-11-05T07:12:00Z", kind: "order_submitted", title: "TITLE-NOTIF", detail: {}, actor: null },
          { at: "2026-11-05T07:20:00Z", kind: "planning_run", title: "TITLE-PLAN-RUN", detail: { result: "secret plan" }, actor: { name: "Dispatcher X" } },
          { at: "2026-11-05T07:30:00Z", kind: "decision", title: "TITLE-DECISION", detail: { reason_text: "secret reason" }, actor: { name: "Dispatcher X" } },
          {
            at: "2026-11-13T06:30:00Z",
            kind: "milestone",
            title: "TITLE-MILESTONE",
            detail: { type: "departed", lat: 59.3293, lon: 18.0686, vehicle: "MLM-12-02" },
            actor: null,
          },
          { at: "2026-11-13T06:35:00Z", kind: "gps_ping", title: "TITLE-PING", detail: { lat: 59.3293, lon: 18.0686 }, actor: null },
        ],
      };
    default:
      throw new Error(`Unexpected GET ${path}`);
  }
}

function renderLookup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderLookup />
    </QueryClientProvider>,
  );
}

async function openOrder(user: ReturnType<typeof userEvent.setup>) {
  renderLookup();
  await user.type(screen.getByLabelText("Search orders"), "ORD-0042");
  await user.click(screen.getByRole("button", { name: "Search" }));
  await user.click(await screen.findByRole("button", { name: /ORD-0042/ }));
  const region = screen.getByRole("region", { name: "Order details" });
  // Chờ cả ba khối phụ tải xong để kiểm tra DOM đầy đủ.
  await within(region).findByText("Version 2");
  await within(region).findByText("CONFIRMED");
  await within(region).findByText("Order submitted");
  return region;
}

beforeEach(() => {
  vi.resetAllMocks();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  get.mockImplementation(((path: string) => Promise.resolve(route(path))) as typeof apiGet);
  contact = {
    name: "Anna Svensson",
    phone: RAW_PHONE,
    phone_masked: "+46 •• ••• 12 34",
    email: RAW_EMAIL,
    email_masked: "a•••@example.com",
  };
});
afterEach(() => vi.unstubAllGlobals());

describe("CS privacy: server over-returns forbidden data", () => {
  it("test_US_CS_01_AC1_overreturned_payloads_never_reach_the_dom", async () => {
    const user = userEvent.setup();
    const region = await openOrder(user);
    const html = document.body.innerHTML;
    for (const value of FORBIDDEN) expect(html, `DOM must not contain ${value}`).not.toContain(value);

    // Dữ liệu được phép vẫn hiện.
    expect(within(region).getByText("+46 •• ••• 12 34")).toBeInTheDocument();
    expect(within(region).getByText("a•••@example.com")).toBeInTheDocument();
    expect(within(region).getByText("Milestone: departed")).toBeInTheDocument();
    expect(within(region).queryByText(/gps_ping|planning_run|decision/i)).toBeNull();
    // Timeline chỉ còn 2 mục được phép: order_submitted và milestone.
    expect(within(region).getByText("Milestone: departed").closest("li")).not.toBeNull();
    expect(within(region).queryByText(/Plan run|Approved|Ping/)).toBeNull();
  });

  it("test_US_CS_01_AC1_raw_values_in_masked_fields_become_contact_hidden_and_log_no_pii", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    contact = { name: "Anna Svensson", phone_masked: RAW_PHONE, email_masked: RAW_EMAIL };
    const user = userEvent.setup();
    const region = await openOrder(user);
    expect(within(region).getAllByText("Contact hidden")).toHaveLength(2);
    const html = document.body.innerHTML;
    for (const value of FORBIDDEN) expect(html).not.toContain(value);
    const logged = warn.mock.calls.flat().join(" ");
    expect(logged).toContain("contact.phone_masked");
    expect(logged).toContain("contact.email_masked");
    for (const value of [RAW_PHONE, "70 123 12 34", RAW_EMAIL, "anna.raw"]) expect(logged).not.toContain(value);
    warn.mockRestore();
  });

  it("test_US_CS_01_AC1_no_reveal_control_no_tel_or_mailto_links_and_no_write_requests", async () => {
    const user = userEvent.setup();
    await openOrder(user);
    expect(screen.queryByRole("button", { name: /reveal|unmask|show (phone|email|number|contact)/i })).toBeNull();
    expect(document.querySelector('a[href^="tel:"], a[href^="mailto:"]')).toBeNull();
    expect(post).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
    // Mọi request đều là GET tới đúng các endpoint dự kiến.
    const paths = get.mock.calls.map((call) => call[0]);
    expect(new Set(paths)).toEqual(
      new Set(["/orders", "/orders/42", "/orders/42/eta-forecasts", "/orders/42/notifications", "/orders/42/timeline"]),
    );
  });
});