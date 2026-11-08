import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DEMO_DRIVER_ROWS } from "../fixtures";
import type { DriverRow } from "../types";
import { DriverEligibilityList } from "./DriverEligibilityList";

function driver(id: string): DriverRow {
  const row = DEMO_DRIVER_ROWS.find((r) => r.id === id);
  if (!row) throw new Error(`Missing demo driver ${id}`);
  return row;
}

describe("DriverEligibilityList", () => {
  it("states that eligibility was not evaluated when there are no results (regression)", () => {
    const { container } = render(<DriverEligibilityList items={[]} />);

    expect(container).not.toBeEmptyDOMElement();
    expect(screen.getByRole("note")).toHaveTextContent("Eligibility not evaluated");
    expect(screen.getByText(/Do not treat this driver as meeting all requirements/)).toBeInTheDocument();
    expect(screen.queryByText("Eligible")).toBeNull();
    expect(container.querySelector('[data-eligibility="not-evaluated"]')).toHaveClass("bg-risk-atRisk-bg");
    expect(container.querySelector('[data-eligibility="not-evaluated"]')).not.toHaveClass("bg-risk-onTrack-bg");
  });

  it("accepts label overrides for the not-evaluated message", () => {
    render(<DriverEligibilityList items={[]} labels={{ eligibilityNotEvaluated: "Not checked yet" }} />);

    expect(screen.getByText("Not checked yet")).toBeInTheDocument();
  });

  it("shows a missing-history result as Unknown with its reason code, never as eligible", () => {
    const { container } = render(<DriverEligibilityList items={driver("dr-d03").eligibility} />);

    expect(screen.getByText("Driving history")).toBeInTheDocument();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
    expect(screen.getByText("DRIVER_HISTORY_MISSING · DEC-DEV2-D7-001")).toBeInTheDocument();
    expect(screen.queryByText("Eligible")).toBeNull();
    expect(container.querySelector('[data-status="unknown"]')).toHaveClass("bg-risk-atRisk-bg");
    expect(container.querySelector('[data-status="unknown"]')).not.toHaveClass("bg-risk-onTrack-bg");
  });

  it("shows insufficient rest as Not eligible with its reason code", () => {
    render(<DriverEligibilityList items={driver("dr-d02").eligibility} />);

    expect(screen.getByText("Not eligible")).toBeInTheDocument();
    expect(screen.getByText("DRIVER_REST_INSUFFICIENT · DEC-DRIVER-001")).toBeInTheDocument();
  });

  it("shows the vehicle scope as unknown, distinct from the other states", () => {
    const { container } = render(<DriverEligibilityList items={driver("dr-d04").eligibility} />);

    expect(screen.getByText("Vehicle scope")).toBeInTheDocument();
    expect(container.querySelector('[data-kind="vehicle_scope"]')).toHaveAttribute("data-status", "unknown");
  });

  it("shows eligible results with an Eligible label", () => {
    render(<DriverEligibilityList items={driver("dr-d01").eligibility} />);

    expect(screen.getAllByText("Eligible").length).toBeGreaterThan(0);
  });
});