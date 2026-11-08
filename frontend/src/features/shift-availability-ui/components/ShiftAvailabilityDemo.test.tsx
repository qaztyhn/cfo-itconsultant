import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ShiftAvailabilityDemo } from "./ShiftAvailabilityDemo";

describe("ShiftAvailabilityDemo", () => {
  it("renders both panels from the synthetic fixtures", () => {
    render(<ShiftAvailabilityDemo />);

    expect(screen.getByRole("heading", { name: "Warehouse staff shifts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Driver shifts and availability" })).toBeInTheDocument();
    expect(screen.getByText("Synthetic demo data")).toBeInTheDocument();
  });

  it("switches both panels to loading with the labelled state selector", async () => {
    render(<ShiftAvailabilityDemo />);

    await userEvent.selectOptions(screen.getByLabelText("Demo state"), "loading");

    expect(screen.getAllByRole("status")).toHaveLength(2);
  });

  it("shows an error in both panels and recovers on Retry", async () => {
    render(<ShiftAvailabilityDemo />);

    await userEvent.selectOptions(screen.getByLabelText("Demo state"), "error");
    expect(screen.getAllByRole("alert")).toHaveLength(2);
    expect(screen.getAllByText("demo-corr-0001")).toHaveLength(2);

    await userEvent.click(screen.getAllByRole("button", { name: "Retry" })[0]);

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getAllByRole("region", { name: "Shift timeline" })).toHaveLength(2);
  });
});