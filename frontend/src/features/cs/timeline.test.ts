import { describe, expect, it } from "vitest";
import { CS_TIMELINE_KINDS, projectCsTimeline } from "./timeline";

const T = "2026-11-05T07:12:00Z";

const payload = {
  items: [
    { at: T, kind: "order_submitted", title: "Order submitted", detail: {}, actor: null },
    { at: T, kind: "planning_run", title: "Plan run", detail: { kind: "initial", result: "secret plan" }, actor: { name: "Dispatcher X" } },
    { at: T, kind: "decision", title: "Approved", detail: { reason_text: "secret reason" }, actor: { name: "Dispatcher X" } },
    { at: T, kind: "milestone", title: "Departed", detail: { type: "departed", lat: 59.33, lon: 18.06, vehicle: "MLM-12-02" }, actor: null },
    {
      at: T,
      kind: "notification",
      title: "Email",
      detail: { template: "CONFIRMED", channel: "email", status: "sent", recipient: "anna.raw@example.com" },
      actor: null,
    },
    {
      at: T,
      kind: "eta",
      title: "ETA v2",
      detail: { version: 2, forecast_eta: "2026-11-13T08:40:00Z", risk_status: "AT_RISK", risk_color: "orange", slack_min: 4 },
      actor: null,
    },
    { at: T, kind: "gps_ping", title: "Ping", detail: { lat: 59.33, lon: 18.06 }, actor: null },
  ],
};

describe("CS timeline allowlist", () => {
  it("test_US_CS_01_AC1_timeline_keeps_only_allowed_kinds_and_fields", () => {
    const out = projectCsTimeline(payload);
    expect(out).toEqual([
      { kind: "order_submitted", at: T },
      { kind: "milestone", at: T, milestoneType: "departed" },
      { kind: "notification", at: T, template: "CONFIRMED", channel: "email", status: "sent" },
      { kind: "eta", at: T, forecastEta: "2026-11-13T08:40:00Z", riskStatus: "AT_RISK" },
    ]);
    expect(out.map((i) => i.kind).every((k) => (CS_TIMELINE_KINDS as readonly string[]).includes(k))).toBe(true);
    const json = JSON.stringify(out);
    for (const value of ["secret plan", "secret reason", "Dispatcher X", "59.33", "18.06", "MLM-12-02", "anna.raw", "slack_min", "orange"]) {
      expect(json).not.toContain(value);
    }
  });

  it("test_US_CS_01_AC1_timeline_drops_free_text_codes_and_invalid_rows", () => {
    const out = projectCsTimeline({
      items: [
        { at: T, kind: "milestone", detail: { type: "left depot at 59.33,18.06" } },
        { at: "not-a-date", kind: "order_submitted" },
        { kind: "order_submitted" },
        "garbage",
        null,
      ],
    });
    expect(out).toEqual([{ kind: "milestone", at: T, milestoneType: null }]);
  });

  it("test_US_CS_01_AC1_timeline_non_list_payload_returns_empty", () => {
    expect(projectCsTimeline(null)).toEqual([]);
    expect(projectCsTimeline({ items: "x" })).toEqual([]);
    expect(projectCsTimeline(undefined)).toEqual([]);
  });
});