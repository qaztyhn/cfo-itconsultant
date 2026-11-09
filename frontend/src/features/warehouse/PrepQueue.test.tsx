import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../../api/config";
import { fetchLocations } from "../../api/locations";
import { useScopeStore } from "../../app/scope";
import { currentPath, renderAt, signInAs, userByEmail } from "../../test/utils";
import { buildPrepQueueFixture } from "./prep-queue/fixtures";
import { PREP_QUEUE_URL, prepQueueFailure, prepQueueSuccess } from "./prep-queue/mswHandlers";

vi.mock("../../api/locations", () => ({ fetchLocations: vi.fn() }));

// The Sidebar asks for order counts; switch that request off so it never reaches the network.
const countsOff = http.get(`${API_BASE_URL}/orders/counts`, () => HttpResponse.json({ error: { code: "SERVICE_UNAVAILABLE", message: "off", details: {}, correlation_id: "corr-counts" } }, { status: 503 }));
const server = setupServer(countsOff);

let mswFetch: typeof fetch;

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  // Test-only workaround (same as usePrepQueue.test.tsx): jsdom's AbortSignal is rejected by Node's fetch.
  mswFetch = globalThis.fetch;
  vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => mswFetch(input, { ...init, signal: undefined }));
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  vi.unstubAllGlobals();
  server.close();
});

const GBG = { id: 1, code: "GBG", name: "Göteborg DC", type: "warehouse", timezone: "Europe/Stockholm" };
const STO = { id: 2, code: "STO", name: "Stockholm DC", type: "warehouse", timezone: "Europe/Stockholm" };
const GBG_NO_TZ = { id: 1, code: "GBG", name: "Göteborg DC", type: "warehouse" };

const OVERLINE = (name: string) => new RegExp(`^${name} · [A-Z][a-z]+ \\d{1,2} [A-Z][a-z]+$`);

beforeEach(() => {
  useScopeStore.setState({ warehouseId: null });
  vi.mocked(fetchLocations).mockReset();
  vi.mocked(fetchLocations).mockResolvedValue([GBG, STO]);
});

function signInWarehouse() {
  signInAs(userByEmail("wm.got@cfo.demo"));
}

