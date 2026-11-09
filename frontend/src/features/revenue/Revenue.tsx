/** US-REV-01 — financial reporting is read-only, location-scoped, and server-authoritative. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { isApiError } from "../../api/client";
import { useAuthStore } from "../../app/store";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { RevenueChart } from "./RevenueChart";
import {
  downloadRevenueCsv, getRevenueDaily, getRevenueLocations, getRevenueOrders, getRevenueSummary,
  money, noCustomerNames, revenueQueryKeys, validPeriod,
  type RevenueFilters, type RevenueView,
} from "./revenueApi";

const field = "min-h-11 rounded-control border border-border bg-surface px-3 py-2 text-body text-ink";
const button = "min-h-11 rounded-control border border-border bg-surface px-4 py-2 text-body font-semibold text-ink disabled:opacity-50";
const panel = "rounded-card border border-border bg-surface p-4 md:p-6";
const REFRESH = 60_000;

function metric(label: string, value: string, suffix?: string) {
  return <div key={label} className="rounded-card border border-border bg-surface p-5">
    <p className="text-caption font-semibold text-inkMuted">{label}</p>
    <p className="mt-3 break-words font-mono text-h2 text-ink" title={value}>{value}</p>
    {suffix && <p className="mt-2 text-caption text-inkMuted">{suffix}</p>}
  </div>;
}
function RevenueBody({ fullAccess, ownerIds, ownerView, hideCustomers }: {
  fullAccess: boolean; ownerIds: number[]; ownerView: RevenueView | null; hideCustomers: boolean;
}) {
  const [view, setView] = useState<RevenueView>(ownerView ?? "store");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [location, setLocation] = useState<number | undefined>(
    !fullAccess && ownerIds.length === 1 ? ownerIds[0] : undefined,
  );
  const [selected, setSelected] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [exportError, setExportError] = useState<unknown>(null);
  const [exporting, setExporting] = useState(false);
  const client = useQueryClient();
  const periodValid = validPeriod(from, to);
  const filters: RevenueFilters = { view, ...(from ? { from } : {}), ...(to ? { to } : {}),
    ...(location !== undefined ? { location_id: location } : {}) };
  const configured = periodValid;
  const summary = useQuery({
    queryKey: revenueQueryKeys.summary(filters), queryFn: ({ signal }) => getRevenueSummary(filters, signal),
    enabled: configured, refetchInterval: REFRESH, refetchIntervalInBackground: false, retry: false,
  });
  const daily = useQuery({
    queryKey: revenueQueryKeys.daily(filters), queryFn: ({ signal }) => getRevenueDaily(filters, signal),
    enabled: configured, refetchInterval: REFRESH, refetchIntervalInBackground: false, retry: false,
  });
  const locations = useQuery({
    queryKey: revenueQueryKeys.locations(filters), queryFn: ({ signal }) => getRevenueLocations(filters, signal),
    enabled: configured, refetchInterval: REFRESH, refetchIntervalInBackground: false, retry: false,
  });
  const selectedFilters = selected === null ? null : { ...filters, location_id: selected };
  const orders = useQuery({
    queryKey: selectedFilters ? revenueQueryKeys.orders(selectedFilters, page) : ["revenue", "orders", "none"],
    queryFn: ({ signal }) => {
      if (!selectedFilters) throw new Error("Select a location.");
      return getRevenueOrders(selectedFilters, page, signal);
    },
    enabled: configured && selected !== null,
    refetchInterval: REFRESH, refetchIntervalInBackground: false, retry: false,
  });
  const failures = [summary.error, daily.error, locations.error].filter(Boolean);
  const forbidden = failures.some(error => isApiError(error) && error.status === 403);
  const missing = failures.some(error => isApiError(error) && error.status === 404);
  const currencies = [summary.data?.currency, daily.data?.currency, locations.data?.currency].filter(Boolean);
  const inconsistentCurrency = new Set(currencies).size > 1;
  const loading = summary.isPending || daily.isPending || locations.isPending;

  function switchView(next: RevenueView) {
    if (!fullAccess || view === next) return;
    setView(next); setLocation(undefined); setSelected(null); setPage(1); setExportError(null);
  }
  function chooseLocation(id?: number) {
    setLocation(id); setSelected(null); setPage(1); setExportError(null);
  }
  async function exportCsv() {
    if (exporting || !periodValid) return;
    setExporting(true); setExportError(null);
    try {
      const blob = await downloadRevenueCsv(filters);
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "revenue.csv";
        document.body.append(anchor);
        anchor.click();
        anchor.remove();
      } finally { URL.revokeObjectURL(url); }
    } catch (error) { setExportError(error); }
    finally { setExporting(false); }
  }
  const empty = summary.data?.orders_delivered === 0;
  return <div className="space-y-6">
    <header className="space-y-2">
      <p className="text-overline font-semibold text-pine">REVENUE · {fullAccess ? "MARKET REPORT" : "MY LOCATION"}</p>
      <h1 className="text-h1 font-semibold text-ink">Revenue</h1>
      <p className="text-body text-inkMuted">Recognised when an order is delivered. Failed and cancelled orders are excluded.</p>
    </header>
    <p className="rounded-card border border-border bg-surface px-4 py-3 text-body text-inkMuted">
      Illustrative values from seeded orders. Revenue = unit price × quantity of goods; delivery and packaging fees are not included.
    </p>
    <div className="flex flex-col gap-4 rounded-card border border-border bg-surface p-4 lg:flex-row lg:flex-wrap lg:items-end">
      <fieldset className="flex flex-wrap gap-2" aria-label="Revenue view">
        <legend className="mb-1 text-caption font-semibold">Breakdown</legend>
        {(["store", "warehouse"] as const).map(option => (
          <button key={option} type="button" className={button + (view === option ? " ring-2 ring-pine" : "")}
            aria-pressed={view === option} disabled={!fullAccess} onClick={() => switchView(option)}>
            By {option}
          </button>
        ))}
      </fieldset>
      <label className="flex flex-col gap-1 text-caption">From
        <input type="date" className={field} aria-label="From date" value={from}
          onChange={e => { setFrom(e.target.value); setSelected(null); }} />
      </label>
      <label className="flex flex-col gap-1 text-caption">To
        <input type="date" className={field} aria-label="To date" value={to}
          onChange={e => { setTo(e.target.value); setSelected(null); }} />
      </label>
      <label className="flex flex-col gap-1 text-caption">Location
        <select className={field} aria-label="Location filter" disabled={!fullAccess || locations.isPending}
          value={location ?? ""} onChange={e => chooseLocation(e.target.value ? Number(e.target.value) : undefined)}>
          <option value="">All authorised locations</option>
          {(locations.data?.rows ?? []).filter(row => row.location_id !== null).map(row => (
            <option key={row.location_id} value={row.location_id ?? ""}>{row.name}</option>
          ))}
        </select>
      </label>
      <button className={button} type="button" disabled={!periodValid || exporting || forbidden}
        onClick={() => void exportCsv()}>{exporting ? "Exporting…" : "Export CSV"}</button>
    </div>
    {!fullAccess && <p className="text-caption text-inkMuted">Your revenue view and location scope are restricted by ownership. The server independently verifies every request.</p>}
    {!periodValid && <p role="alert" className="text-risk-predictedLate-fg">Select both dates with From ≤ To, for a period of at most 366 days.</p>}
    {exportError && <ErrorState error={exportError} title="CSV export failed" />}
    {configured && forbidden && <p role="alert" className="rounded-card border p-5">You do not have access to revenue.</p>}
    {configured && !forbidden && missing && <p role="alert" className="rounded-card border p-5">Location not found or outside your access scope (404).</p>}
    {configured && !forbidden && !missing && failures.length > 0 &&
      <ErrorState error={failures[0]} onRetry={() => {
        void client.invalidateQueries({ queryKey: ["revenue"] });
      }} />}
    {configured && !failures.length && loading && <LoadingState rows={5} rowClassName="h-[92px]" />}
    {configured && !failures.length && !loading && inconsistentCurrency && (
      <p role="alert">Mixed or inconsistent currencies were returned. Financial figures are hidden.</p>
    )}
    {configured && !failures.length && !loading && !inconsistentCurrency && summary.data && daily.data && locations.data && <>
      <p className="text-caption text-inkMuted" aria-live="polite">
        Period {summary.data.period.from} – {summary.data.period.to} · {summary.data.currency} · refresh every 60 seconds while active
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5" aria-label="Revenue KPI cards">
        {metric("Recognised revenue", money(summary.data.recognised, summary.data.currency))}
        {metric("Booked not yet delivered", money(summary.data.booked_not_delivered, summary.data.currency))}
        {metric("Orders delivered", String(summary.data.orders_delivered))}
        {metric("Average order value", money(summary.data.avg_order_value, summary.data.currency))}
        {fullAccess && metric("Share of market", summary.data.share_of_market_pct === null ? "—" : summary.data.share_of_market_pct + "%")}
      </div>
      {empty && <p role="status" className="text-body text-inkMuted">No delivered orders in this period. Booked orders may still be shown.</p>}
      <section className={panel} aria-label="Revenue chart">
        <h2 className="mb-4 text-h2 font-semibold">Daily revenue</h2>
        <RevenueChart data={daily.data} />
      </section>
      <section className={panel} aria-label="Location breakdown">
        <h2 className="mb-4 text-h2 font-semibold">By {view} · locations</h2>
        {locations.data.rows.length === 0 ? <p role="status">No locations in this period.</p> :
          <div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left text-body">
            <thead><tr className="border-b border-border text-caption text-inkMuted">
              <th className="p-3">Location</th><th className="p-3">Delivered</th>
              <th className="p-3">Recognised</th><th className="p-3">Booked</th><th className="p-3">Share</th>
            </tr></thead><tbody>{locations.data.rows.map((row, index) => <tr className="border-b border-border"
              key={row.location_id ?? "unassigned-" + index}>
              <td className="p-3">{row.location_id === null ? row.name : (
                <button type="button" className="font-semibold text-pine underline underline-offset-2"
                  onClick={() => { setSelected(row.location_id); setPage(1); }}>
                  {row.name}</button>)}</td>
              <td className="p-3">{row.orders_delivered}</td>
              <td className="p-3 font-mono">{money(row.recognised, locations.data.currency)}</td>
              <td className="p-3 font-mono">{money(row.booked_not_delivered, locations.data.currency)}</td>
              <td className="p-3">{row.share_pct === null ? "—" : row.share_pct + "%"}</td>
            </tr>)}</tbody>
          </table></div>}
      </section>
      {selected !== null && <section className={panel} aria-label="Revenue order details">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-h2 font-semibold">Orders · selected {view} #{selected}</h2>
          <button type="button" className={button} onClick={() => setSelected(null)}>Close details</button>
        </div>
        {orders.isPending && <LoadingState rows={3} />}
        {orders.isError && <ErrorState error={orders.error} onRetry={() => void orders.refetch()} />}
        {orders.data && <>
          {orders.data.items.length === 0 ? <p role="status">No orders at this location.</p> :
            <div className="overflow-x-auto"><table className="w-full min-w-[480px] text-left text-body">
              <thead><tr className="border-b border-border"><th className="p-3">Order</th>
                <th className="p-3">Delivered at</th><th className="p-3">Amount</th>
                <th className="p-3">Status</th>{!hideCustomers && <th className="p-3">Customer</th>}
              </tr></thead>
              <tbody>{(hideCustomers ? noCustomerNames(orders.data.items) : orders.data.items).map(record =>
                <tr key={record.order_no} className="border-b border-border">
                  <td className="p-3">{record.order_no}</td>
                  <td className="p-3">{record.delivered_at ? new Date(record.delivered_at).toLocaleString() : "—"}</td>
                  <td className="p-3 font-mono">{money(record.amount, record.currency)}</td>
                  <td className="p-3">{record.status}</td>
                  {!hideCustomers && <td className="p-3">{"customer_name" in record ? record.customer_name ?? "—" : "—"}</td>}
                </tr>)}</tbody></table></div>}
          <div className="mt-4 flex items-center gap-4">
            <button className={button} type="button" disabled={page <= 1} onClick={() => setPage(n => n - 1)}>Previous</button>
            <span>Page {page} / {Math.max(1, Math.ceil(orders.data.total / orders.data.page_size))}</span>
            <button className={button} type="button"
              disabled={page * orders.data.page_size >= orders.data.total}
              onClick={() => setPage(n => n + 1)}>Next</button>
          </div>
        </>}
      </section>}
    </>}
  </div>;
}

export function Revenue() {
  const user = useAuthStore(s => s.user);
  const fullAccess = Boolean(user?.roles.includes("admin") || user?.kpi_scopes.includes("revenue_all"));
  const ownerIds = user?.owned_location_ids ?? [];
  const ownerView: RevenueView | null = user?.roles.includes("warehouse") && !user.roles.includes("sales")
    ? "warehouse" : user?.roles.includes("sales") && !user.roles.includes("warehouse") ? "store" : null;
  // Mixed-role owners have no approved location-type map; fail closed instead of guessing.
  const mayView = fullAccess || (ownerIds.length > 0 && ownerView !== null);
  return <section data-screen="Revenue" className="space-y-6">
    {!mayView ? <p role="alert">You do not have access to revenue.</p> :
      <RevenueBody key={user?.id} fullAccess={fullAccess} ownerIds={ownerIds}
        ownerView={ownerView} hideCustomers={Boolean(user?.kpi_scopes.includes("revenue_all") && !user.roles.includes("admin"))} />}
  </section>;
}
