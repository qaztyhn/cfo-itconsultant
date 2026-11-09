import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { fetchEtaForecasts, fetchNotifications, fetchTimeline } from "./api";
import { EtaForecasts } from "./EtaForecasts";
import { NotificationHistory } from "./NotificationHistory";
import { OrderTimeline } from "./OrderTimeline";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, fetchEtaForecasts: vi.fn(), fetchNotifications: vi.fn(), fetchTimeline: vi.fn() };
});

const eta = vi.mocked(fetchEtaForecasts);
const notifications = vi.mocked(fetchNotifications);
const timeline = vi.mocked(fetchTimeline);

function renderUi(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const stubError = () => new ApiError("UNKNOWN_ERROR", "HTTP 500", "cid-stub", undefined, 500);

beforeEach(() => vi.resetAllMocks());

describe("CS ETA history", () => {
  it("test_US_CS_01_AC2_eta_shows_versions_with_text_and_risk_chip", async () => {
    eta.mockResolvedValueOnce([{ version: 2, forecastEta: "2026-11-13T08:40:00Z", riskStatus: "AT_RISK" }]);
    renderUi(<EtaForecasts orderId={42} />);
    expect(await screen.findByText("Version 2")).toBeInTheDocument();
    expect(screen.getByText("ETA 2026-11-13 08:40 UTC")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Risk: At risk" })).toBeInTheDocument();
    expect(eta).toHaveBeenCalledWith(42, expect.any(AbortSignal));
  });

  it("test_US_CS_01_AC2_eta_loading_empty_and_unavailable_states", async () => {
    const user = userEvent.setup();
    eta.mockReturnValueOnce(new Promise(() => {}));
    const first = renderUi(<EtaForecasts orderId={1} />);
    expect(await screen.findByText("Loading…")).toBeInTheDocument();
    first.unmount();

    eta.mockRejectedValueOnce(stubError());
    eta.mockResolvedValueOnce([]);
    renderUi(<EtaForecasts orderId={2} />);
    expect(await screen.findByText("ETA history unavailable")).toBeInTheDocument();
    expect(screen.getByText("cid-stub")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No ETA forecasts yet.")).toBeInTheDocument();
  });

  it("test_US_CS_01_AC2_eta_forbidden_has_no_retry", async () => {
    eta.mockRejectedValueOnce(new ApiError("FORBIDDEN", "No", "cid-403", undefined, 403));
    renderUi(<EtaForecasts orderId={3} />);
    expect(await screen.findByText("You don't have permission to view this.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});

describe("CS notification history", () => {
  it("test_US_CS_01_AC2_notifications_show_safe_fields_only", async () => {
    notifications.mockResolvedValueOnce([
      { id: 77, template: "CONFIRMED", channel: "email", status: "sent", at: "2026-11-05T08:00:00Z" },
    ]);
    renderUi(<NotificationHistory orderId={42} />);
    expect(await screen.findByText("CONFIRMED")).toBeInTheDocument();
    expect(screen.getByText("email")).toBeInTheDocument();
    expect(screen.getByText("sent")).toBeInTheDocument();
    expect(screen.getByText("2026-11-05 08:00 UTC")).toBeInTheDocument();
  });

  it("test_US_CS_01_AC2_notifications_empty_and_unavailable_states", async () => {
    const user = userEvent.setup();
    notifications.mockRejectedValueOnce(stubError());
    notifications.mockResolvedValueOnce([]);
    renderUi(<NotificationHistory orderId={42} />);
    expect(await screen.findByText("Notification history unavailable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No notifications recorded for this order.")).toBeInTheDocument();
  });
});

describe("CS timeline", () => {
  it("test_US_CS_01_AC2_timeline_renders_the_four_allowed_kinds_with_ui_built_labels", async () => {
    timeline.mockResolvedValueOnce([
      { kind: "order_submitted", at: "2026-11-05T07:12:00Z" },
      { kind: "milestone", at: "2026-11-13T06:30:00Z", milestoneType: "departed" },
      { kind: "notification", at: "2026-11-13T06:31:00Z", template: "DISPATCHED", channel: "email", status: "sent" },
      { kind: "eta", at: "2026-11-13T06:40:00Z", forecastEta: "2026-11-13T08:40:00Z", riskStatus: "AT_RISK" },
    ]);
    renderUi(<OrderTimeline orderId={42} />);
    expect(await screen.findByText("Order submitted")).toBeInTheDocument();
    expect(screen.getByText("Milestone: departed")).toBeInTheDocument();
    expect(screen.getByText("Notification: DISPATCHED · email · sent")).toBeInTheDocument();
    expect(screen.getByText("ETA update: 2026-11-13 08:40 UTC")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Risk: At risk" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
  });

  it("test_US_CS_01_AC2_timeline_empty_and_unavailable_states", async () => {
    const user = userEvent.setup();
    timeline.mockRejectedValueOnce(stubError());
    timeline.mockResolvedValueOnce([]);
    renderUi(<OrderTimeline orderId={42} />);
    expect(await screen.findByText("Timeline unavailable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No timeline events to show.")).toBeInTheDocument();
  });
});