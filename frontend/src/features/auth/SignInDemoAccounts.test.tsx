import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SignIn } from "./SignIn";

describe("SignIn demo accounts (docs/03 mục 5.0)", () => {
  it("hides the demo cards, the demo password hint and the DEMO banner in production", () => {
    render(<SignIn env="production" />);

    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Demo accounts" })).toBeNull();
    expect(screen.queryByText(/demo password/i)).toBeNull();
    expect(screen.queryByRole("note")).toBeNull();
  });

  it.each(["demo", "staging"])("shows the demo cards in %s", (env) => {
    render(<SignIn env={env} />);

    expect(screen.getByRole("list", { name: "Demo accounts" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
  });
});
