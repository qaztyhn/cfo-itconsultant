import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  atRisk,
  atRiskExplanation,
  eventLog,
  lateExplanation,
  milestones,
  missingForecast,
  multiVehicle,
  notifications,
  onTrackRisk,
  predictedLate,
  staleRisk,
} from "./fixtures";
import { formatInstant, timeText } from "./format";
import { RiskSummary } from "./RiskSummary";
import { MilestoneTimeline } from "./MilestoneTimeline";
import { VehicleStatusList } from "./VehicleStatusList";
import { RiskExplanation } from "./RiskExplanation";
import { OrderEventLog } from "./OrderEventLog";
import { NotificationHistory } from "./NotificationHistory";

describe("US-TRK-01 / M7: risk and forecast presentations", () => {
  it("renders on-track data from props with a labelled risk and committed window", () => {
    render(<RiskSummary model={onTrackRisk} />);
    const region = screen.getByRole("region", { name: "Delivery risk summary" });
    expect(within(region).getByRole("status", { name: "Risk: On track" })).toBeInTheDocument();
    expect(within(region).getByText("13%")).toBeInTheDocument();
    expect(within(region).getByText("Committed window")).toBeInTheDocument();
    expect(within(region).getByText("Europe/Stockholm")).toBeInTheDocument();
    expect(within(region).getByText("Verified ORS route", { exact: false })).toBeInTheDocument();
    expect(within(region).getByRole("img", { name: "Planning reserve consumed: 13 percent" }))
      .toBeInTheDocument();
  });

  it("distinguishes at-risk from predicted-late, without inferring status from time", () => {
    const { rerender } = render(<RiskSummary model={atRisk} />);
    expect(screen.getByRole("status", { name: "Risk: At risk" })).toBeInTheDocument();
    rerender(<RiskSummary model={predictedLate} />);
    expect(screen.getByRole("status", { name: "Risk: Predicted late" })).toBeInTheDocument();
    expect(screen.getByText("120%")).toBeInTheDocument();
    expect(screen.getByText(/Estimated fallback route — not verified ORS/)).toBeInTheDocument();
    expect(screen.queryByText("Verified ORS route", { exact: true })).not.toBeInTheDocument();
  });

  it("does not invent a forecast, reserve consumption or risk when missing", () => {
    render(<RiskSummary model={missingForecast} />);
    const region = screen.getByRole("region", { name: "Delivery risk summary" });
    expect(within(region).getByText("Not recorded")).toBeInTheDocument();
    expect(within(region).getAllByText("Unknown").length).toBeGreaterThan(0);
    expect(within(region).queryByText("0%")).not.toBeInTheDocument();
    expect(within(region).queryByRole("img", { name: /reserve consumed/ })).not.toBeInTheDocument();
    expect(within(region).queryByRole("status", { name: /On track/ })).not.toBeInTheDocument();
  });

  it("marks stale data stale, even when its upstream risk status was ON_TRACK", () => {
    render(<RiskSummary model={staleRisk} />);
    expect(screen.getByRole("status", { name: "Risk: On track (stale)" })).toBeInTheDocument();
    expect(screen.getAllByText("Stale").length).toBeGreaterThan(0);
  });

  it("retains upstream explanations, reason codes, and estimated fallback provenance", () => {
    const { rerender } = render(<RiskExplanation model={lateExplanation} />);
    expect(screen.getByText(/The supplied forecast is beyond/)).toBeInTheDocument();
    expect(screen.getByText("FORECAST_AFTER_PROMISE")).toBeInTheDocument();
    expect(screen.getByText(/Estimated fallback route — not verified ORS/)).toBeInTheDocument();
    rerender(<RiskExplanation model={atRiskExplanation} />);
    expect(screen.getByRole("status", { name: "Risk: At risk" })).toBeInTheDocument();
    expect(screen.queryByText("FORECAST_AFTER_PROMISE")).not.toBeInTheDocument();
  });

  it("does not turn missing upstream explanation into a fabricated reason", () => {
    render(<RiskExplanation model={{ risk: { status: null, quality: "unknown" }, explanation: null, reasonCodes: [], provenance: null }} />);
    expect(screen.getByText(/No rule-based explanation supplied/)).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: /Risk:/ })).not.toBeInTheDocument();
  });
});

describe("US-TRK-01 / M7: execution milestones and vehicles", () => {
  it("shows the six ordered milestones with separate planned, actual and forecast evidence", () => {
    render(<MilestoneTimeline model={milestones} />);
    const region = screen.getByRole("region", { name: /Milestones/ });
    const rows = within(region).getAllByRole("listitem");
    expect(rows).toHaveLength(6);
    expect(rows.map((item) => item.getAttribute("data-milestone"))).toEqual([
      "APPROVED", "START_PREP", "GOODS_READY", "LOADED", "DISPATCHED", "DELIVERED",
    ]);
    expect(within(region).getAllByText("Planned")).toHaveLength(6);
    expect(within(region).getAllByText("Actual")).toHaveLength(6);
    expect(within(region).getAllByText("Forecast")).toHaveLength(6);
    expect(within(rows[5]).getByText("Not recorded")).toBeInTheDocument();
  });

  it("discloses a missing milestone instead of pretending the step happened", () => {
    render(<MilestoneTimeline model={{ ...milestones, milestones: milestones.milestones.filter((m) => m.kind !== "GOODS_READY") }} />);
    const missingRow = screen.getByRole("listitem", { name: /Goods ready/ });
    expect(within(missingRow).getByText(/Milestone data missing/)).toBeInTheDocument();
  });

  it("supports multiple vehicles including FAILED and displays the supplied overall ETA unchanged", () => {
    const altered = {
      ...multiVehicle,
      overallForecastEta: { at: "2026-11-12T13:00:00Z", quality: "verified" as const },
    };
    render(<VehicleStatusList model={altered} />);
    expect(screen.getByRole("list", { name: "Vehicles assigned to this order" })
      .querySelectorAll("li")).toHaveLength(3);
    expect(screen.getByText("STO-12-04")).toBeInTheDocument();
    expect(screen.getByText("STO-18-01")).toBeInTheDocument();
    expect(screen.getByText("STO-CR-01")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/14:00/)).toBeInTheDocument();
    expect(screen.getByText(/Estimated fallback route — not verified ORS/)).toBeInTheDocument();
  });

  it("does not expose a stale vehicle state as a verified status", () => {
    render(<VehicleStatusList model={{
      ...multiVehicle,
      vehicles: [{ ...multiVehicle.vehicles[0], stateQuality: "stale" }],
    }} />);
    expect(screen.getByText("Delivered")).toBeInTheDocument();
    expect(screen.getByText("Stale")).toBeInTheDocument();
  });
});

