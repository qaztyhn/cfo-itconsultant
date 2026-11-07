import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusChip, type OrderStatus } from "./StatusChip";

// `satisfies Record<OrderStatus, true>` làm test này vỡ biên dịch nếu enum đổi mà danh sách chưa cập nhật.
const ALL = Object.keys({
  SUBMITTED: true,
  BLOCKED_UNMAPPED_SKU: true,
  PLANNED: true,
  APPROVED: true,
  NO_FEASIBLE_DATE: true,
  PREPARING: true,
  GOODS_READY: true,
  LOADED: true,
  DISPATCHED: true,
  DELIVERED: true,
  FAILED: true,
  CANCELLED: true,
} satisfies Record<OrderStatus, true>) as OrderStatus[];

describe("StatusChip", () => {
  it.each(ALL)("shows the exact enum code for %s, uppercase and mono (03 #35)", (status) => {
    render(<StatusChip status={status} />);

    const chip = screen.getByText(status);
    expect(chip).toHaveClass("font-mono", "uppercase", "rounded-full", "text-overline");
  });

  it("does not abbreviate PREPARING and has no MANUAL_PLANNING chip", () => {
    render(<StatusChip status="PREPARING" />);

    expect(screen.getByText("PREPARING")).toBeInTheDocument();
    expect(screen.queryByText(/IN PREP/)).toBeNull();
    expect(screen.queryByText("MANUAL_PLANNING")).toBeNull();
  });

  it.each(["SUBMITTED", "BLOCKED_UNMAPPED_SKU", "PLANNED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED", "CANCELLED"] as const)(
    "%s uses the default chip colours with no extra border (ASM-I)",
    (status) => {
      render(<StatusChip status={status} />);

      const chip = screen.getByText(status);
      expect(chip).toHaveClass("bg-chip", "text-ink");
      expect(chip.className).not.toMatch(/border/);
    },
  );

  it.each(["APPROVED", "DELIVERED"] as const)("%s uses the On track set", (status) => {
    render(<StatusChip status={status} />);
    expect(screen.getByText(status)).toHaveClass("bg-risk-onTrack-bg", "text-risk-onTrack-fg");
  });

  it.each(["NO_FEASIBLE_DATE", "FAILED"] as const)("%s uses the Predicted late set", (status) => {
    render(<StatusChip status={status} />);
    expect(screen.getByText(status)).toHaveClass("bg-risk-predictedLate-bg", "text-risk-predictedLate-fg");
  });

  it("shows the 'Manual plan' sub-label only on APPROVED", () => {
    const { rerender } = render(<StatusChip status="APPROVED" manualPlan />);
    expect(screen.getByText("Manual plan")).toBeInTheDocument();

    rerender(<StatusChip status="APPROVED" />);
    expect(screen.queryByText("Manual plan")).toBeNull();

    rerender(<StatusChip status="PLANNED" manualPlan />);
    expect(screen.queryByText("Manual plan")).toBeNull();
  });

  it("falls back to the default chip for a status the frontend does not know yet", () => {
    render(<StatusChip status={"ON_HOLD" as OrderStatus} />);
    expect(screen.getByText("ON_HOLD")).toHaveClass("bg-chip", "text-ink");
  });
});