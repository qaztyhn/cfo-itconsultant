import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { API_BASE_URL } from "../../api/config";
import { currentPath, renderAt, signInAs, userByEmail } from "../../test/utils";
import { setupOrderQueueMsw } from "./orderQueue/testServer";

const LIVE = API_BASE_URL + "/gps/live";
const LOCATIONS = API_BASE_URL + "/locations";
const RECEIVERS = API_BASE_URL + "/__mock/t17/trips/:id/eligible-dispatchers";
const HANDOVER = API_BASE_URL + "/trips/:id/handover";

function trip(over: Record<string, unknown> = {}) {
  return {
    trip_id: 930, order_id: 249, vehicle_code: "STO-12-04",
    last_position: { lat: 57.70, lon: 11.97 },
    remaining_km: 12, updated_at: "2026-11-12T09:52:00Z",
    forecast_eta: "2026-11-12T10:20:00Z",
    risk: { status: "ON_TRACK", color: "green" },
    open_incident: null, ...over,
  };
}
const TWO = [
  trip(),
  trip({ trip_id: 931, vehicle_code: "STO-18-01", last_position: null,
    remaining_km: null, updated_at: null }),
];
const errorBody = (code: string) => ({
  error: { code, message: "Internal sensitive detail must not appear", correlation_id: "test" },
});

const server = setupOrderQueueMsw(
  http.get(LIVE, () => HttpResponse.json(TWO)),
  http.get(LOCATIONS, () => HttpResponse.json({
    items: [{ id: 1, type: "warehouse", code: "STO", name: "Stockholm DC",
      timezone: "Europe/Stockholm" }],
    total: 1, page: 1, page_size: 200,
  })),
  http.get(RECEIVERS, () => HttpResponse.json({
    items: [{ employee_id: 109, display_name: "Erik Holm" }],
  })),
);

beforeEach(() => signInAs(userByEmail("dispatcher@cfo.demo")));

const main = () => within(screen.getByRole("main"));
const assigned = (id: number) => main().getByRole("listitem", { name: "Chuyến " + id });

