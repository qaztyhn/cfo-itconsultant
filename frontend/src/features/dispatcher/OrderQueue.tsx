/**
 * 5.1 Order queue — GET /orders, GET /orders/counts (docs/06 mục 5.4; docs/03 mục 5.1, 7).
 * Lọc/sắp xếp/phân trang do SERVER; mặc định FIFO submitted_at, id (hiển thị, không ép thứ tự thực thi).
 * Đơn legacy BLOCKED_UNMAPPED_SKU không thuộc backlog CFO. Không suy diễn routing, ngày khả thi hay kết quả duyệt.
 * Owner: Dev 3 (luồng C).
 */
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { isApiError } from "../../api/client";
import { fetchIntegrationOverview, summariseFreshness } from "../../api/integration";
import { PATHS } from "../../app/access";
import { useAuthStore } from "../../app/store";
import { DataFreshness } from "../../components/DataFreshness";
import { FilterChips } from "../../components/FilterChips";
import { PageHeader } from "../../components/PageHeader";
import { RiskChip } from "../../components/RiskChip";
import { StatusChip, type OrderStatus } from "../../components/StatusChip";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { formatDayTime, formatTime } from "../../lib/planFormat";
import { planningNow } from "../../lib/useHoldExpired";
import { PAGE_SIZES, fetchOrderQueue, fetchQueueCounts, type QueueSort } from "./orderQueue/api";
import type { QueueOrder } from "./orderQueue/model";
import {
  BUCKETS, RISK_OPTIONS, SORT_OPTIONS, STATUS_OPTIONS, isDateRangeInvalid, parseQueueState, toQueueQuery, updateParams,
  type Bucket,
} from "./orderQueue/queueState";
import { OrderAction } from "./orderQueue/OrderAction";
import { customerSite, requestedLabel, warehouseLabel } from "./orderQueue/rowView";

const POLL_MS = 20_000;
const BUCKET_LABELS: Record<Bucket, string> = {
  active: "Open", needs_plan: "Needs plan", awaiting_approval: "Awaiting approval",
  no_feasible_date: "No feasible date", in_execution: "In execution",
};
const SORT_LABELS: Record<QueueSort, string> = {
  submitted_at: "Submitted", date_to: "Requested date", promise_end: "Promise end",
  committed_date: "Committed date", order_no: "Order no.", status: "Status",
};

function forbidden(error: unknown): boolean {
  return isApiError(error) && (error.status === 403 || error.code === "FORBIDDEN");
}
const pollInterval = (query: { state: { error: unknown } }) => (forbidden(query.state.error) ? false : POLL_MS);

const control = "rounded-control border border-border bg-surface p-2 text-sm font-normal text-ink";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="flex min-w-0 flex-col gap-1 text-xs font-semibold text-ink">{label}{children}</label>;
}

function Indicators({ order }: { order: QueueOrder }) {
  return (
    <>
      <RiskChip color={order.riskColor ?? undefined} />
      {order.blockReason && (
        <span className="rounded-full bg-risk-lateRow px-2 py-0.5 font-mono text-overline text-risk-predictedLate-fg">
          Blocked: {order.blockReason}
        </span>
      )}
    </>
  );
}