describe("PrepQueue screen (read-only)", () => {
  it("shows the header, capacity card and orders table for the warehouse manager's warehouse", async () => {
    const seen = vi.fn();
    server.use(prepQueueSuccess(buildPrepQueueFixture("verified"), seen));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByRole("table", { name: "Orders to prepare" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Preparation queue" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Capacity today" })).toBeInTheDocument();
    expect(screen.getByText(OVERLINE("Göteborg DC"))).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(1 + 5);
    expect(screen.getByText(/Live · refreshes every 20 s/)).toBeInTheDocument();
    expect(seen).toHaveBeenCalledWith({ warehouse_id: 1, date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/) });
  });

  it("has no write buttons in PR 1", async () => {
    server.use(prepQueueSuccess());
    signInWarehouse();
    renderAt("/warehouse/prep");

    await screen.findByRole("table", { name: "Orders to prepare" });
    expect(screen.queryByRole("button", { name: /start prep|pause|resume|goods ready|mark loaded/i })).toBeNull();
  });

  it("test_US_WH_03_AC1_shows_no_equipment_row", async () => {
    server.use(prepQueueSuccess());
    signInWarehouse();
    renderAt("/warehouse/prep");

    await screen.findByRole("table", { name: "Orders to prepare" });
    expect(screen.queryByText(/equipment/i)).toBeNull();
  });

  it("shows a loading state first, then the queue", async () => {
    server.use(
      http.get(PREP_QUEUE_URL, async () => {
        await delay(50);
        return HttpResponse.json(buildPrepQueueFixture("verified"));
      }),
    );
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect((await screen.findAllByText("Loading…")).length).toBeGreaterThan(0);
    await screen.findByRole("table", { name: "Orders to prepare" });
    expect(screen.queryByText("Loading…")).toBeNull();
  });

  it("shows an empty message when there are no approved orders", async () => {
    server.use(prepQueueSuccess(buildPrepQueueFixture("empty")));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText(/No approved orders to prepare for/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it.each([
    [403, "FORBIDDEN"],
    [404, "NOT_FOUND"],
  ])("shows a permission-denied state, not data, for HTTP %i", async (status, code) => {
    server.use(prepQueueFailure(status, code, "Denied", "corr-denied"));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText("No access to this queue")).toBeInTheDocument();
    expect(screen.getByText("corr-denied")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Capacity today" })).toBeNull();
  });

  it("shows an error with correlation_id and Retry for a 500, then recovers on Retry", async () => {
    server.use(prepQueueFailure(500, "INTERNAL_ERROR", "Boom", "corr-500"));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText("The preparation queue could not be loaded")).toBeInTheDocument();
    expect(screen.getByText("corr-500")).toBeInTheDocument();

    server.use(prepQueueSuccess());
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("table", { name: "Orders to prepare" })).toBeInTheDocument();
    expect(screen.queryByText("The preparation queue could not be loaded")).toBeNull();
  });

  it("ASM-007: capacity without schedule_verified is shown as not verified", async () => {
    server.use(prepQueueSuccess(buildPrepQueueFixture("unverified")));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText("Capacity not verified.")).toBeInTheDocument();
    // The warning does not hide the orders (it records what happened; it is not an approval gate).
    expect(screen.getByRole("table", { name: "Orders to prepare" })).toBeInTheDocument();
  });

  it("test_US_WH_02_AC3_no_official_schedule_shows_no_shifts_and_no_capacity_numbers", async () => {
    server.use(prepQueueSuccess(buildPrepQueueFixture("noSchedule")));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText("No official shift schedule is entered for today.")).toBeInTheDocument();
    expect(screen.queryByText(/min booked ·/)).toBeNull();
  });

  it("stops with a clear message when the warehouse time zone is unavailable, without calling the API", async () => {
    const seen = vi.fn();
    vi.mocked(fetchLocations).mockResolvedValue([GBG_NO_TZ]);
    server.use(prepQueueSuccess(buildPrepQueueFixture("verified"), seen));
    signInWarehouse();
    renderAt("/warehouse/prep");

    expect(await screen.findByText(/The time zone of Göteborg DC is not available/)).toBeInTheDocument();
    expect(seen).not.toHaveBeenCalled();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("asks a multi-warehouse manager to pick a warehouse, then loads the picked one", async () => {
    const seen = vi.fn();
    server.use(prepQueueSuccess(buildPrepQueueFixture("verified"), seen));
    signInAs({ ...userByEmail("wm.got@cfo.demo"), location_ids: [1, 2] });
    renderAt("/warehouse/prep");

    expect(await screen.findByText("Select a warehouse in the sidebar to see its preparation queue.")).toBeInTheDocument();
    expect(seen).not.toHaveBeenCalled();

    await userEvent.setup().selectOptions(await screen.findByRole("combobox", { name: "Warehouse" }), "Stockholm DC");

    expect(await screen.findByRole("table", { name: "Orders to prepare" })).toBeInTheDocument();
    expect(seen).toHaveBeenCalledWith(expect.objectContaining({ warehouse_id: 2 }));
    expect(screen.getByText(OVERLINE("Stockholm DC"))).toBeInTheDocument();
  });

  it.each(["dispatcher@cfo.demo", "sales@cfo.demo"])("%s cannot open the screen and no queue is requested", async (email) => {
    const seen = vi.fn();
    server.use(prepQueueSuccess(buildPrepQueueFixture("verified"), seen));
    signInAs(userByEmail(email));
    renderAt("/warehouse/prep");

    await waitFor(() => expect(currentPath()).not.toBe("/warehouse/prep"));
    expect(document.querySelector('[data-screen="PrepQueue"]')).toBeNull();
    expect(seen).not.toHaveBeenCalled();
  });

  it("opens Edit shifts & staff from the keyboard", async () => {
    server.use(prepQueueSuccess());
    signInWarehouse();
    renderAt("/warehouse/prep");

    const link = await screen.findByRole("link", { name: "Edit shifts & staff" });
    link.focus();
    expect(link).toHaveFocus();
    await userEvent.setup().keyboard("{Enter}");

    await waitFor(() => expect(currentPath()).toBe("/warehouse/attendance"));
  });
});