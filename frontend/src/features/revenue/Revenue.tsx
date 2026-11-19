/** US-REV-01 — financial reporting is read-only, location-scoped, and server-authoritative. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { isApiError } from "../../api/client";
import { useAuthStore } from "../../app/store";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { RevenueChart } from "./RevenueChart";
import {
  downloadRevenueCsv, getRevenueDaily, getRevenueLocations, getRevenueOrders, getRevenueOrderStatus,
  getRevenueSummary, money, noCustomerNames, REVENUE_STATUS_GROUPS, revenueQueryKeys, validPeriod,
  type RevenueFilters, type RevenueStatusGroup, type RevenueView,
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
    !fullAccess ? ownerIds[0] : undefined,
  );
  const [selected, setSelected] = useState<number | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<RevenueStatusGroup | null>(null);
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
  const status = useQuery({
    queryKey: revenueQueryKeys.orderStatus(filters),
    queryFn: ({ signal }) => getRevenueOrderStatus(filters, signal),
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
  // For the server's default 30-day market-local window, the *status* response
  // supplies the exact dates used in drill-down. Never infer dates from device time.
  // The selected-location breakdown is intentionally scoped to that location.
  // Keep an unfiltered, server-authorised list for the dropdown; otherwise a
  // user cannot switch directly from one location to another. The query key is
  // identical to the main breakdown when no location filter is active.
  const needsChoiceList = fullAccess || ownerIds.length > 1;
  const choicesFilters: RevenueFilters = {
    view, ...(from ? { from } : {}), ...(to ? { to } : {}),
  };
  const locationChoices = useQuery({
    queryKey: revenueQueryKeys.locations(choicesFilters),
    queryFn: ({ signal }) => getRevenueLocations(choicesFilters, signal),
    enabled: configured && needsChoiceList,
    refetchInterval: REFRESH, refetchIntervalInBackground: false, retry: false,
  });
  const selectableLocations = needsChoiceList
    ? (locationChoices.data?.rows ?? []) : (locations.data?.rows ?? []);
  const selectedFilters = selected === null || !status.data ? null : {
    ...filters, from: from || status.data.period.from, to: to || status.data.period.to, location_id: selected,
  };
  const orders = useQuery({
    queryKey: selectedFilters
      ? revenueQueryKeys.orders(selectedFilters, page, selectedGroup) : ["revenue", "orders", "none"],
    queryFn: ({ signal }) => {
      if (!selectedFilters) throw new Error("Select an authorised location.");
      return getRevenueOrders(selectedFilters, page, signal, selectedGroup);
    },
    enabled: configured && selectedFilters !== null && !status.isError,
    refetchInterval: REFRESH, refetchIntervalInBackground: false, retry: false,
  });
  const failures = [summary.error, status.error, daily.error, locations.error,
    needsChoiceList ? locationChoices.error : null].filter(Boolean);
  const forbidden = failures.some(error => isApiError(error) && error.status === 403);
  const missing = failures.some(error => isApiError(error) && error.status === 404);
  const currencies = [summary.data?.currency, status.data?.currency, daily.data?.currency,
    locations.data?.currency].filter(Boolean);
  const inconsistentCurrency = new Set(currencies).size > 1;
  const mismatchedPeriod = Boolean(status.data && summary.data && (
    status.data.period.from !== summary.data.period.from || status.data.period.to !== summary.data.period.to
  ));
  const loading = summary.isPending || status.isPending || daily.isPending || locations.isPending ||
    (needsChoiceList && locationChoices.isPending);
  const statusCounts = new Map(status.data?.groups.map(group => [group.key, group]) ?? []);
  const totalOrders = status.data?.total.orders ?? 0;
  const groupLabel = REVENUE_STATUS_GROUPS.find(item => item.key === selectedGroup)?.label ?? "";
  const locationName = (locations.data?.rows ?? []).find(item => item.location_id === selected)?.name
    ?? (selected === null ? "" : `#${selected}`);

  function switchView(next: RevenueView) {
    if (!fullAccess || view === next) return;
    setView(next); setLocation(undefined); setSelected(null); setPage(1); setExportError(null);
  }
  function chooseLocation(id?: number) {
    if (!fullAccess && (id === undefined || !ownerIds.includes(id))) return;
    setLocation(id); setSelected(selectedGroup && id !== undefined ? id : null);
    setPage(1); setExportError(null);
  }
  function chooseGroup(key: RevenueStatusGroup) {
    setSelectedGroup(key);
    setSelected(location ?? null);
    setPage(1);
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
      <h1 className="text-h1 font-semibold text-ink">Đơn hàng & doanh thu</h1>
      <p className="text-body text-inkMuted">
        Doanh thu ghi nhận theo ngày giao thực tế. Số đơn lọc theo ngày cam kết giao,
        riêng đơn hủy theo ngày hủy; không gồm đơn chờ duyệt hoặc legacy bị chặn.
      </p>
    </header>
    <p className="rounded-card border border-border bg-surface px-4 py-3 text-body text-inkMuted">
      Figures come from the CFO reporting API for the selected market and period. Revenue covers goods only; delivery and packaging fees are excluded.
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
          onChange={e => {
            setFrom(e.target.value); setSelected(selectedGroup && location !== undefined ? location : null);
            setPage(1);
          }} />
      </label>
      <label className="flex flex-col gap-1 text-caption">To
        <input type="date" className={field} aria-label="To date" value={to}
          onChange={e => {
            setTo(e.target.value); setSelected(selectedGroup && location !== undefined ? location : null);
            setPage(1);
          }} />
      </label>
      <label className="flex flex-col gap-1 text-caption">Location
        <select className={field} aria-label="Location filter" disabled={(!fullAccess && ownerIds.length <= 1) ||
            (needsChoiceList ? locationChoices.isPending || locationChoices.isError : locations.isPending)}
          value={location ?? ""} onChange={e => chooseLocation(e.target.value ? Number(e.target.value) : undefined)}>
          {fullAccess && <option value="">All authorised locations</option>}
          {selectableLocations.filter(row => row.location_id !== null &&
            (fullAccess || ownerIds.includes(row.location_id))).map(row => (
            <option key={row.location_id} value={row.location_id ?? ""}>{row.name}</option>
          ))}
        </select>
      </label>
      <button className={button} type="button" disabled={!periodValid || exporting || forbidden}
        onClick={() => void exportCsv()}>{exporting ? "Exporting…" : "Export CSV"}</button>
    </div>
    {!fullAccess && <p className="text-caption text-inkMuted">Your revenue view and location scope are restricted by ownership. The server independently verifies every request.</p>}
    {!periodValid && <p role="alert" className="text-risk-predictedLate-fg">Select both dates with From ≤ To, for a period of at most 366 days.</p>}
    {exportError !== null && <ErrorState error={exportError} title="CSV export failed" />}
    {configured && forbidden && <p role="alert" className="rounded-card border p-5">You do not have access to revenue.</p>}
    {configured && !forbidden && missing && <p role="alert" className="rounded-card border p-5">Location not found or outside your access scope (404).</p>}
    {configured && !forbidden && !missing && failures.length > 0 &&
      <ErrorState error={failures[0]} onRetry={() => {
        void client.invalidateQueries({ queryKey: ["revenue"] });
      }} />}
    {configured && !failures.length && loading && <LoadingState rows={5} rowClassName="h-[92px]" />}
    {configured && !failures.length && !loading && (inconsistentCurrency || mismatchedPeriod) && (
      <p role="alert">Reporting period or currency mismatch. Financial figures are hidden.</p>
    )}
    {configured && !failures.length && !loading && !inconsistentCurrency && !mismatchedPeriod &&
      summary.data && status.data && daily.data && locations.data && <>
      <p className="text-caption text-inkMuted" aria-live="polite">
        Period {summary.data.period.from} – {summary.data.period.to} · {summary.data.currency} · refresh every 60 seconds while active
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" aria-label="Primary order and revenue metrics">
        {metric("Recognised revenue", money(summary.data.recognised, summary.data.currency),
          "From /revenue/summary · actual delivery date")}
        {metric("Total orders", String(status.data.total.orders),
          "From /revenue/order-status · 5 reportable groups")}
      </div>
      <section aria-label="Order status groups" className="space-y-3">
        <h2 className="text-h2 font-semibold">Đơn theo trạng thái</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {REVENUE_STATUS_GROUPS.map(({ key, label }) => {
            const group = statusCounts.get(key);
            const count = group?.orders ?? 0;
            return <button key={key} type="button"
              className={panel + " text-left hover:bg-rowHover focus-visible:outline focus-visible:outline-2 focus-visible:outline-pine" +
                (selectedGroup === key ? " ring-2 ring-pine" : "")}
              aria-pressed={selectedGroup === key}
              aria-label={`${label}: ${count} orders`} onClick={() => chooseGroup(key)}>
              <span className="block text-caption font-semibold text-inkMuted">{label}</span>
              <span className="mt-2 block font-mono text-h2 text-ink">{count}</span>
              <span className="mt-1 block text-caption text-inkMuted">
                {money(group?.amount ?? "0.00", status.data.currency)} · giá trị đơn
              </span>
            </button>;
          })}
        </div>
        <div className="space-y-2" aria-label="Order status distribution">
          {totalOrders > 0 ? <>
            <div role="img" aria-label="Tỷ trọng theo số đơn của năm nhóm trạng thái"
              className="flex h-4 overflow-hidden rounded-full bg-rowHover">
              {REVENUE_STATUS_GROUPS.map(({ key, label }, index) => {
                const count = statusCounts.get(key)?.orders ?? 0;
                const percent = count / totalOrders * 100;
                return <div key={key} title={`${label}: ${count} (${percent.toFixed(1)}%)`}
                  style={{ width: `${percent}%` }}
                  className={["bg-pine", "bg-deepPine", "bg-ink", "bg-apricot", "bg-stone"][index]} />;
              })}
            </div>
            <p className="text-caption text-inkMuted">
              {REVENUE_STATUS_GROUPS.map(({ key, label }) =>
                `${label}: ${(100 * (statusCounts.get(key)?.orders ?? 0) / totalOrders).toFixed(1)}%`).join(" · ")}
            </p>
          </> : <p role="status" className="text-body text-inkMuted">Không có đơn trong kỳ; tỷ trọng chưa có dữ liệu (0 đơn).</p>}
        </div>
      </section>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Revenue KPI cards">
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
                  onClick={() => { setSelectedGroup(null); setSelected(row.location_id); setPage(1); }}>
                  {row.name}</button>)}</td>
              <td className="p-3">{row.orders_delivered}</td>
              <td className="p-3 font-mono">{money(row.recognised, locations.data.currency)}</td>
              <td className="p-3 font-mono">{money(row.booked_not_delivered, locations.data.currency)}</td>
              <td className="p-3">{row.share_pct === null ? "—" : row.share_pct + "%"}</td>
            </tr>)}</tbody>
          </table></div>}
      </section>
      {selectedGroup !== null && selected === null && <p role="status" className={panel}>
        Đã chọn nhóm <strong>{groupLabel}</strong>. Chọn một địa điểm được phép ở bộ lọc Location
        trước khi tải danh sách đơn. Báo cáo tổng hợp phía trên vẫn giữ nguyên phạm vi đang chọn.
      </p>}
      {selected !== null && <section className={panel} aria-label="Revenue order details">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-h2 font-semibold">
            Orders · {selectedGroup === null ? "all statuses" : groupLabel} · {view}: {locationName}
          </h2>
          <button type="button" className={button} onClick={() => {
            setSelected(null); setSelectedGroup(null); setPage(1);
          }}>Close details</button>
        </div>
        {orders.isPending && <LoadingState rows={3} />}
        {orders.isError && (isApiError(orders.error) && orders.error.status === 403
          ? <p role="alert">You do not have access to revenue.</p>
          : isApiError(orders.error) && orders.error.status === 404
            ? <p role="alert">Location not found or outside your access scope (404).</p>
            : <ErrorState error={orders.error} onRetry={() => void orders.refetch()} />)}
        {orders.isSuccess && orders.data && <>
          {selectedGroup !== null && status.data.location_id === selected && orders.data.total !==
            (statusCounts.get(selectedGroup)?.orders ?? 0) && (
            <p role="alert">Order count differs from the selected group. Refresh the report before relying on this list.</p>
          )}
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
                  {!hideCustomers && <td className="p-3">{"customer_name" in record && typeof record.customer_name === "string" ? record.customer_name : "—"}</td>}
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
