import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SchedulingWarning } from "../types";
import { WarningList } from "./WarningList";

const WARNINGS: SchedulingWarning[] = [
  {
    id: "w1",
    severity: "blocking",
    code: "DRIVER_REST_INSUFFICIENT",
    message: "Driver rest is insufficient; this plan cannot be approved.",
    ruleSource: "DEC-DRIVER-001",
  },
  { id: "w2", severity: "info", code: "SCHEDULE_PARTIAL", message: "One schedule is not verified." },
];

describe("WarningList", () => {
  it("renders nothing when there are no warnings", () => {
    const { container } = render(<WarningList warnings={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows severity word, code, message and rule source for each warning", () => {
    render(<WarningList warnings={WARNINGS} />);

    expect(screen.getByText("Blocking")).toBeInTheDocument();
    expect(screen.getByText("DRIVER_REST_INSUFFICIENT")).toBeInTheDocument();
    expect(screen.getByText("Driver rest is insufficient; this plan cannot be approved.")).toBeInTheDocument();
    expect(screen.getByText("DEC-DRIVER-001")).toBeInTheDocument();
    expect(screen.getByText("Info")).toBeInTheDocument();
  });

  it("marks each item with its severity and announces changes politely", () => {
    const { container } = render(<WarningList warnings={WARNINGS} />);

    expect(container.querySelector('[data-severity="blocking"]')).not.toBeNull();
    expect(container.querySelector('[data-severity="info"]')).not.toBeNull();
    expect(screen.getByRole("list")).toHaveAttribute("aria-live", "polite");
  });

  it("can hide the heading and accepts label overrides", () => {
    const { rerender } = render(<WarningList warnings={WARNINGS} />);
    expect(screen.getByRole("heading", { name: "Scheduling warnings" })).toBeInTheDocument();

    rerender(<WarningList warnings={WARNINGS} showTitle={false} labels={{ warningSeverity: { blocking: "Stop" } }} />);
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.getByText("Stop")).toBeInTheDocument();
  });
});