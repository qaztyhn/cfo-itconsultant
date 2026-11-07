import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { ReasonModal, type ReasonModalProps } from "./ReasonModal";

const REASONS = [
  { code: "customer_change", label: "Customer changed the order" },
  { code: "stock_issue", label: "Stock issue" },
];

function setup(props: Partial<ReasonModalProps> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const view = render(
    <>
      <button type="button">Open</button>
      <ReasonModal open title="Replan this order" description="The current plan will be superseded." reasons={REASONS} onConfirm={onConfirm} onCancel={onCancel} {...props} />
    </>,
  );
  return { onConfirm, onCancel, user: userEvent.setup(), ...view };
}

describe("ReasonModal (03 mục 4)", () => {
  it("renders nothing while closed", () => {
    render(<ReasonModal open={false} title="Replan" onConfirm={() => undefined} onCancel={() => undefined} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("is an accessible modal dialog with a title and description", () => {
    setup();

    const dialog = screen.getByRole("dialog", { name: "Replan this order" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleDescription("The current plan will be superseded.");
  });

  it("keeps Confirm disabled until a reason is chosen and a note is written", async () => {
    const { user } = setup();
    const confirm = screen.getByRole("button", { name: "Confirm" });
    expect(confirm).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("Reason"), "customer_change");
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText("Note"), "   ");
    expect(confirm).toBeDisabled(); // chỉ có khoảng trắng

    await user.type(screen.getByLabelText("Note"), "Moved to Friday");
    expect(confirm).toBeEnabled();
  });

  it("confirms with reason_code and a trimmed reason_text", async () => {
    const { user, onConfirm } = setup();

    await user.selectOptions(screen.getByLabelText("Reason"), "customer_change");
    await user.type(screen.getByLabelText("Note"), "  Customer moved the delivery  ");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(onConfirm).toHaveBeenCalledWith({ reasonCode: "customer_change", reasonText: "Customer moved the delivery" });
  });

  it("supports endpoints that only need reason_text (cancel, discard, reject)", async () => {
    const { user, onConfirm } = setup({ reasons: undefined, confirmLabel: "Cancel order" });

    expect(screen.queryByLabelText("Reason")).toBeNull();
    await user.type(screen.getByLabelText("Note"), "Duplicate order");
    await user.click(screen.getByRole("button", { name: "Cancel order" }));

    expect(onConfirm).toHaveBeenCalledWith({ reasonCode: undefined, reasonText: "Duplicate order" });
  });

  it("closes with Esc and with the Cancel button, but not by clicking the backdrop", async () => {
    const { user, onCancel } = setup();

    await user.click(screen.getByRole("dialog").parentElement as HTMLElement);
    expect(onCancel).not.toHaveBeenCalled();

    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("moves focus into the dialog on open and returns it to the opener on close", () => {
    const { rerender } = setup();
    expect(screen.getByLabelText("Reason")).toHaveFocus();

    rerender(
      <>
        <button type="button">Open</button>
        <ReasonModal open={false} title="Replan this order" onConfirm={() => undefined} onCancel={() => undefined} />
      </>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("traps Tab and Shift+Tab inside the dialog", async () => {
    const { user } = setup();
    const select = screen.getByLabelText("Reason");
    const cancel = screen.getByRole("button", { name: "Cancel" });

    await user.tab();
    expect(screen.getByLabelText("Note")).toHaveFocus();
    await user.tab();
    expect(cancel).toHaveFocus(); // Confirm đang disabled nên bị bỏ qua
    await user.tab();
    expect(select).toHaveFocus(); // vòng lại đầu

    await user.tab({ shift: true });
    expect(cancel).toHaveFocus();
  });

  it("locks the Esc key and the controls while the request is running", async () => {
    const { user, onCancel } = setup({ onConfirm: vi.fn(() => new Promise<void>(() => undefined)) });

    await user.selectOptions(screen.getByLabelText("Reason"), "stock_issue");
    await user.type(screen.getByLabelText("Note"), "Short on cement");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("shows the API error with its correlation id and stays open so the user can retry", async () => {
    const failing = vi.fn().mockRejectedValue(new ApiError("REASON_REQUIRED", "A reason is required.", "corr-1", undefined, 422));
    const { user } = setup({ onConfirm: failing });

    await user.selectOptions(screen.getByLabelText("Reason"), "stock_issue");
    await user.type(screen.getByLabelText("Note"), "x");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("A reason is required.")).toBeInTheDocument();
    expect(screen.getByText("Ref corr-1")).toHaveClass("font-mono");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
  });

  it("shows a generic message for an unexpected error without leaking its text", async () => {
    const { user } = setup({ reasons: undefined, onConfirm: vi.fn().mockRejectedValue(new TypeError("secret detail")) });

    await user.type(screen.getByLabelText("Note"), "x");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("Something went wrong. Try again.")).toBeInTheDocument();
    expect(screen.queryByText("secret detail")).toBeNull();
  });

  it("starts with an empty form every time it is opened", async () => {
    const { user, rerender } = setup();
    await user.type(screen.getByLabelText("Note"), "draft text");

    const props = { title: "Replan this order", reasons: REASONS, onConfirm: () => undefined, onCancel: () => undefined };
    rerender(<ReasonModal open={false} {...props} />);
    rerender(<ReasonModal open {...props} />);

    expect(screen.getByLabelText("Note")).toHaveValue("");
  });
});