describe("US-TRK-01 / M7: event and notification read models", () => {
  it("shows event time, event type, actor role and supplied effect", () => {
    render(<OrderEventLog model={eventLog} />);
    const table = screen.getByRole("table", { name: /Time, event/ });
    expect(within(table).getByRole("columnheader", { name: "Time" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "By" })).toBeInTheDocument();
    expect(within(table).getByText("PLAN_APPROVED")).toBeInTheDocument();
    expect(within(table).getByText("Dispatcher")).toBeInTheDocument();
    expect(within(table).getByText("Dispatcher alert recorded")).toBeInTheDocument();
  });

  it("shows notification type, channel, status and time without sending/editing controls", () => {
    render(<NotificationHistory model={notifications} />);
    expect(screen.getByText(/CONFIRMED/)).toBeInTheDocument();
    expect(screen.getByText(/sms_sim/)).toBeInTheDocument();
    expect(screen.getByText("draft")).toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
  });

  it("does not display extra GPS, driver, recipient or message-body fields accidentally", () => {
    const vehicleWithPrivateExtra = {
      ...multiVehicle,
      vehicles: multiVehicle.vehicles.map((v) => ({
        ...v,
        driverName: "PRIVATE DRIVER",
        lat: 59.9,
        lon: 17.8,
      })),
    };
    const notificationsWithPrivateExtra = {
      ...notifications,
      notifications: notifications.notifications.map((n) => ({
        ...n,
        messageBody: "PRIVATE CUSTOMER MESSAGE",
        recipientEmail: "secret@example.test",
      })),
    };
    const eventsWithPrivateExtra = {
      ...eventLog,
      events: eventLog.events.map((e) => ({
        ...e,
        actorName: "PRIVATE EMPLOYEE",
        gps: [59.9, 17.8],
      })),
    };
    const { container } = render(
      <>
        <VehicleStatusList model={vehicleWithPrivateExtra} />
        <NotificationHistory model={notificationsWithPrivateExtra} />
        <OrderEventLog model={eventsWithPrivateExtra} />
      </>,
    );
    for (const sensitive of [
      "PRIVATE DRIVER", "59.9", "17.8", "PRIVATE CUSTOMER MESSAGE",
      "secret@example.test", "PRIVATE EMPLOYEE",
    ]) {
      expect(container.textContent).not.toContain(sensitive);
    }
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});

describe("US-TRK-01 / M7: states and accessibility", () => {
  const views = [
    ["Delivery risk summary", <RiskSummary key="risk" model={null} />],
    ["Milestones · planned vs actual vs forecast", <MilestoneTimeline key="milestones" model={null} />],
    ["Vehicle execution status", <VehicleStatusList key="vehicles" model={null} />],
    ["Risk explanation", <RiskExplanation key="explanation" model={null} />],
    ["Order event log", <OrderEventLog key="events" model={null} />],
    ["Customer notification history", <NotificationHistory key="notifications" model={null} />],
  ] as const;

  it.each(views)("%s has an explicit accessible empty state", (title, view) => {
    render(view);
    const region = screen.getByRole("region", { name: title });
    expect(within(region).getByRole("status")).toBeInTheDocument();
  });

  it("represents loading, errors and correlation identifiers without showing sensitive error bodies", () => {
    const { rerender } = render(<RiskSummary model={null} loadState="loading" />);
    expect(screen.getByRole("status", { name: /Loading Delivery risk summary/ })).toHaveAttribute("aria-busy", "true");
    rerender(<RiskSummary model={null} loadState="error" errorReference="safe-correlation-123" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load delivery risk summary.");
    expect(screen.getByRole("alert")).toHaveTextContent("safe-correlation-123");
    expect(screen.queryByRole("status", { name: /On track/ })).not.toBeInTheDocument();
  });

  it("does not turn absent, unavailable or malformed time data into an ETA", () => {
    expect(formatInstant("2026-11-12T09:00:00", "Europe/Stockholm")).toBe("Unverified timestamp");
    expect(formatInstant("not-an-instant", "Europe/Stockholm")).toBe("Unverified timestamp");
    expect(formatInstant("2026-11-12T09:00:00Z", "Invalid/Zone")).toBe("Unknown time zone");
    expect(timeText({ at: null, quality: "unavailable" }, "Europe/Stockholm")).toBe("Unavailable");
    expect(timeText({ at: null, quality: "missing" }, "Europe/Stockholm")).toBe("Not recorded");
    expect(timeText({ at: null, quality: "unknown" }, "Europe/Stockholm")).toBe("Unknown");
  });
});
