import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "./StateViews";

describe("EmptyState", () => {
  it("shows one sentence, a decorative icon and an optional action (03 mục 4)", async () => {
    const onClick = vi.fn();
    render(<EmptyState message="No orders match these filters" action={{ label: "Clear filters", onClick }} />);

    expect(screen.getByText("No orders match these filters")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("renders without an action", () => {
    render(<EmptyState message="Nothing here" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("LoadingState", () => {
  it("is announced as busy and draws the requested number of skeleton rows at table-row height", () => {
    const { container } = render(<LoadingState rows={3} />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Loading…")).toHaveClass("sr-only");
    const rows = container.querySelectorAll("[aria-hidden='true']");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveClass("h-[72px]", "bg-chip");
  });
});

describe("ErrorState", () => {
  const error = new ApiError("RESOURCE_CONFLICT", "The truck was taken by another order.", "corr-9", undefined, 409);

  it("shows the API message, the correlation id in mono, and retries on demand", async () => {
    const onRetry = vi.fn();
    render(<ErrorState error={error} onRetry={onRetry} />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("bg-risk-lateRow");
    expect(screen.getByText("The truck was taken by another order.")).toBeInTheDocument();
    expect(screen.getByText("corr-9")).toHaveClass("font-mono");

    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("copies the correlation id", async () => {
    const user = userEvent.setup();
    render(<ErrorState error={error} />);

    await user.click(screen.getByRole("button", { name: "Copy" }));

    expect(await navigator.clipboard.readText()).toBe("corr-9");
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("hides Retry for FORBIDDEN and uses a plain permission message (ASM-L)", () => {
    render(<ErrorState error={new ApiError("FORBIDDEN", "role not allowed", "c-1", undefined, 403)} onRetry={() => undefined} />);

    expect(screen.getByText("You don't have permission to view this.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("shows the friendly network message from the client", () => {
    render(<ErrorState error={new ApiError("NETWORK_ERROR", "Cannot reach the server. Check your connection and retry.", "c-2", undefined, 0)} onRetry={() => undefined} />);
    expect(screen.getByText(/Cannot reach the server/)).toBeInTheDocument();
  });

  it("copes with a non-API error and has no reference line", () => {
    render(<ErrorState error={new TypeError("boom")} />);

    expect(screen.getByText("Unexpected error. Try again.")).toBeInTheDocument();
    expect(screen.queryByText("Reference")).toBeNull();
    expect(screen.queryByText("boom")).toBeNull();
  });
});