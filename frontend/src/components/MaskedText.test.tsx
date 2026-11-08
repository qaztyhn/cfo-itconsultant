import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MaskedText } from "./MaskedText";

describe("MaskedText", () => {
  it("masks an email by default and keeps the raw value out of the DOM", () => {
    const { container } = render(<MaskedText kind="email" value="anna.berg@takservice.demo" />);

    expect(screen.getByText("a•••@takservice.demo")).toBeInTheDocument();
    expect(container.innerHTML).not.toContain("anna.berg");
  });

  it("masks a phone number the way the spec shows", () => {
    render(<MaskedText kind="phone" value="+46 70 123 12 34" />);
    expect(screen.getByText("+46 •• ••• 12 34")).toBeInTheDocument();
  });

  it("shows the full value only when the caller reveals it", () => {
    render(<MaskedText kind="email" value="anna.berg@takservice.demo" revealed />);
    expect(screen.getByText("anna.berg@takservice.demo")).toBeInTheDocument();
  });

  it("tells screen readers the value is hidden instead of reading bullets", () => {
    render(<MaskedText kind="phone" value="+46 70 123 12 34" />);

    expect(screen.getByText("Phone number (hidden)")).toHaveClass("sr-only");
    expect(screen.getByText("+46 •• ••• 12 34")).toHaveAttribute("aria-hidden", "true");
  });

  it("shows a dash when there is no value", () => {
    render(<MaskedText kind="email" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("uses the mono font", () => {
    const { container } = render(<MaskedText kind="email" value="a@b.se" />);
    expect(container.firstChild).toHaveClass("font-mono");
  });
});