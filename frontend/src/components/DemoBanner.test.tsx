import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DemoBanner } from "./DemoBanner";

describe("DemoBanner", () => {
  it("shows the DEMO label and the screen context outside production", () => {
    render(<DemoBanner env="demo" context="Orders are synthetic." />);

    expect(screen.getByRole("note")).toBeInTheDocument();
    expect(screen.getByText("DEMO · SYNTHETIC DATA")).toBeInTheDocument();
    expect(screen.getByText("Orders are synthetic.")).toBeInTheDocument();
  });

  it("renders nothing in production", () => {
    const { container } = render(<DemoBanner env="production" context="x" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("warns about the mock API only when mocks are on", () => {
    const { rerender } = render(<DemoBanner env="demo" mock />);
    expect(screen.getByText(/not integrated with the real backend/)).toBeInTheDocument();

    rerender(<DemoBanner env="demo" mock={false} />);
    expect(screen.queryByText(/not integrated/)).toBeNull();
  });

  it("omits the context line when none is given", () => {
    render(<DemoBanner env="demo" mock={false} />);

    expect(screen.getByRole("note").children).toHaveLength(1);
  });
});
