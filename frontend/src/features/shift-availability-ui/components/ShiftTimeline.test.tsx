import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DEMO_DRIVER_MODEL, DEMO_WAREHOUSE_MODEL } from "../fixtures";
import { ShiftTimeline } from "./ShiftTimeline";

function getRow(container: HTMLElement, id: string): HTMLElement {
  const el = container.querySelector<HTMLElement>(`[data-row-id="${id}"]`);
  if (!el) throw new Error(`Row ${id} not rendered`);
  return el;
}

describe("ShiftTimeline (warehouse)", () => {
  it("renders a named region with one row per staff member", () => {
    const { container } = render(<ShiftTimeline model={DEMO_WAREHOUSE_MODEL} />);

    expect(screen.getByRole("region", { name: "Shift timeline" })).toBeInTheDocument();
    expect(container.querySelectorAll("[data-row-id]")).toHaveLength(DEMO_WAREHOUSE_MODEL.rows.length);
  });

  it("draws the official shift and the break with readable titles", () => {
    const { container } = render(<ShiftTimeline model={DEMO_WAREHOUSE_MODEL} />);
    const row = getRow(container, "wh-w02");

    expect(row.querySelector('[data-kind="shift"]')).toHaveAttribute("title", "Official shift: 06:00–14:00");
    expect(row.querySelector('[data-kind="break"]')).toHaveAttribute("title", "Break: 10:00–10:30");
    expect(within(row).getByText("Assigned")).toBeInTheDocument();
  });

  it("marks the part of a task outside the official shift with text, not only colour (W05)", () => {
    const { container } = render(<ShiftTimeline model={DEMO_WAREHOUSE_MODEL} />);
    const row = getRow(container, "wh-w05");

    expect(row.querySelector('[data-kind="outside-schedule"]')).toHaveAttribute(
      "title",
      "Outside official schedule: 14:00–15:30",
    );
    expect(row).toHaveTextContent("Outside official schedule: 14:00–15:30");
    expect(within(row).getByText("TASK_OUTSIDE_SHIFT")).toBeInTheDocument();
    expect(within(row).getByText("Warning")).toBeInTheDocument();
    expect(screen.getByText("Display hint only. The backend validates scheduling.")).toBeInTheDocument();
  });

  it("shows the display-hint note only when a task is actually outside a shift", () => {
    render(
      <ShiftTimeline
        model={{ ...DEMO_WAREHOUSE_MODEL, rows: DEMO_WAREHOUSE_MODEL.rows.filter((r) => r.id === "wh-w02") }}
      />,
    );

    expect(screen.queryByText("Display hint only. The backend validates scheduling.")).toBeNull();
  });

  it("shows 'Schedule not verified' for an unverified schedule (W06), not an empty lane", () => {
    const { container } = render(<ShiftTimeline model={DEMO_WAREHOUSE_MODEL} />);
    const row = getRow(container, "wh-w06");

    expect(row).toHaveAttribute("data-schedule", "unverified");
    expect(within(row).getByRole("note")).toHaveTextContent("Schedule not verified");
    expect(within(row).queryByText("No official shift in this window")).toBeNull();
  });

  it("distinguishes a verified schedule with no shift (W07) from an unverified one", () => {
    const { container } = render(<ShiftTimeline model={DEMO_WAREHOUSE_MODEL} />);
    const row = getRow(container, "wh-w07");

    expect(row).toHaveAttribute("data-schedule", "verified");
    expect(within(row).getByText("No official shift in this window")).toBeInTheDocument();
    expect(within(row).queryByText("Schedule not verified")).toBeNull();
  });

  it("keeps the drawn lane out of the accessibility tree (a text list carries the same facts)", () => {
    const { container } = render(<ShiftTimeline model={DEMO_WAREHOUSE_MODEL} />);
    const shiftBlock = getRow(container, "wh-w02").querySelector('[data-kind="shift"]');

    expect(shiftBlock?.closest('[aria-hidden="true"]')).not.toBeNull();
  });

  it("accepts label overrides", () => {
    const { container } = render(
      <ShiftTimeline model={DEMO_WAREHOUSE_MODEL} labels={{ officialShift: "Shift" }} />,
    );

    expect(getRow(container, "wh-w02").querySelector('[data-kind="shift"]')).toHaveAttribute(
      "title",
      "Shift: 06:00–14:00",
    );
  });
});

describe("ShiftTimeline (drivers)", () => {
  it("separates task phases (D01)", () => {
    const { container } = render(<ShiftTimeline model={DEMO_DRIVER_MODEL} />);
    const row = getRow(container, "dr-d01");

    expect(row.querySelector('[data-kind="task"][title^="Drive DEMO-0001"]')).toHaveAttribute(
      "title",
      "Drive DEMO-0001 · Driving · Assigned · 07:45–10:15",
    );
    expect(row).toHaveTextContent("Loading");
    expect(row).toHaveTextContent("Unloading");
    expect(row).toHaveTextContent("Return");
  });

  it("shows the blocking rest warning with its code and rule source (D02)", () => {
    const { container } = render(<ShiftTimeline model={DEMO_DRIVER_MODEL} />);
    const row = getRow(container, "dr-d02");

    expect(within(row).getByText("Blocking")).toBeInTheDocument();
    expect(within(row).getByText("DRIVER_REST_INSUFFICIENT")).toBeInTheDocument();
    expect(within(row).getByText("DEC-DRIVER-001")).toBeInTheDocument();
    expect(row.querySelector('[data-kind="rest"]')).toHaveAttribute("title", "Rest period: 04:00–14:00");
  });

  it("shows a missing-history warning as its own reason (D03)", () => {
    const { container } = render(<ShiftTimeline model={DEMO_DRIVER_MODEL} />);

    expect(within(getRow(container, "dr-d03")).getByText("DRIVER_HISTORY_MISSING")).toBeInTheDocument();
  });

  it("shows an unknown vehicle scope warning (D04)", () => {
    const { container } = render(<ShiftTimeline model={DEMO_DRIVER_MODEL} />);

    expect(within(getRow(container, "dr-d04")).getByText("VEHICLE_SCOPE_UNKNOWN")).toBeInTheDocument();
  });

  it("shows an unverified driver schedule as not verified (D05)", () => {
    const { container } = render(<ShiftTimeline model={DEMO_DRIVER_MODEL} />);

    expect(within(getRow(container, "dr-d05")).getByRole("note")).toHaveTextContent("Schedule not verified");
  });

  it("draws a night shift that crosses midnight as a single shift (D06)", () => {
    const { container } = render(<ShiftTimeline model={DEMO_DRIVER_MODEL} />);
    const row = getRow(container, "dr-d06");

    expect(row.querySelectorAll('[data-kind="shift"]')).toHaveLength(1);
    expect(row.querySelector('[data-kind="shift"]')).toHaveAttribute("title", "Official shift: 18:00–02:00");
    expect(row.querySelector('[data-kind="outside-schedule"]')).toBeNull();
  });
});