function OrderTable({ items }: { items: QueueOrder[] }) {
  return (
    <div className="hidden overflow-x-auto rounded-card border border-border bg-surface md:block">
      <table className="w-full min-w-[860px] text-left text-sm">
        <caption className="sr-only">Orders, oldest submitted first unless another sort is chosen</caption>
        <thead className="bg-stone text-xs uppercase text-inkMuted">
          <tr>
            {["Order", "Customer · Site", "Requested", "Committed", "Risk", "Status", "Open"].map(label => (
              <th key={label} scope="col" className="px-4 py-3">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map(order => {
            const who = customerSite(order);
            return (
              <tr key={order.id} className={order.riskColor === "red" ? "bg-risk-lateRow" : ""}>
                <td className="px-4 py-3">
                  <span className="font-mono font-semibold text-ink">{order.orderNo}</span>
                  <span className="block text-xs text-inkMuted">{warehouseLabel(order)}</span>
                  <span className="block text-xs text-inkMuted">Submitted {formatTime(order.submittedAt)}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="font-semibold text-ink">{who.customer}</span>
                  <span className="block text-xs text-inkMuted">{who.site}</span>
                </td>
                <td className="px-4 py-3 font-mono text-xs">{requestedLabel(order)}</td>
                <td className="px-4 py-3 font-mono text-xs">
                  {order.committedDate ?? "—"}
                  {order.promiseEnd && <span className="block text-inkMuted">until {formatDayTime(order.promiseEnd)}</span>}
                </td>
                <td className="px-4 py-3"><div className="flex flex-col items-start gap-1"><Indicators order={order} /></div></td>
                <td className="px-4 py-3"><StatusChip status={order.status as OrderStatus} /></td>
                <td className="px-4 py-3"><OrderAction order={order} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function OrderCards({ items }: { items: QueueOrder[] }) {
  return (
    <ul className="flex flex-col gap-3 md:hidden" aria-label="Orders">
      {items.map(order => {
        const who = customerSite(order);
        return (
          <li key={order.id} className={`rounded-card border border-border p-4 ${order.riskColor === "red" ? "bg-risk-lateRow" : "bg-surface"}`}>
            <div className="flex items-start justify-between gap-2">
              <span className="font-mono font-semibold text-ink">{order.orderNo}</span>
              <StatusChip status={order.status as OrderStatus} />
            </div>
            <p className="mt-2 font-semibold text-ink">{who.customer}</p>
            <p className="text-xs text-inkMuted">{who.site}</p>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div><dt className="text-inkMuted">Warehouse</dt><dd className="font-mono">{warehouseLabel(order)}</dd></div>
              <div><dt className="text-inkMuted">Requested</dt><dd className="font-mono">{requestedLabel(order)}</dd></div>
              <div><dt className="text-inkMuted">Committed</dt><dd className="font-mono">{order.committedDate ?? "—"}</dd></div>
              <div><dt className="text-inkMuted">Submitted</dt><dd className="font-mono">{formatTime(order.submittedAt)}</dd></div>
            </dl>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2"><Indicators order={order} /></div>
              <OrderAction order={order} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function OrderQueue({ reviewOnly = false }: { reviewOnly?: boolean }) {
  const userId = useAuthStore(s => s.user?.id ?? null);
  const [params, setParams] = useSearchParams();
  const parsed = parseQueueState(params);
  const state = reviewOnly ? { ...parsed, status: "PLANNED" } : parsed;
  const title = reviewOnly ? "Plan review" : "Order queue";
  // `q` chỉ nằm trong state component: không đưa số điện thoại/tên khách lên URL hay lịch sử trình duyệt.
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== search) {
        setSearch(searchInput);
        setParams(prev => updateParams(prev, {}), { replace: true }); // về trang 1
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput, search, setParams]);

  const query = toQueueQuery(state, search);
  const list = useQuery({
    queryKey: ["dispatcher-order-queue", "list", userId, query],
    queryFn: ({ signal }) => fetchOrderQueue(query, signal),
    retry: false, refetchInterval: pollInterval, refetchIntervalInBackground: false,
  });
  const countsQuery = useQuery({
    queryKey: ["dispatcher-order-queue", "counts", userId],
    queryFn: ({ signal }) => fetchQueueCounts(signal),
    retry: false, refetchInterval: pollInterval, refetchIntervalInBackground: false,
  });
  const overview = useQuery({
    queryKey: ["dispatcher-order-queue", "freshness", userId],
    queryFn: ({ signal }) => fetchIntegrationOverview(signal),
    retry: false, refetchInterval: query => forbidden(query.state.error) ? false : 60_000,
    refetchIntervalInBackground: false,
  });

  const counts = countsQuery.data ?? null;
  const freshness = overview.data ? summariseFreshness(overview.data, planningNow()) : null;
  const change = (changes: Record<string, string | null>) => setParams(prev => updateParams(prev, changes), { replace: true });
  const filtered = params.size > 0 || search !== "";
  const refreshing = list.isFetching || countsQuery.isFetching || overview.isFetching;
  const refresh = () => { void list.refetch(); void countsQuery.refetch(); void overview.refetch(); };
  const clear = () => { setSearchInput(""); setSearch(""); setParams(new URLSearchParams(), { replace: true }); };

  if (forbidden(list.error) || forbidden(countsQuery.error)) {
    return (
      <section data-screen="OrderQueue" className="flex flex-col gap-5">
        <PageHeader overline="Dispatcher" title={title} />
        <div role="alert" className="rounded-card border border-border bg-surface p-6">
          <h2 className="text-h3 text-ink">You do not have access to the order queue</h2>
          <p className="mt-2 text-body text-inkMuted">Access is decided by the server for your role and market. No orders were loaded.</p>
        </div>
      </section>
    );
  }

  const page = list.data;
  const totalPages = page && page.total !== null ? Math.max(1, Math.ceil(page.total / state.pageSize)) : 1;
  const first = page && page.total ? (state.page - 1) * state.pageSize + 1 : 0;
  const last = page ? (state.page - 1) * state.pageSize + page.items.length : 0;

  return (
    <section data-screen="OrderQueue" className="flex flex-col gap-5">
      <PageHeader
        overline="Dispatcher"
        title={title}
        description={reviewOnly ? "Orders awaiting plan approval." : state.sort === null
          ? "Oldest submitted first. This is display order only; later orders may still be planned earlier if they do not take committed resources."
          : `Sorted by ${SORT_LABELS[state.sort]} (${state.desc ? "descending" : "ascending"}).`}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <nav aria-label="Dispatcher areas" className="flex flex-wrap gap-2">
          {[
            reviewOnly ? { to: PATHS.dispatcherOrders, label: "Order queue", count: undefined }
              : { to: PATHS.dispatcherPlanReview, label: "Plan review", count: counts?.awaitingApproval },
            { to: PATHS.dispatcherExceptions, label: "Exceptions", count: counts?.nav.exceptions },
            { to: PATHS.dispatcherTracking, label: "Tracking & risk", count: counts?.nav.trackingRisk },
          ].map(item => (
            <Link key={item.to} to={item.to} className="inline-flex items-center gap-2 rounded-control border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-pine hover:bg-rowHover">
              {item.label}
              {item.count !== undefined && <span className="rounded-full bg-chip px-1.5 font-mono text-[11px] text-ink">{item.count}</span>}
            </Link>
          ))}
        </nav>
        <div className="flex flex-wrap items-center gap-2">
          {!overview.isPending && <DataFreshness asOf={freshness?.asOf} nextSyncAt={freshness?.nextSyncAt} stale={freshness?.stale ?? true} />}
          <button type="button" onClick={refresh} disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-control border border-border bg-surface px-3 py-1.5 text-sm disabled:opacity-50">
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} aria-hidden="true" /> Refresh
          </button>
        </div>
      </div>

      {!reviewOnly && <FilterChips
        options={BUCKETS.map(bucket => ({
          value: bucket, label: BUCKET_LABELS[bucket],
          count: !counts ? undefined : bucket === "needs_plan" ? counts.needsPlan : bucket === "awaiting_approval" ? counts.awaitingApproval
            : bucket === "no_feasible_date" ? counts.noFeasibleDate : bucket === "in_execution" ? counts.inExecution : undefined,
        }))}
        selected={state.status ? "" : state.bucket}
        onChange={value => change({ bucket: !state.status && value === state.bucket ? "all" : value })}
      />}
      {counts && (
        <p className="font-mono text-caption text-inkMuted">
          Replan suggested {counts.replanSuggested} · Delivered today {counts.deliveredToday}
        </p>
      )}
      {countsQuery.isError && <p role="status" className="text-caption text-risk-atRisk-fg">Counts are unavailable right now.</p>}
      {countsQuery.isSuccess && counts === null && <p role="status" className="text-caption text-risk-atRisk-fg">Counts response was invalid and is not shown.</p>}

      <div className="grid gap-3 rounded-card border border-border bg-surface p-4 sm:grid-cols-2 xl:grid-cols-4">
        <Field label="Search">
          <div className="flex items-center gap-2 rounded-control border border-border px-2">
            <Search className="h-4 w-4 text-inkMuted" aria-hidden="true" />
            <input aria-label="Search" value={searchInput} maxLength={100} onChange={e => setSearchInput(e.target.value)}
              placeholder="Order no., customer or phone" className="w-full min-w-0 bg-transparent py-2 text-sm font-normal" />
          </div>
        </Field>
        {!reviewOnly && <Field label="Status">
          <select aria-label="Status" value={state.status ?? ""} onChange={e => change({ status: e.target.value })} className={control}>
            <option value="">Any in selected group</option>
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </Field>}
        <Field label="Risk">
          <select aria-label="Risk" value={state.risk ?? ""} onChange={e => change({ risk: e.target.value })} className={control}>
            <option value="">Any risk</option>
            {RISK_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </Field>
        <Field label="Sort">
          <div className="flex gap-2">
            <select aria-label="Sort" value={state.sort ?? ""} onChange={e => change({ sort: e.target.value, desc: null })} className={`${control} w-full`}>
              <option value="">Oldest submitted first</option>
              {SORT_OPTIONS.map(s => <option key={s} value={s}>{SORT_LABELS[s]}</option>)}
            </select>
            <button type="button" disabled={state.sort === null} aria-pressed={state.desc}
              onClick={() => change({ desc: state.desc ? null : "1" })} className={`${control} disabled:opacity-50`}>
              {state.desc ? "Desc" : "Asc"}
            </button>
          </div>
        </Field>
        <Field label="Committed from">
          <input type="date" aria-label="Committed from" value={state.from ?? ""} onChange={e => change({ from: e.target.value })} className={control} />
        </Field>
        <Field label="Committed to">
          <input type="date" aria-label="Committed to" value={state.to ?? ""} onChange={e => change({ to: e.target.value })} className={control} />
        </Field>
        <Field label="Rows per page">
          <select aria-label="Rows per page" value={state.pageSize} onChange={e => change({ page_size: e.target.value })} className={control}>
            {PAGE_SIZES.map(size => <option key={size} value={size}>{size}</option>)}
          </select>
        </Field>
        <div className="flex items-end">
          <button type="button" onClick={clear} disabled={!filtered} className={`${control} disabled:opacity-50`}>Clear filters</button>
        </div>
      </div>
      {isDateRangeInvalid(state) && <p role="alert" className="text-caption text-risk-predictedLate-fg">The “from” date is after the “to” date, so the date filter is not applied.</p>}

      {list.isPending && <LoadingState rows={5} />}
      {list.isError && !page && <ErrorState error={list.error} onRetry={() => void list.refetch()} title="Orders unavailable" />}
      {list.isError && page && (
        <p role="alert" className="rounded-control bg-risk-atRisk-bg p-3 text-sm text-risk-atRisk-fg">
          Refresh failed. Showing the last loaded orders, which may be out of date.
        </p>
      )}
      {page?.invalid && <div role="alert" className="rounded-card border border-border bg-surface p-5">Invalid order response. No data is shown. Please retry.</div>}
      {page && !page.invalid && (
        <>
          {page.skipped > 0 && <p role="status" className="text-caption text-risk-atRisk-fg">{page.skipped} row(s) could not be displayed because their data was invalid.</p>}
          {page.hiddenLegacy > 0 && <p role="status" className="text-caption text-inkMuted">{page.hiddenLegacy} legacy order(s) hidden: they are not part of CFO planning.</p>}
          {page.items.length === 0 ? (
            <div className="rounded-card border border-border bg-surface">
              <EmptyState
                message={filtered ? "No orders match these filters." : "No orders in the queue."}
                action={state.page > 1 ? { label: "Go to first page", onClick: () => change({ page: null }) } : filtered ? { label: "Clear filters", onClick: clear } : undefined}
              />
            </div>
          ) : (
            <>
              <OrderTable items={page.items} />
              <OrderCards items={page.items} />
            </>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-inkMuted">
            <span role="status">{page.total ? `Showing ${first}–${last} of ${page.total}` : "0 orders"}</span>
            <div className="flex items-center gap-2">
              <button type="button" disabled={state.page <= 1} onClick={() => change({ page: String(state.page - 1) })} className={`${control} disabled:opacity-50`}>Previous</button>
              <span className="font-mono">Page {state.page} / {totalPages}</span>
              <button type="button" disabled={state.page >= totalPages} onClick={() => change({ page: String(state.page + 1) })} className={`${control} disabled:opacity-50`}>Next</button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}