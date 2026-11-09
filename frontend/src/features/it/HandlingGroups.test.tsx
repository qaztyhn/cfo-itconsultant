import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../../api/config";
import { useAuthStore } from "../../app/store";
import { signInAs, userByEmail } from "../../test/utils";
import { HandlingGroups } from "./HandlingGroups";

const groups = [
  { id: 1, code: "N1", name: "Small items & accessories", prep_unit: "line", fixed_hours: "0", labour_hours_per_unit: "0.05", min_crew: 1, vehicle_requirement: [] },
  { id: 2, code: "N2", name: "Boards, sheets & tiles", prep_unit: "pallet", fixed_hours: "0.25", labour_hours_per_unit: "0.40", min_crew: 1, vehicle_requirement: [] },
  { id: 3, code: "N3", name: "Bagged cement & mortar", prep_unit: "pallet", fixed_hours: "0.25", labour_hours_per_unit: "0.15", min_crew: 1, vehicle_requirement: [] },
  { id: 4, code: "N4", name: "Bulk materials", prep_unit: "m3", fixed_hours: "0.50", labour_hours_per_unit: "0.10", min_crew: 1, vehicle_requirement: ["dump"] },
  { id: 5, code: "N5", name: "Long goods", prep_unit: "bundle", fixed_hours: "0.50", labour_hours_per_unit: "0.50", min_crew: 2, vehicle_requirement: [] },
  { id: 6, code: "N6", name: "Large & fragile items", prep_unit: "package", fixed_hours: "0.25", labour_hours_per_unit: "0.60", min_crew: 2, vehicle_requirement: [] },
];
const flags = [{ code: "FRAGILE", name: "Fragile", multiplier: "1.25" }];
const rules = [{ id: 10, priority: 1, category_like: "Cement%", min_weight_kg: null, max_weight_kg: null, handling_group_id: 3, flags: [] }];
let groupResponse: unknown = groups;
let flagResponse: unknown = flags;
let ruleResponse: unknown = rules;
let groupStatus = 200;
let requests = 0;
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><HandlingGroups /></QueryClientProvider>);
}

beforeEach(() => {
  signInAs(userByEmail("admin@cfo.demo"));
  groupResponse = groups; flagResponse = flags; ruleResponse = rules; groupStatus = 200; requests = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const path = String(input).replace(API_BASE_URL, "");
    if (path === "/handling-groups") { requests += 1; return Promise.resolve(response(groupResponse, groupStatus)); }
    if (path === "/special-flags") return Promise.resolve(response(flagResponse));
    if (path === "/handling-group-rules") return Promise.resolve(response(ruleResponse));
    throw new Error(`Unexpected request ${path}`);
  }));
});
afterEach(() => { vi.unstubAllGlobals(); useAuthStore.getState().clearAuth(); });

describe("HandlingGroups", () => {
  it("test_US_PRD_04_AC3_renders_server_norms_shared_across_warehouses", async () => {
    renderPage();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(await screen.findByText("N6", { selector: "span" })).toBeInTheDocument();
    expect(document.querySelectorAll("article")).toHaveLength(6);
    const n3 = screen.getByText("N3", { selector: "span" }).closest("article");
    expect(n3).not.toBeNull();
    expect(within(n3!).getByText("0.15 h")).toBeInTheDocument();
    expect(within(n3!).getByText("≈ 9 min")).toBeInTheDocument();
    expect(screen.getByText("One norm set for all warehouses.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit|save|approve/i })).not.toBeInTheDocument();
  });

  it("test_US_PRD_04_AC2_shows_server_rules_and_flags", async () => {
    renderPage();
    expect(await screen.findByText("FRAGILE · ×1.25")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("tab", { name: "Group rules" }));
    expect(screen.getByText("Cement% → N3")).toBeInTheDocument();
    expect(screen.getByText(/Priority 1/)).toBeInTheDocument();
  });

  it("shows empty configuration without fixture data", async () => {
    groupResponse = []; flagResponse = []; ruleResponse = [];
    renderPage();
    expect(await screen.findByText("No handling groups are configured.")).toBeInTheDocument();
    expect(screen.getByText("No special handling flags are configured.")).toBeInTheDocument();
  });

  it("shows API error reference and retries", async () => {
    groupResponse = { error: { code: "UNAVAILABLE", message: "Try again", correlation_id: "ref-12" } }; groupStatus = 503;
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("ref-12");
    groupResponse = groups; groupStatus = 200;
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("N6", { selector: "span" })).toBeInTheDocument();
  });

  it("does not request configuration for a non-admin", async () => {
    signInAs(userByEmail("dispatcher@cfo.demo"));
    renderPage();
    expect(screen.getByRole("alert")).toHaveTextContent("permission");
    await waitFor(() => expect(requests).toBe(0));
  });

  it("shows server permission denial without configuration", async () => {
    groupResponse = { error: { code: "FORBIDDEN", message: "Forbidden" } }; groupStatus = 403;
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("permission");
    expect(screen.queryByText("N3", { selector: "span" })).not.toBeInTheDocument();
  });
});
