import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { PageHeader, type PageHeaderProps } from "./PageHeader";

function renderHeader(props: PageHeaderProps) {
  return render(
    <MemoryRouter>
      <PageHeader {...props} />
    </MemoryRouter>,
  );
}

describe("PageHeader (03 mục 3.1)", () => {
  it("renders overline, a level-1 title and a one-line description with the spec tokens", () => {
    renderHeader({ overline: "DISPATCHER · SWEDEN", title: "Order queue", description: "Orders waiting for a plan." });

    expect(screen.getByRole("heading", { level: 1, name: "Order queue" })).toHaveClass("text-h1");
    const overline = screen.getByText("DISPATCHER · SWEDEN");
    expect(overline).toHaveClass("font-mono", "uppercase", "text-overline");
    expect(overline.className).not.toMatch(/tracking-widest/);
    expect(screen.getByText("Orders waiting for a plan.")).toHaveClass("text-body");
  });

  it("does not render the title with the old 24px size", () => {
    renderHeader({ title: "Order queue" });
    expect(screen.getByRole("heading", { level: 1 }).className).not.toMatch(/text-2xl/);
  });

  it("omits overline, description and breadcrumb when not given", () => {
    renderHeader({ title: "Order queue" });

    expect(screen.queryByRole("navigation", { name: "Breadcrumb" })).toBeNull();
    expect(document.querySelector("p")).toBeNull();
  });

  it("renders breadcrumbs as client-side links with the current page last", () => {
    renderHeader({
      title: "Acme AB",
      breadcrumbs: [
        { label: "Order queue", href: "/dispatcher/orders" },
        { label: "SE-2026-000123", href: "/dispatcher/orders/SE-2026-000123" },
      ],
    });

    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(nav).toHaveTextContent("Order queue/SE-2026-000123");

    const first = screen.getByRole("link", { name: "Order queue" });
    const last = screen.getByRole("link", { name: "SE-2026-000123" });
    expect(first).toHaveAttribute("href", "/dispatcher/orders");
    expect(first).not.toHaveAttribute("aria-current");
    expect(last).toHaveAttribute("aria-current", "page");
  });

  it("navigates in the SPA instead of reloading the page", () => {
    renderHeader({ title: "Acme AB", breadcrumbs: [{ label: "Order queue", href: "/dispatcher/orders" }] });

    // React Router chặn hành vi mặc định (tải lại trang) khi bấm <Link>; thẻ <a href> thường thì không.
    const notPrevented = fireEvent.click(screen.getByRole("link", { name: "Order queue" }));
    expect(notPrevented).toBe(false);
  });

  it("test_#35_does not collide when two crumbs share a label", () => {
    renderHeader({
      title: "Detail",
      breadcrumbs: [
        { label: "Orders", href: "/a" },
        { label: "Orders", href: "/b" },
      ],
    });

    expect(screen.getAllByRole("link", { name: "Orders" })).toHaveLength(2);
  });
});