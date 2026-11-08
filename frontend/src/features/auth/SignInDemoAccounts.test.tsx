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


describe("SignIn two-half layout (docs/03 mục 5.0)", () => {
  it("shows the brand half, the form half and the footer note", () => {
    render(<SignIn env="demo" />);

    expect(screen.getByText("ORDER-TO-DELIVERY ORCHESTRATION")).toBeInTheDocument();
    expect(screen.getByText("Make every order a reliable, visible promise.")).toBeInTheDocument();
    for (const title of ["Time-phased inventory", "Warehouse readiness", "Fleet & delivery"]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
    expect(screen.getByText("Sweden pilot · synthetic data · v0.1-demo")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("Use your work account. Access follows your role.")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("name@company.se")).toBeInTheDocument();
    expect(screen.getByText(/Customers have no login/)).toBeInTheDocument();
  });

  it("uses the demo hints from the spec on the cards", () => {
    render(<SignIn env="demo" />);

    for (const hint of ["Plans & approvals", "Order intake", "Prep & milestones", "PWA on phone", "Data & inbox", "Status & contact log", "KPIs, read-only"]) {
      expect(screen.getByText(hint)).toBeInTheDocument();
    }
  });

  it("keeps the brand half and the footer note in production, without demo cards", () => {
    render(<SignIn env="production" />);

    expect(screen.getByText("Make every order a reliable, visible promise.")).toBeInTheDocument();
    expect(screen.getByText(/Customers have no login/)).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Demo accounts" })).toBeNull();
  });
});
