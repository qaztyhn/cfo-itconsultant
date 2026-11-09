import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FIXTURE_DATE, buildPrepQueueFixture } from "./fixtures";
import { OrdersTable } from "./OrdersTable";

const TZ = "Europe/Stockholm";
const plain = (text: string) => text.replace(/\u202f/g, " ");

function renderTable() {
  const { orders } = buildPrepQueueFixture("verified");
  return render(<OrdersTable orders={orders} timeZone={TZ} queueDate={FIXTURE_DATE} />);
}

function rowOf(orderNo: string): HTMLElement {
  const row = screen.getByText(orderNo).closest("tr");
  if (!row) throw new Error(`Row for ${orderNo} not found`);
  return row;
}

describe("OrdersTable (read-only)", () => {
  it("has column headers with scope=col, a caption and a polite live region", () => {
    const { container } = renderTable();

    const headers = screen.getAllByRole("columnheader");
    expect(headers.map((h) => h.textContent)).toEqual(["Order", "Handling mix", "Work", "Prep window", "Loading", "Status"]);
    headers.forEach((h) => expect(h).toHaveAttribute("scope", "col"));
    expect(screen.getByRole("table", { name: "Orders to prepare" })).toBeInTheDocument();
    expect(container.querySelector('[aria-live="polite"]')).not.toBeNull();
  });

  it("shows one row per order and NO buttons (PR 1 is read-only)", () => {
    renderTable();

    expect(screen.getAllByRole("row")).toHaveLength(1 + 5);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("shows the handling mix, work minutes, prep window and first vehicle of an approved order", () => {
    renderTable();
    const row = within(rowOf("SE-2026-000137"));

    expect(row.getByText(plain("6 lines · 3\u202f340 kg"))).toBeInTheDocument();
    expect(row.getByText("N2 · Boards, sheets & tiles")).toBeInTheDocument();
    expect(row.getByText("N1 · Small items & accessories")).toBeInTheDocument();
    expect(row.getByText("130 min")).toBeInTheDocument();
    expect(row.getByText("06:00 → 08:10")).toBeInTheDocument();
    expect(row.getByText("08:30 · GBG-12-03")).toBeInTheDocument();
    expect(row.getByText("APPROVED")).toBeInTheDocument();
  });

  it("shows a Paused chip only for a paused order, keeping the PREPARING status", () => {
    renderTable();

    const paused = within(rowOf("SE-2026-000152"));
    expect(paused.getByText("PREPARING")).toBeInTheDocument();
    expect(paused.getByText("Paused")).toBeInTheDocument();

    const running = within(rowOf("SE-2026-000141"));
    expect(running.getByText("PREPARING")).toBeInTheDocument();
    expect(running.queryByText("Paused")).not.toBeInTheDocument();
  });

  it("lists every vehicle of a multi-vehicle order and marks only the loaded one", () => {
    renderTable();
    const row = within(rowOf("SE-2026-000158"));

    const first = row.getByText("12:00 · GBG-18-04").closest("li");
    const second = row.getByText("12:15 · GBG-18-05").closest("li");
    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    expect(within(first as HTMLElement).getByText("Loaded")).toBeInTheDocument();
    expect(within(second as HTMLElement).queryByText("Loaded")).not.toBeInTheDocument();
  });

  it("shows weekday and 'after cut-off' for a loading time on the next day", () => {
    renderTable();
    const row = within(rowOf("SE-2026-000163"));

    expect(row.getByText("Fri 06:00 after cut-off · GBG-12-02")).toBeInTheDocument();
  });

  it("shows an explicit placeholder instead of guessing an ISO time without offset", () => {
    const [order] = buildPrepQueueFixture("verified").orders;
    order.loading = [{ ...order.loading[0], at: "2026-11-12T08:30:00" }];
    render(<OrdersTable orders={[order]} timeZone={TZ} queueDate={FIXTURE_DATE} />);

    expect(screen.getByText("Unverified time · GBG-12-03")).toBeInTheDocument();
  });

  it("converts an ISO prep window and loading time to the warehouse's local time", () => {
    const [order] = buildPrepQueueFixture("verified").orders;
    order.prep_window = { start: "2026-11-12T05:00:00Z", end: "2026-11-12T07:10:00Z" };
    order.loading = [{ ...order.loading[0], at: "2026-11-12T07:30:00Z" }];
    render(<OrdersTable orders={[order]} timeZone={TZ} queueDate={FIXTURE_DATE} />);

    expect(screen.getByText("06:00 → 08:10")).toBeInTheDocument();
    expect(screen.getByText("08:30 · GBG-12-03")).toBeInTheDocument();
  });
});