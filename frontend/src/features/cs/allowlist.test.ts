import { afterEach, describe, expect, it, vi } from "vitest";
import {
  isServerMaskedEmail,
  isServerMaskedPhone,
  projectCsEtaForecasts,
  projectCsNotifications,
  projectCsOrderDetail,
  projectCsOrderPage,
} from "./allowlist";

const RAW_PHONE = "+46 70 123 12 34";
const RAW_EMAIL = "anna.raw@example.com";

const overReturnedDetail = {
  id: 42,
  order_no: "ORD-0042",
  external_ref: "POS-9001",
  status: "APPROVED",
  version: 3,
  submitted_at: "2026-11-05T07:12:00Z",
  customer: { name: "Anna Svensson" },
  contact: {
    name: "Anna Svensson",
    phone: RAW_PHONE,
    phone_masked: "+46 •• ••• 12 34",
    email: RAW_EMAIL,
    email_masked: "a•••@example.com",
  },
  delivery: { address_line: "Storgatan 1", lat: 59.3293, lon: 18.0686, receiving_restrictions: "GATE-7731" },
  committed: { date: "2026-11-13", promise_start: "2026-11-13T07:00:00Z", promise_end: "2026-11-13T09:00:00Z" },
  risk: {
    status: "AT_RISK",
    color: "orange",
    forecast_eta: "2026-11-13T08:40:00Z",
    planned_eta: "2026-11-13T08:00:00Z",
    slack_min: 4,
    consumption_pct: 91,
  },
  approved_plan_id: 7,
  latest_run_id: 9,
  lines: [{ handling_group: "HG-FRAGILE", flags: ["fragile"] }],
};

const FORBIDDEN_VALUES = [RAW_PHONE, RAW_EMAIL, "59.3293", "18.0686", "GATE-7731", "Storgatan", "HG-FRAGILE", "consumption_pct"];

afterEach(() => vi.restoreAllMocks());

describe("CS allowlist", () => {
  it("test_US_CS_01_AC1_detail_projection_keeps_only_allowed_fields", () => {
    const out = projectCsOrderDetail(overReturnedDetail);
    expect(out).toEqual({
      id: 42,
      orderNo: "ORD-0042",
      externalRef: "POS-9001",
      status: "APPROVED",
      submittedAt: "2026-11-05T07:12:00Z",
      customerName: "Anna Svensson",
      contact: { name: "Anna Svensson", phone: "+46 •• ••• 12 34", email: "a•••@example.com" },
      committed: { date: "2026-11-13", promiseStart: "2026-11-13T07:00:00Z", promiseEnd: "2026-11-13T09:00:00Z" },
      risk: { status: "AT_RISK", color: "orange", forecastEta: "2026-11-13T08:40:00Z" },
    });
    const json = JSON.stringify(out);
    for (const value of FORBIDDEN_VALUES) expect(json).not.toContain(value);
  });

  it("test_US_CS_01_AC1_raw_phone_email_in_masked_fields_are_dropped_without_logging_values", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const out = projectCsOrderDetail({
      ...overReturnedDetail,
      contact: { name: "Anna Svensson", phone_masked: RAW_PHONE, email_masked: RAW_EMAIL },
    });
    expect(out?.contact.phone).toBeNull();
    expect(out?.contact.email).toBeNull();
    expect(JSON.stringify(out)).not.toContain(RAW_PHONE);
    expect(JSON.stringify(out)).not.toContain(RAW_EMAIL);
    expect(warn).toHaveBeenCalledTimes(2);
    const logged = warn.mock.calls.flat().join(" ");
    expect(logged).toContain("contact.phone_masked");
    expect(logged).not.toContain("70 123");
    expect(logged).not.toContain("anna.raw");
  });

  it("test_US_CS_01_AC1_missing_contact_yields_null_without_violation", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const out = projectCsOrderDetail({ id: 1, order_no: "ORD-1" });
    expect(out?.contact).toEqual({ name: null, phone: null, email: null });
    expect(out?.risk).toBeNull();
    expect(warn).not.toHaveBeenCalled();
  });

  it("test_US_CS_01_AC1_invalid_detail_payload_returns_null", () => {
    expect(projectCsOrderDetail(null)).toBeNull();
    expect(projectCsOrderDetail("x")).toBeNull();
    expect(projectCsOrderDetail({ order_no: "ORD-1" })).toBeNull();
  });

  it("test_US_CS_01_AC1_list_projection_drops_extra_fields_and_invalid_rows", () => {
    const out = projectCsOrderPage({
      items: [
        {
          id: 1,
          order_no: "ORD-1",
          status: "APPROVED",
          customer_name: "Anna Svensson",
          committed_date: "2026-11-13",
          promise_end: null,
          risk_color: "green",
          phone: RAW_PHONE,
          total_amount: "1200.00",
          lat: 59.3293,
        },
        { id: "bad", order_no: "ORD-2" },
      ],
      page: 1,
      page_size: 50,
      total: 2,
    });
    expect(out).toEqual({
      items: [
        {
          id: 1,
          orderNo: "ORD-1",
          status: "APPROVED",
          customerName: "Anna Svensson",
          committedDate: "2026-11-13",
          promiseEnd: null,
          riskColor: "green",
        },
      ],
      page: 1,
      pageSize: 50,
      total: 2,
    });
    expect(JSON.stringify(out)).not.toContain(RAW_PHONE);
    expect(projectCsOrderPage({ nope: true })).toBeNull();
  });

  it("test_US_CS_02_notifications_keep_only_safe_fields", () => {
    const out = projectCsNotifications({
      items: [
        {
          id: 77,
          template: "CONFIRMED",
          channel: "email",
          status: "sent",
          sent_at: "2026-11-05T08:00:00Z",
          recipient: RAW_EMAIL,
          subject: "Your order",
          body_html: "<p>secret body</p>",
        },
      ],
    });
    expect(out).toEqual([{ id: 77, template: "CONFIRMED", channel: "email", status: "sent", at: "2026-11-05T08:00:00Z" }]);
    expect(JSON.stringify(out)).not.toContain("secret body");
    expect(JSON.stringify(out)).not.toContain(RAW_EMAIL);
  });

  it("test_US_CS_02_eta_forecasts_drop_internal_scores", () => {
    const out = projectCsEtaForecasts({
      items: [{ version: 2, forecast_eta: "2026-11-13T08:40:00Z", risk_status: "AT_RISK", slack_min: 4, consumption_pct: 91 }],
    });
    expect(out).toEqual([{ version: 2, forecastEta: "2026-11-13T08:40:00Z", riskStatus: "AT_RISK" }]);
  });

  it("test_US_CS_01_AC1_mask_validators", () => {
    expect(isServerMaskedPhone("+46 •• ••• 12 34")).toBe(true);
    expect(isServerMaskedPhone("•• ••• 12 34")).toBe(true);
    expect(isServerMaskedPhone(RAW_PHONE)).toBe(false);
    expect(isServerMaskedPhone("+46701231234")).toBe(false);
    expect(isServerMaskedPhone("+46 70 123 •• 34 abc")).toBe(false);
    expect(isServerMaskedPhone("+46 70 123 •• 34")).toBe(false);
    expect(isServerMaskedEmail("a•••@example.com")).toBe(true);
    expect(isServerMaskedEmail(RAW_EMAIL)).toBe(false);
    expect(isServerMaskedEmail("•••")).toBe(false);
    expect(isServerMaskedEmail("anna.raw@exa•ple.com")).toBe(false);
  });
});