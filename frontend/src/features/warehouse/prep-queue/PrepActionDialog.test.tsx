import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import { orderApproved, orderMultiVehicle, orderRunning } from "./fixtures";
import { PrepActionDialog, type ActionChoice } from "./PrepActionDialog";
import { submitPrepEvent } from "./executionActions";

vi.mock("./executionActions", async (original) => ({
  ...(await original<typeof import("./executionActions")>()),
  submitPrepEvent: vi.fn(),
}));

function open(choice: ActionChoice) {
  const onClose = vi.fn();
  const onAcknowledged = vi.fn().mockResolvedValue(undefined);
  const onReload = vi.fn().mockResolvedValue(undefined);
  render(<PrepActionDialog choice={choice} warehouseId={1} onClose={onClose}
    onAcknowledged={onAcknowledged} onReload={onReload} />);
  return { onClose, onAcknowledged, onReload };
}

beforeEach(() => {
  vi.mocked(submitPrepEvent).mockReset().mockResolvedValue({ event_id: 99, order_status: "PREPARING" });
});

describe("Round 3 warehouse milestone confirmation", () => {
  it("test_US_WH_01_AC1_collects_crew_size_at_START_PREP_only", async () => {
    const { onClose } = open({ order: orderApproved(), type: "START_PREP" });
    const user = userEvent.setup();
    await user.clear(screen.getByRole("spinbutton", { name: /Crew size/ }));
    await user.type(screen.getByRole("spinbutton", { name: /Crew size/ }), "4");
    await user.click(screen.getByRole("button", { name: "Confirm Start preparation" }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(vi.mocked(submitPrepEvent).mock.calls[0][0].payload).toEqual({ crew_size: 4 });
  });

  it("test_US_WH_01_AC1_confirms_GOODS_READY_with_empty_payload", async () => {
    open({ order: orderRunning(), type: "GOODS_READY" });
    expect(screen.queryByRole("spinbutton", { name: /Crew size/ })).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "Confirm Goods ready" }));
    await waitFor(() => expect(submitPrepEvent).toHaveBeenCalledTimes(1));
    expect(vi.mocked(submitPrepEvent).mock.calls[0][0].payload).toEqual({});
  });

  it("test_US_WH_01_AC2_loads_the_specified_vehicle_trip", async () => {
    open({ order: orderMultiVehicle(), type: "LOADED", tripId: 942, vehicleCode: "GBG-18-05" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Confirm Mark loaded" }));
    await waitFor(() => expect(submitPrepEvent).toHaveBeenCalledTimes(1));
    expect(vi.mocked(submitPrepEvent).mock.calls[0][0].payload).toEqual({ trip_id: 942 });
  });

  it("test_US_WH_01_AC3_does_not_resend_while_the_first_request_is_pending", async () => {
    let release!: (value: { event_id: number; order_status: string }) => void;
    vi.mocked(submitPrepEvent).mockImplementation(() => new Promise((resolve) => { release = resolve; }));
    const { onClose } = open({ order: orderApproved(), type: "START_PREP" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Confirm Start preparation" }));
    const pending = screen.getByRole("button", { name: /Sending/ });
    expect(pending).toBeDisabled();
    expect(submitPrepEvent).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
    release({ event_id: 90, order_status: "PREPARING" });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("test_US_WH_01_AC4_409_never_replays_the_stale_request_without_refresh", async () => {
    vi.mocked(submitPrepEvent).mockRejectedValueOnce(new ApiError("ILLEGAL_TRANSITION", "private details", "c", undefined, 409));
    const { onReload, onClose } = open({ order: orderApproved(), type: "START_PREP" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Confirm Start preparation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Refresh the queue/);
    expect(screen.queryByText("private details")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry same event" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Reload queue" }));
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(1));
    expect(submitPrepEvent).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("test_US_WH_01_AC4_network_retry_reuses_the_same_immutable_event", async () => {
    vi.mocked(submitPrepEvent).mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "offline", "c", undefined, 0))
      .mockResolvedValueOnce({ event_id: 50, order_status: "PREPARING" });
    const { onClose } = open({ order: orderApproved(), type: "START_PREP" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Confirm Start preparation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/unconfirmed/);
    expect(screen.getByRole("spinbutton", { name: /Crew size/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Retry same event" }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    const events = vi.mocked(submitPrepEvent).mock.calls.map((call) => call[0]);
    expect(events[0]).toBe(events[1]);
  });

  it("test_US_WH_01_AC3_after_ACK_never_reposts_if_refresh_fails", async () => {
    const { onAcknowledged, onClose } = open({ order: orderApproved(), type: "START_PREP" });
    onAcknowledged.mockRejectedValueOnce(new Error("read failed")).mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Confirm Start preparation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/accepted, but the queue could not be refreshed/);
    expect(submitPrepEvent).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Retry queue refresh" }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(submitPrepEvent).toHaveBeenCalledTimes(1);
  });
});
