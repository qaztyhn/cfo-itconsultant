import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AssignmentStatus } from "../types";
import { AssignmentStatusBadge } from "./AssignmentStatusBadge";

describe("AssignmentStatusBadge", () => {
  it.each([
    ["assigned", "Assigned"],
    ["tentative", "Tentative"],
    ["available", "Available"],
    ["conflict", "Conflict"],
    ["unavailable", "Unavailable"],
  ] as const)("shows a text label for %s (never colour alone)", (status: AssignmentStatus, label) => {
    const { container } = render(<AssignmentStatusBadge status={status} />);

    expect(screen.getByText(label)).toBeInTheDocument();
    expect(container.querySelector(`[data-status="${status}"]`)).not.toBeNull();
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("uses token classes for conflict", () => {
    const { container } = render(<AssignmentStatusBadge status="conflict" />);

    expect(container.firstElementChild).toHaveClass("bg-risk-predictedLate-bg");
  });

  it("accepts label overrides", () => {
    render(<AssignmentStatusBadge status="assigned" labels={{ assignmentStatus: { assigned: "Booked" } }} />);

    expect(screen.getByText("Booked")).toBeInTheDocument();
  });
});