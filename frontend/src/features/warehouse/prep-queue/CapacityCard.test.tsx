import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CapacityCard } from "./CapacityCard";
import { capacityNoSchedule, capacityUnverified, capacityVerified } from "./fixtures";

const TZ = "Europe/Stockholm";

/** Testing Library collapses all whitespace (including U+202F) to a plain space, so normalise the expected text the same way. */
const plain = (text: string) => text.replace(/\u202f/g, " ");

describe("CapacityCard (US-WH-02, ASM-007)", () => {
  it("shows the headline and the per-shift formula for a verified schedule", () => {
    render(<CapacityCard capacity={capacityVerified()} timeZone={TZ} />);

    expect(screen.getByRole("heading", { name: "Capacity today" })).toBeInTheDocument();
    expect(screen.getByText(plain("4\u202f524 of 5\u202f292 min booked · 768 free"))).toBeInTheDocument();
    expect(screen.getByText(plain("8 present × 7.0 h useful × 90% = 3\u202f024 min · fully booked"))).toBeInTheDocument();
    expect(screen.getByText(plain("6 present × 7.0 h useful × 90% = 2\u202f268 min"))).toBeInTheDocument();
    expect(screen.queryByText(/Capacity not verified/)).not.toBeInTheDocument();
  });

  it("warns when the API does not say the schedule is verified, even if people are present", () => {
    render(<CapacityCard capacity={capacityUnverified()} timeZone={TZ} />);

    expect(screen.getByRole("status")).toHaveTextContent("Capacity not verified");
    expect(screen.getByRole("status")).toHaveTextContent("Do not use these figures to promise delivery");
  });

  it("says no official schedule is entered and shows no shifts or headline", () => {
    render(<CapacityCard capacity={capacityNoSchedule()} timeZone={TZ} />);

    expect(screen.getByRole("status")).toHaveTextContent("No official shift schedule is entered for today.");
    expect(screen.queryByTestId("capacity-bar")).not.toBeInTheDocument();
    expect(screen.queryByText(/min booked ·/)).not.toBeInTheDocument();
  });

  it("has no equipment row and shows the labour-standards banner", () => {
    render(<CapacityCard capacity={capacityVerified()} timeZone={TZ} />);

    expect(screen.queryByText(/equipment|forklift|crane/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Labour standards are shared rule-based assumptions set by IT/)).toBeInTheDocument();
  });

  it("shows the loading cut-off time", () => {
    render(<CapacityCard capacity={capacityVerified()} timeZone={TZ} />);
    expect(screen.getByText("15:00")).toBeInTheDocument();
  });
});