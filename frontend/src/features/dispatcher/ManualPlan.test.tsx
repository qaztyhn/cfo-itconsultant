/** Isolated screen tests: no router or global MSW mocks changed. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ManualPlan } from "./ManualPlan";
import type { ManualOrder } from "./manualPlanModel";
import { useAuthStore } from "../../app/store";
import { userByEmail } from "../../test/utils";

const order: ManualOrder = {
  id: 42, order_no: "SE-0042", status: "PLANNED",
  date_request: { mode: "range", date_from: "2026-11-12", date_to: "2026-11-15" },
  lines: [{ line_no: 1, name: "Cement", qty_base: 800 }, { line_no: 2, name: "Tiles", qty_base: 30 }],
};
let received: { body: unknown; key: string | null }[] = [];
let postStatus = 409;
let postTimeout = false;
let approvedResponse = false;
let orderStatus = 200;
const oldFetch = globalThis.fetch;
beforeEach(() => {
  received = [];
  postStatus = 409;
  postTimeout = false;
  approvedResponse = false;
  orderStatus = 200;
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/orders/42") && init?.method === "GET") {
      return new Response(
        JSON.stringify(orderStatus === 200 ? order : { error: { code: "FORBIDDEN", message: "Denied" } }),
        { status: orderStatus, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url.endsWith("/orders/42/manual-plan") && init?.method === "POST") {
      received.push({ body: JSON.parse(String(init.body)), key: new Headers(init.headers).get("Idempotency-Key") });
      if (postTimeout) throw new TypeError("Network request timed out");
      return new Response(
        JSON.stringify(postStatus === 200
          ? approvedResponse
            ? { plan: { id: 100, status: "manual" }, order: { status: "APPROVED" } }
            : { plan: { id: 100, status: "proposed" }, order: { status: "PLANNED" } }
          : { error: { code: "RESOURCE_CONFLICT", message: "Truck busy", correlation_id: "cid-42", details: { conflict: "vehicle" } } }),
        { status: postStatus, headers: { "Content-Type": "application/json" } },
      );
    }
    throw new Error("Unexpected endpoint: " + url);
  });
});
afterEach(() => {
  globalThis.fetch = oldFetch;
  useAuthStore.getState().clearAuth();
  vi.restoreAllMocks();
});
function signIn(role: "dispatcher" | "sales") {
  const user = userByEmail(role === "dispatcher" ? "dispatcher@cfo.demo" : "sales@cfo.demo");
  useAuthStore.getState().setAuth({
    access_token: "test-token", token_type: "bearer", expires_in: 28800, user,
  }, "test@cfo.demo");
}
function mount() {
  const query = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={query}>
      <MemoryRouter initialEntries={["/manual/42"]}>
        <Routes><Route path="/manual/:orderId" element={<ManualPlan />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
function change(name: string, value: string) {
  fireEvent.change(screen.getByRole("textbox", { name }), { target: { value } });
}
async function fillReady() {
  await screen.findByRole("heading", { name: /Manual plan/ });
  change("Warehouse ID", "3");
  fireEvent.change(screen.getByLabelText("Proposed delivery date"), { target: { value: "2026-11-13" } });
  change("Goods ready", "2026-11-12T11:20:00+01:00");
  change("Vehicle 1 ID", "15");
  change("Vehicle 1 driver ID", "71");
  change("Vehicle 1 departure", "2026-11-13T05:10:00+01:00");
  change("Vehicle 1 ETA", "2026-11-13T07:00:00+01:00");
  fireEvent.change(screen.getByLabelText("Vehicle 1 line 1 quantity"), { target: { value: "800" } });
  fireEvent.change(screen.getByLabelText("Vehicle 1 line 2 quantity"), { target: { value: "30" } });
  change("Manual reason code", "special_vehicle");
  change("Auditable explanation", "Requires review");
}

describe("US-APR-02 — manual planning UI", () => {
  it("blocks non-dispatchers before fetching any order resource", () => {
    signIn("sales");
    mount();
    expect(screen.getByText(/Only a Dispatcher/)).toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
  it("shows loading and server permission denial", async () => {
    signIn("dispatcher");
    orderStatus = 403;
    mount();
    expect(await screen.findByText("You don't have permission to view this.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
  it("disables preview for incomplete and overallocated quantities", async () => {
    signIn("dispatcher"); mount();
    await fillReady();
    fireEvent.change(screen.getByLabelText("Vehicle 1 line 1 quantity"), { target: { value: "801" } });
    expect(screen.getByText(/Overallocated — reduce quantity/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview proposal" })).toBeDisabled();
    expect(received).toHaveLength(0);
  });
  it("supports two vehicles, five unverified gates, conflict explanation and idempotent retry", async () => {
    signIn("dispatcher"); mount();
    await fillReady();
    fireEvent.click(screen.getByRole("button", { name: "Add vehicle" }));
    fireEvent.change(screen.getByLabelText("Vehicle 1 line 1 quantity"), { target: { value: "400" } });
    fireEvent.change(screen.getByLabelText("Vehicle 1 line 2 quantity"), { target: { value: "10" } });
    change("Vehicle 2 ID", "16");
    change("Vehicle 2 driver ID", "72");
    change("Vehicle 2 departure", "2026-11-13T05:20:00+01:00");
    change("Vehicle 2 ETA", "2026-11-13T07:15:00+01:00");
    fireEvent.change(screen.getByLabelText("Vehicle 2 line 1 quantity"), { target: { value: "400" } });
    fireEvent.change(screen.getByLabelText("Vehicle 2 line 2 quantity"), { target: { value: "20" } });
    expect(screen.getByText("800 / 800 base units")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Preview proposal" }));
    const preview = screen.getByRole("region", { name: "Manual plan preview" });
    expect(within(preview).getAllByText(/Unverified/)).toHaveLength(5);
    expect(screen.getByRole("button", { name: /Submit manual plan/ })).toBeDisabled();
    fireEvent.click(within(preview).getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /Submit manual plan/ }));
    await waitFor(() => expect(received).toHaveLength(1));
    expect(received[0].body).toMatchObject({
      warehouse_id: 3,
      vehicles: [
        { vehicle_id: 15, load_lines: [{ line_no: 1, qty_base: 400 }, { line_no: 2, qty_base: 10 }] },
        { vehicle_id: 16, load_lines: [{ line_no: 1, qty_base: 400 }, { line_no: 2, qty_base: 20 }] },
      ],
    });
    expect(received[0].key).toBeTruthy();
    expect(await screen.findByText(/Truck busy/)).toBeInTheDocument();
    expect(screen.getByText(/RESOURCE_CONFLICT/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry the same request" }));
    await waitFor(() => expect(received).toHaveLength(2));
    expect(received[1].key).toBe(received[0].key);
  });
  it("does not claim approval from a 200 response without approved plan confirmation", async () => {
    postStatus = 200;
    signIn("dispatcher"); mount();
    await fillReady();
    fireEvent.click(screen.getByRole("button", { name: "Preview proposal" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /Submit manual plan/ }));
    expect(await screen.findByText(/did not confirm approval/)).toBeInTheDocument();
    expect(screen.queryByText(/Server confirmed manual plan/)).not.toBeInTheDocument();
  });
  it("does not treat CFO APPROVED without a WMS ACK as reserved stock", async () => {
    postStatus = 200;
    approvedResponse = true;
    signIn("dispatcher"); mount();
    await fillReady();
    fireEvent.click(screen.getByRole("button", { name: "Preview proposal" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /Submit manual plan/ }));
    expect(await screen.findByText(/WMS reservation remains unverified/)).toBeInTheDocument();
    expect(screen.queryByText(/Server confirmed manual plan/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Submit manual plan/ })).toBeDisabled();
  });
  it("keeps the same idempotency key after a request timeout", async () => {
    postTimeout = true;
    signIn("dispatcher"); mount();
    await fillReady();
    fireEvent.click(screen.getByRole("button", { name: "Preview proposal" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /Submit manual plan/ }));
    await waitFor(() => expect(received).toHaveLength(1));
    expect(await screen.findByRole("button", { name: "Retry the same request" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry the same request" }));
    await waitFor(() => expect(received).toHaveLength(2));
    expect(received[1].key).toBe(received[0].key);
  });
  it("does not submit twice when the approval button is clicked twice", async () => {
    postStatus = 200;
    approvedResponse = true;
    signIn("dispatcher"); mount();
    await fillReady();
    fireEvent.click(screen.getByRole("button", { name: "Preview proposal" }));
    fireEvent.click(screen.getByRole("checkbox"));
    const submit = screen.getByRole("button", { name: /Submit manual plan/ });
    fireEvent.click(submit);
    fireEvent.click(submit);
    await screen.findByText(/WMS reservation remains unverified/);
    expect(received).toHaveLength(1);
  });
  it("keeps a single-column mobile-safe layout and exposes meaningful labels", async () => {
    signIn("dispatcher"); mount();
    await screen.findByRole("heading", { name: /Manual plan/ });
    expect(screen.getByRole("region", { name: "Warehouse and date" }).className).toContain("grid-cols-1");
    expect(screen.getByRole("region", { name: "Vehicle allocations" }).className).toContain("space-y-4");
    expect(screen.getByRole("region", { name: "Allocation totals" })).toBeInTheDocument();
  });
});