describe("T17 Dispatcher live tracking (MSW)", () => {
  it("test_US_GPS_02_AC1_many_trips_show_latest_coordinates_market_time_and_risk", async () => {
    renderAt("/dispatcher/tracking");
    expect(await main().findByText("Chuyến #930 · STO-12-04")).toBeInTheDocument();
    expect(main().getByText("Chuyến #931 · STO-18-01")).toBeInTheDocument();
    expect(within(assigned(930)).getByText("57.70, 11.97")).toBeInTheDocument();
    expect(within(assigned(930)).getByText("12 km", { exact: false })).toBeInTheDocument();
    expect(within(assigned(930)).getByText("Rủi ro: Đúng kế hoạch")).toBeInTheDocument();
    expect(within(assigned(931)).getByText("Chưa có vị trí")).toBeInTheDocument();
    expect(within(assigned(931)).getByText("Chưa có dữ liệu")).toBeInTheDocument();
    await waitFor(() => expect(within(assigned(930)).getByText("12/11 10:52")).toBeInTheDocument());
    expect(within(assigned(930)).getByText("12/11 11:20")).toBeInTheDocument();
    expect(main().queryByRole("img", { name: /map/i })).toBeNull();
    expect(main().queryByText(/lịch sử điểm/i)).toBeNull();
  });

  it("test_US_GPS_02_AC1_vehicle_breakdown_forces_unknown_eta_even_if_server_sends_forecast", async () => {
    server.use(http.get(LIVE, () => HttpResponse.json([
      trip({ open_incident: "vehicle_breakdown", forecast_eta: "2026-11-12T10:20:00Z" }),
    ])));
    renderAt("/dispatcher/tracking");
    expect(await main().findByText("ETA không xác định")).toBeInTheDocument();
    expect(main().getByText("Sự cố mở: Xe hỏng")).toBeInTheDocument();
    expect(main().queryByText("12/11 11:20")).toBeNull();
  });

  it("test_US_GPS_02_AC1_loading_empty_and_api_error_are_explicit", async () => {
    server.use(http.get(LIVE, async () => {
      await delay("infinite");
      return HttpResponse.json([]);
    }));
    const first = renderAt("/dispatcher/tracking");
    expect(main().getByRole("status", { name: "" })).toHaveAttribute("aria-busy", "true");
    first.unmount();

    server.use(http.get(LIVE, () => HttpResponse.json([])));
    renderAt("/dispatcher/tracking");
    expect(await main().findByText("Không có chuyến đang chạy được gán cho bạn.")).toBeInTheDocument();
  });

  it("test_US_GPS_02_AC1_failed_list_is_not_misrepresented_as_zero_trips", async () => {
    server.use(http.get(LIVE, () => HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 })));
    renderAt("/dispatcher/tracking");
    expect(await main().findByRole("alert")).toHaveTextContent("Không thể tải vị trí trực tiếp");
    expect(main().queryByText("Không có chuyến đang chạy được gán cho bạn.")).toBeNull();
    expect(document.body.textContent).not.toContain("Internal sensitive detail");
    server.use(http.get(LIVE, () => HttpResponse.json(TWO)));
    await userEvent.setup().click(main().getByRole("button", { name: "Retry" }));
    expect(await main().findByText("Chuyến #930 · STO-12-04")).toBeInTheDocument();
  });

  it("test_US_GPS_02_AC1_missing_timezone_never_uses_browser_locale", async () => {
    server.use(http.get(LOCATIONS, () => HttpResponse.json({ items: [], total: 0 })));
    renderAt("/dispatcher/tracking");
    expect(await main().findByText("Chuyến #930 · STO-12-04")).toBeInTheDocument();
    expect(await main().findByText(/Múi giờ market chưa xác minh/)).toBeInTheDocument();
    expect(within(assigned(930)).getAllByText("Chưa xác định múi giờ market")).toHaveLength(2);
  });

  it("test_US_GPS_02_AC3_requires_reason_and_posts_only_the_selected_trip_then_refetches", async () => {
    let getCount = 0;
    let calls = 0;
    let body: unknown;
    let tripId = "";
    let rows = [...TWO];
    server.use(
      http.get(LIVE, () => { getCount += 1; return HttpResponse.json(rows); }),
      http.post(HANDOVER, async ({ params, request }) => {
        calls += 1;
        tripId = String(params.id);
        body = await request.json();
        rows = rows.filter((item) => item.trip_id !== Number(params.id));
        return HttpResponse.json({ trip_id: params.id });
      }),
    );
    renderAt("/dispatcher/tracking");
    expect(await main().findByText("Chuyến #930 · STO-12-04")).toBeInTheDocument();
    await userEvent.setup().click(within(assigned(930)).getByRole("button", { name: "Bàn giao chuyến" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Xác nhận bàn giao" });
    expect(confirm).toBeDisabled();
    expect(within(dialog).getByText("Lý do bàn giao là bắt buộc.")).toBeInTheDocument();
    expect(calls).toBe(0);
    const user = userEvent.setup();
    await user.selectOptions(within(dialog).getByLabelText("Dispatcher nhận chuyến"), "109");
    await user.type(within(dialog).getByLabelText("Lý do bàn giao (bắt buộc)"), "End of shift");
    await user.click(confirm);
    await waitFor(() => expect(getCount).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(main().queryByText("Chuyến #930 · STO-12-04")).toBeNull());
    expect(main().getByText("Chuyến #931 · STO-18-01")).toBeInTheDocument();
    expect(tripId).toBe("930");
    expect(body).toEqual({ to_employee_id: 109, reason_text: "End of shift" });
    expect(calls).toBe(1);
  });

  it("test_US_GPS_02_AC3_post_error_keeps_receiver_and_reason_with_safe_feedback", async () => {
    let calls = 0;
    server.use(http.post(HANDOVER, () => {
      calls += 1;
      return HttpResponse.json(errorBody("VALIDATION_ERROR"), { status: 422 });
    }));
    renderAt("/dispatcher/tracking");
    await main().findByText("Chuyến #930 · STO-12-04");
    const user = userEvent.setup();
    await user.click(within(assigned(931)).getByRole("button", { name: "Bàn giao chuyến" }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Dispatcher nhận chuyến"), "109");
    await user.type(within(dialog).getByLabelText("Lý do bàn giao (bắt buộc)"), "Capacity handoff");
    await user.click(within(dialog).getByRole("button", { name: "Xác nhận bàn giao" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("không còn đủ điều kiện");
    expect(within(dialog).getByLabelText("Dispatcher nhận chuyến")).toHaveValue("109");
    expect(within(dialog).getByLabelText("Lý do bàn giao (bắt buộc)")).toHaveValue("Capacity handoff");
    expect(main().getByText("Chuyến #931 · STO-18-01")).toBeInTheDocument();
    expect(calls).toBe(1);
    expect(document.body.textContent).not.toContain("Internal sensitive detail");
  });

  it("test_US_GPS_02_AC2_route_guard_and_backend_403_prevent_position_disclosure", async () => {
    signInAs(userByEmail("sales@cfo.demo"));
    let calls = 0;
    server.use(http.get(LIVE, () => { calls += 1; return HttpResponse.json(TWO); }));
    const denied = renderAt("/dispatcher/tracking");
    await waitFor(() => expect(currentPath()).not.toBe("/dispatcher/tracking"));
    expect(calls).toBe(0);
    denied.unmount();

    signInAs(userByEmail("dispatcher@cfo.demo"));
    server.use(http.get(LIVE, () => HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 })));
    renderAt("/dispatcher/tracking");
    expect(await main().findByText("Không thể tải vị trí trực tiếp")).toBeInTheDocument();
    expect(main().queryByText("Chuyến #930 · STO-12-04")).toBeNull();
    expect(main().queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
