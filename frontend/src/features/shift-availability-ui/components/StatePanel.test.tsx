import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PanelState } from "../types";
import { StatePanel } from "./StatePanel";

type Data = { count: number };

function renderPanel(state: PanelState<Data>, body = vi.fn((d: Data) => <p>Count: {d.count}</p>)) {
  render(<StatePanel state={state}>{body}</StatePanel>);
  return body;
}

describe("StatePanel", () => {
  it("shows a busy status while loading and does not render the body", () => {
    const body = renderPanel({ status: "loading" });

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(body).not.toHaveBeenCalled();
  });

  it("shows the default or a custom empty message", () => {
    const { unmount } = render(
      <StatePanel<Data> state={{ status: "empty" }}>{() => null}</StatePanel>,
    );
    expect(screen.getByText("No shifts to show for this period")).toBeInTheDocument();
    unmount();

    render(<StatePanel<Data> state={{ status: "empty", message: "Nothing today" }}>{() => null}</StatePanel>);
    expect(screen.getByText("Nothing today")).toBeInTheDocument();
  });

  it("shows an error alert with the correlation id and a working Retry button", async () => {
    const onRetry = vi.fn();
    renderPanel({ status: "error", error: { message: "Load failed", correlationId: "corr-123" }, onRetry });

    expect(screen.getByRole("alert")).toHaveTextContent("Load failed");
    expect(screen.getByText("corr-123")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("omits Retry and the correlation id when they are not supplied", () => {
    renderPanel({ status: "error", error: { message: "Load failed" } });

    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.queryByText(/Correlation ID/)).toBeNull();
  });

  it("shows unavailable as a status, not as an error", () => {
    renderPanel({ status: "unavailable" });

    expect(screen.getByRole("status")).toHaveTextContent("Shift data is not available yet");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders the body with the data when ready", () => {
    const body = renderPanel({ status: "ready", data: { count: 3 } });

    expect(screen.getByText("Count: 3")).toBeInTheDocument();
    expect(body).toHaveBeenCalledWith({ count: 3 });
  });
});