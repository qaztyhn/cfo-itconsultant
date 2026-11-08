import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DEMO_WAREHOUSE_MODEL } from "../fixtures";
import { WarehouseShiftPanel } from "./WarehouseShiftPanel";

describe("WarehouseShiftPanel", () => {
  it("renders the title, data-as-of, panel warning, timeline and backend note when ready", () => {
    render(<WarehouseShiftPanel state={{ status: "ready", data: DEMO_WAREHOUSE_MODEL }} />);

    expect(screen.getByRole("heading", { level: 2, name: "Warehouse staff shifts" })).toBeInTheDocument();
    expect(screen.getByText("Data as of 10:05")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Scheduling warnings" })).toBeInTheDocument();
    expect(screen.getByText("SCHEDULE_PARTIAL")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Shift timeline" })).toBeInTheDocument();
    expect(screen.getByText("Final scheduling decisions are validated by the backend.")).toBeInTheDocument();
  });

  it("does not show staffing suggestions or expected-staff comparisons", () => {
    render(<WarehouseShiftPanel state={{ status: "ready", data: DEMO_WAREHOUSE_MODEL }} />);

    expect(screen.queryByText(/expected/i)).toBeNull();
    expect(screen.queryByText(/suggest/i)).toBeNull();
  });

  it("shows a busy status while loading", () => {
    render(<WarehouseShiftPanel state={{ status: "loading" }} />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  });

  it("shows an error with correlation id and a working Retry", async () => {
    const onRetry = vi.fn();
    render(
      <WarehouseShiftPanel
        state={{ status: "error", error: { message: "Load failed", correlationId: "corr-wh-1" }, onRetry }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Load failed");
    expect(screen.getByText("corr-wh-1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows unavailable as a status, not an error", () => {
    render(<WarehouseShiftPanel state={{ status: "unavailable" }} />);

    expect(screen.getByRole("status")).toHaveTextContent("Shift data is not available yet");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the empty message for an empty state and for a ready state with no rows", () => {
    const { unmount } = render(<WarehouseShiftPanel state={{ status: "empty" }} />);
    expect(screen.getByText("No shifts to show for this period")).toBeInTheDocument();
    unmount();

    render(
      <WarehouseShiftPanel state={{ status: "ready", data: { ...DEMO_WAREHOUSE_MODEL, rows: [] } }} />,
    );
    expect(screen.getByText("No shifts to show for this period")).toBeInTheDocument();
  });

  it("produces no hex colours, cost wording or location data in its output", () => {
    const { container } = render(<WarehouseShiftPanel state={{ status: "ready", data: DEMO_WAREHOUSE_MODEL }} />);

    expect(container.innerHTML).not.toMatch(/#[0-9a-f]{6}\b/i);
    expect(container.innerHTML).not.toMatch(/rgb\(/i);
    expect(container.textContent).not.toMatch(/\bSEK\b|\bcost\b|\bgps\b|latitude|longitude/i);
  });
});