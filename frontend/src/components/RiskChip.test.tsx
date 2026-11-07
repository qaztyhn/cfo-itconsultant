import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RiskChip } from "./RiskChip";

describe("RiskChip (03 mục 2.1)", () => {
  it("renders nothing when there is no risk data, instead of claiming On track", () => {
    const { container } = render(<RiskChip />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it.each([
    ["green", "Risk: On track", "bg-risk-onTrack-bg"],
    ["yellow", "Risk: At risk", "bg-risk-atRisk-bg"],
    ["orange", "Risk: At risk", "bg-risk-atRisk-bg"],
    ["red", "Risk: Predicted late", "bg-risk-predictedLate-bg"],
  ] as const)("maps risk_color %s to its label and palette", (color, name, bg) => {
    render(<RiskChip color={color} />);

    expect(screen.getByRole("img", { name })).toHaveClass(bg);
  });

  it("gives orange At risk a 3px apricot left border, and yellow none", () => {
    const { rerender } = render(<RiskChip level="AT_RISK" color="orange" />);
    expect(screen.getByRole("img")).toHaveClass("border-l-[3px]", "border-l-apricot");

    rerender(<RiskChip level="AT_RISK" color="yellow" />);
    expect(screen.getByRole("img").className).not.toMatch(/border-l/);
  });

  it("uses risk_status for the label so red can be Overdue (white on dark red)", () => {
    render(<RiskChip level="OVERDUE" color="red" />);

    const chip = screen.getByRole("img", { name: "Risk: Overdue" });
    expect(chip).toHaveClass("bg-risk-overdue-bg", "text-risk-overdue-fg");
  });

  it("test_#35_has a dot before the text and an accessible name that reads the full label", () => {
    render(<RiskChip level="PREDICTED_LATE" color="red" />);

    const chip = screen.getByRole("img", { name: "Risk: Predicted late" });
    const [dot] = Array.from(chip.children);
    expect(dot).toHaveAttribute("aria-hidden", "true");
    expect(dot).toHaveClass("rounded-full");
    expect(chip).toHaveTextContent("Predicted late");
  });

  it("appends a custom className without dropping the base classes", () => {
    render(<RiskChip level="ON_TRACK" className="ml-2" />);
    expect(screen.getByRole("img")).toHaveClass("ml-2", "rounded-full");
  });
});