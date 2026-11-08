import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DEMO_DRIVER_MODEL } from "../fixtures";
import { DriverAvailabilityPanel } from "./DriverAvailabilityPanel";

function getDriver(container: HTMLElement, id: string): HTMLElement {
  const el = container.querySelector<HTMLElement>(`[data-driver-id="${id}"]`);
  if (!el) throw new Error(`Driver ${id} not rendered`);
  return el;
}

describe("DriverAvailabilityPanel", () => {
  it("renders title, timeline, eligibility section and backend note when ready", () => {
    render(<DriverAvailabilityPanel state={{ status: "ready", data: DEMO_DRIVER_MODEL }} />);

    expect(screen.getByRole("heading", { level: 2, name: "Driver shifts and availability" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Shift timeline" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Driver eligibility" })).toBeInTheDocument();
    expect(screen.getByText("Final scheduling decisions are validated by the backend.")).toBeInTheDocument();
  });

  it("shows duty time and driving time separately, exactly as supplied (D06)", () => {
    const { container } = render(<DriverAvailabilityPanel state={{ status: "ready", data: DEMO_DRIVER_MODEL }} />);
    const d06 = getDriver(container, "dr-d06");

    expect(within(d06).getByText("Duty time")).toBeInTheDocument();
    expect(within(d06).getByText("6 h")).toBeInTheDocument();
    expect(within(d06).getByText("Driving time")).toBeInTheDocument();
    expect(within(d06).getByText("4 h 30 min")).toBeInTheDocument();
  });

  it("shows insufficient rest as Not eligible with its reason (D02)", () => {
    const { container } = render(<DriverAvailabilityPanel state={{ status: "ready", data: DEMO_DRIVER_MODEL }} />);
    const d02 = getDriver(container, "dr-d02");

    expect(within(d02).getByText("Not eligible")).toBeInTheDocument();
    expect(within(d02).getByText("DRIVER_REST_INSUFFICIENT · DEC-DRIVER-001")).toBeInTheDocument();
  });

  it("shows missing history and unknown vehicle scope as Unknown, never as eligible (D03, D04)", () => {
    const { container } = render(<DriverAvailabilityPanel state={{ status: "ready", data: DEMO_DRIVER_MODEL }} />);
    const d03 = getDriver(container, "dr-d03");
    const d04 = getDriver(container, "dr-d04");

    expect(within(d03).getByText("DRIVER_HISTORY_MISSING · DEC-DEV2-D7-001")).toBeInTheDocument();
    expect(within(d03).queryByText("Eligible")).toBeNull();
    expect(within(d04).getByText("VEHICLE_SCOPE_UNKNOWN · DEC-DEV2-D7-001")).toBeInTheDocument();
    expect(within(d04).queryByText("Eligible")).toBeNull();
    expect(d04.querySelector('[data-kind="vehicle_scope"]')).toHaveAttribute("data-status", "unknown");
  });

  it("lists no eligibility block for a driver without a verified schedule (D05)", () => {
    const { container } = render(<DriverAvailabilityPanel state={{ status: "ready", data: DEMO_DRIVER_MODEL }} />);

    expect(container.querySelector('[data-driver-id="dr-d05"]')).toBeNull();
    expect(screen.getByText("Schedule not verified")).toBeInTheDocument();
  });

  it("shows a busy status while loading", () => {
    render(<DriverAvailabilityPanel state={{ status: "loading" }} />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  });

  it("shows an error with correlation id and a working Retry", async () => {
    const onRetry = vi.fn();
    render(
      <DriverAvailabilityPanel
        state={{ status: "error", error: { message: "Load failed", correlationId: "corr-dr-1" }, onRetry }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Load failed");
    expect(screen.getByText("corr-dr-1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows unavailable as a status, not an error", () => {
    render(<DriverAvailabilityPanel state={{ status: "unavailable" }} />);

    expect(screen.getByRole("status")).toHaveTextContent("Shift data is not available yet");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the empty message when there are no rows", () => {
    render(<DriverAvailabilityPanel state={{ status: "ready", data: { ...DEMO_DRIVER_MODEL, rows: [] } }} />);

    expect(screen.getByText("No shifts to show for this period")).toBeInTheDocument();
  });

  it("produces no hex colours, cost wording or location data in its output", () => {
    const { container } = render(<DriverAvailabilityPanel state={{ status: "ready", data: DEMO_DRIVER_MODEL }} />);

    expect(container.innerHTML).not.toMatch(/#[0-9a-f]{6}\b/i);
    expect(container.innerHTML).not.toMatch(/rgb\(/i);
    expect(container.textContent).not.toMatch(/\bSEK\b|\bcost\b|\bgps\b|latitude|longitude/i);
  });
});