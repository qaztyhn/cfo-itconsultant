import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pos = vi.hoisted(() => ({ url: null as string | null }));
vi.mock("../../api/config", () => ({
  get POS_URL() { return pos.url; },
}));

import { NewOrder } from "./NewOrder";

beforeEach(() => { pos.url = null; });

describe("Sales New order POS entry", () => {
  it("test_US_ORD_01_AC1_does not send Sales to localhost when no POS web UI is configured", () => {
    render(<MemoryRouter><NewOrder /></MemoryRouter>);

    expect(screen.getByRole("heading", { name: "New order" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/POS web application is not configured/);
    expect(screen.queryByRole("link", { name: "Open POS" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sync & confirm delivery" })).toHaveAttribute("href", "/store/sync-check");
  });

  it("opens a configured POS web UI separately without creating a CFO source order", () => {
    pos.url = "https://pos.example.test";
    render(<MemoryRouter><NewOrder /></MemoryRouter>);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open POS" })).toHaveAttribute("href", "https://pos.example.test");
    expect(screen.getByRole("link", { name: "Open POS" })).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: "Open POS" })).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: "My store orders" })).toHaveAttribute("href", "/store/orders");
  });
});
