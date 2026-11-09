import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import { orderApproved, orderMultiVehicle, orderPaused, orderRunning } from "./fixtures";
import { PrepActionDialog, type ActionChoice } from "./PrepActionDialog";
import { submitPrepEvent } from "./executionActions";

vi.mock("./executionActions", async (original) => ({
  ...(await original<typeof import("./executionActions")>()),
  submitPrepEvent: vi.fn(),
}));

function open(choice: ActionChoice) {
  const onClose = vi.fn();
  const onAcknowledged = vi.fn().mockResolvedValue(undefined);
  const view = render(<PrepActionDialog choice={choice} warehouseId={1}
    onClose={onClose} onAcknowledged={onAcknowledged} />);
  return { onClose, onAcknowledged, ...view };
}

beforeEach(() => {
  vi.mocked(submitPrepEvent).mockReset().mockResolvedValue({ event_id: 99, order_status: "PREPARING" });
});

describe("Warehouse action confirmation", () => {
  it.each([
    ["START_PREP", orderApproved(), "Start preparation"],
    ["PREP_PAUSED", orderRunning(), "Pause preparation"],
    ["PREP_RESUMED", orderPaused(), "Resume preparation"],
    ["GOODS_READY", orderRunning(), "Goods ready"],
  ] as const)("confirms %s only after verified server event acknowledgment", async (type, order, label) => {
    const { onClose, onAcknowledged } = open({ order, type });
    const user = userEvent.setup();
    const dialog = screen.getByRole("dialog", { name: `Confirm ${label}` });
    if (type === "START_PREP" || type === "PREP_RESUMED") {
      await user.clear(within(dialog).getByRole("spinbutton", { name: /Crew size/ }));
      await user.type(within(dialog).getByRole("spinbutton", { name: /Crew size/ }), "3");
    }
    expect(onClose).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: `Confirm ${label}` }));
    await waitFor(() => expect(onAcknowledged).toHaveBeenCalledTimes(1));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(submitPrepEvent).toHaveBeenCalledTimes(1);
    const event = vi.mocked(submitPrepEvent).mock.calls[0][0];
    expect(event.event_type).toBe(type);
    expect(event.orderId).toBe(order.order_id);
    expect(event.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(event.occurred_at).toMatch(/Z$/);
  });

  it("loads only one chosen vehicle from the multi-vehicle order", async () => {
    const { onAcknowledged } = open({
      order: orderMultiVehicle(), type: "LOADED", tripId: 942, vehicleCode: "GBG-18-05",
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "Confirm Mark loaded" }));
    await waitFor(() => expect(onAcknowledged).toHaveBeenCalledTimes(1));
    expect(vi.mocked(submitPrepEvent).mock.calls[0][0].payload).toEqual({ trip_id: 942 });
  });

  it.each([
    ["SHORTAGE", "Report shortage", "Quantity missing", "qty_missing"],
    ["BREAKAGE", "Report breakage", "Quantity damaged", "qty"],
  ] as const)("validates SKU and quantity before submitting %s", async (type, label, qtyLabel, field) => {
    open({ order: orderApproved(), type });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: `Confirm ${label}` }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Local SKU is required.");
    expect(submitPrepEvent).not.toHaveBeenCalled();
    await user.type(screen.getByRole("textbox", { name: "Local SKU" }), "SE-CEM");
    await user.clear(screen.getByRole("spinbutton", { name: new RegExp(qtyLabel) }));
    await user.type(screen.getByRole("spinbutton", { name: new RegExp(qtyLabel) }), "4");
    await user.click(screen.getByRole("button", { name: `Confirm ${label}` }));
    await waitFor(() => expect(submitPrepEvent).toHaveBeenCalledTimes(1));
    expect(vi.mocked(submitPrepEvent).mock.calls[0][0].payload).toEqual({ sku: "SE-CEM", [field]: 4 });
  });

  it("rejects vehicle issue without assigned vehicle ID", async () => {
    open({ order: orderApproved(), type: "VEHICLE_ISSUE" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Confirm Report vehicle issue" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/positive whole number for vehicle_id/);
    expect(submitPrepEvent).not.toHaveBeenCalled();
    await user.type(screen.getByRole("spinbutton", { name: "Assigned vehicle ID" }), "17");
    await user.click(screen.getByRole("button", { name: "Confirm Report vehicle issue" }));
    await waitFor(() => expect(submitPrepEvent).toHaveBeenCalledTimes(1));
    expect(vi.mocked(submitPrepEvent).mock.calls[0][0].payload).toEqual({ vehicle_id: 17 });
  });

  it("reports shift change without editing or synthesizing official schedule", async () => {
    open({ order: orderApproved(), type: "SHIFT_CHANGE" });
    expect(screen.getByText(/does not change the official manager-approved shift or capacity/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.clear(screen.getByRole("spinbutton", { name: /Staff present/ }));
    await user.type(screen.getByRole("spinbutton", { name: /Staff present/ }), "0");
    await user.click(screen.getByRole("button", { name: "Confirm Report shift change" }));
    await waitFor(() => expect(submitPrepEvent).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(submitPrepEvent).mock.calls[0][0].payload;
    expect(payload.staff_present).toBe(0);
    expect(payload.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(payload).not.toHaveProperty("expected_staff");
  });

  it("does not close or claim completion before pending server acknowledgment", async () => {
    let release!: (value: { event_id: number; order_status: string }) => void;
    vi.mocked(submitPrepEvent).mockImplementation(() => new Promise((resolve) => { release = resolve; }));
    const { onClose, onAcknowledged } = open({ order: orderApproved(), type: "START_PREP" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Confirm Start preparation" }));
    expect(await screen.findByRole("button", { name: /Sending/ })).toBeDisabled();
    expect(onAcknowledged).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    release({ event_id: 17, order_status: "PREPARING" });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it.each([403, 404, 409, 422, 503])("fails closed on HTTP %i and reuses key for retry", async (status) => {
    vi.mocked(submitPrepEvent).mockRejectedValueOnce(new ApiError("STALE_EVENT", "Unsafe server details", "c", undefined, status))
      .mockResolvedValueOnce({ event_id: 17, order_status: "PREPARING" });
    const { onAcknowledged, onClose } = open({ order: orderApproved(), type: "START_PREP" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Confirm Start preparation" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Unsafe server details")).toBeNull();
    expect(onAcknowledged).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    const retry = screen.getByRole("button", { name: "Retry / confirm same event" });
    await user.click(retry);
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    const [original, replay] = vi.mocked(submitPrepEvent).mock.calls.map((args) => args[0]);
    expect(replay).toBe(original);
  });

  it("blocks a stale illegal order transition before any request", async () => {
    open({ order: orderPaused(), type: "GOODS_READY" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Confirm Goods ready" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/not available for the current order/);
    expect(submitPrepEvent).not.toHaveBeenCalled();
  });
});
