/**
 * A15 My Store Orders — read-only store-scoped Sales monitoring.
 * docs/03 §A15; docs/06 §5.1–5.4; US-ORD-02 AC1–3, US-REV-01 AC2/4.
 * No dispatch, sync-now, Sales approval, or other mutations on this screen.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, RefreshCw, Search } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { apiGet, isApiError } from "../../api/client";
import { canViewRevenue, PATHS } from "../../app/access";
import { useAuthStore } from "../../app/store";
import { EmptyState, LoadingState } from "../../components/StateViews";
import {
  FILTER_STATUSES, PAGE_SIZE, SORT_OPTIONS, projectDetail, projectPage, validPage,
} from "./orders/model";

const REF = /^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$/;
function ErrorNotice({ error, onRetry, detail = false }: {
  error: unknown; onRetry: () => void; detail?: boolean;
}) {
  const status = isApiError(error) ? error.status : null;
  const ref = isApiError(error) && REF.test(error.correlationId ?? "") ? error.correlationId : null;
  return <div role="alert" className="rounded-card border border-border bg-surface p-5">
    <h3 className="font-bold text-ink">{status === 403 ? "Access denied" :
      status === 404 && detail ? "Order unavailable or outside your store scope" :
        "Orders unavailable"}</h3>
    <p className="mt-2 text-sm text-inkMuted">No information from another store is displayed. Check access or retry.</p>
    {ref && <p className="mt-2 font-mono text-xs">Reference: {ref}</p>}
    <button type="button" onClick={onRetry} className="mt-3 rounded-control border border-border px-4 py-2 text-sm">Retry</button>
  </div>;
}
function when(value: string | null): string {
  if (!value) return "Not available";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toISOString().replace("T", " ").slice(0, 16) + " UTC" : "Not available";
}
function StoreOrderDetails({ orderId, allowedStores, onClose }: {
  orderId: number; allowedStores: number[]; onClose: () => void;
}) {
  const detailQuery = useQuery({
    queryKey: ["my-store-orders","detail",orderId,allowedStores.join(",")],
    queryFn: ({signal}) => apiGet<unknown>(`/orders/${orderId}`,undefined,signal),
    retry: false,
  });
  const detail = detailQuery.data === undefined ? null : projectDetail(detailQuery.data,allowedStores,orderId);
  return <section aria-labelledby="store-order-detail-title" className="rounded-card border border-border bg-surface p-5">
    <div className="flex items-start justify-between gap-3">
      <h2 id="store-order-detail-title" className="text-xl font-bold text-ink">Order details · read only</h2>
      <button type="button" onClick={onClose} className="rounded-control border border-border px-3 py-2 text-sm">Close</button>
    </div>
    {detailQuery.isPending && <LoadingState rows={3} className="mt-4" />}
    {detailQuery.isError && <ErrorNotice detail error={detailQuery.error} onRetry={()=>void detailQuery.refetch()} />}
    {detailQuery.isSuccess && !detail && <div role="alert" className="mt-4 text-sm text-inkMuted">
      Order unavailable or outside your store scope. Contact your administrator if you believe this is an error.
    </div>}
    {detailQuery.isSuccess && detail && <div className="mt-4 space-y-4">
      <p className="font-mono text-sm font-semibold">{detail.reference} · {detail.status}</p>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Requested date",when(detail.requestedDate)],
          ["Committed date",when(detail.committedDate)],
          ["Promised start",when(detail.promisedStart)],
          ["Promised end",when(detail.promisedEnd)],
          ["Allowed forecast ETA",when(detail.forecastEta)],
        ].map(([label,value])=><div key={label} className="rounded-control bg-stone p-3">
          <dt className="text-xs text-inkMuted">{label}</dt>
          <dd className="mt-1 font-mono text-sm text-ink">{value}</dd>
        </div>)}
      </dl>
      <div>
        <h3 className="font-semibold text-ink">Order lines</h3>
        {detail.lines.length === 0 ? <p className="mt-2 text-sm text-inkMuted">No line details reported.</p> :
          <ul className="mt-2 divide-y divide-border rounded-control border border-border">
            {detail.lines.map(line=><li key={line.number} className="flex flex-wrap justify-between gap-2 p-3 text-sm">
              <span>{line.product}</span><span className="font-mono">{line.quantity} {line.unit}</span>
            </li>)}
          </ul>}
      </div>
      <p className="text-xs text-inkMuted">No customer contact details, driver GPS, planning scores, dispatch or approval controls are shown.</p>
    </div>}
  </section>;
}

export function MyStoreOrders() {
  const user = useAuthStore(s=>s.user);
  const [params,setParams] = useSearchParams();
  const isSales = Boolean(user?.roles.includes("sales"));
  const assigned = Array.from(new Set((user?.location_ids ?? []).filter(id=>Number.isSafeInteger(id) && id>0))).sort((a,b)=>a-b);
  const storeParam = params.get("store") ?? "all";
  const selectedStore = storeParam === "all" ? null : assigned.find(id=>String(id)===storeParam) ?? null;
  const invalidStore = storeParam !== "all" && selectedStore === null;
  const statusParam = params.get("status") ?? "ALL";
  const status = FILTER_STATUSES.find(s=>s===statusParam) ?? "ALL";
  const sortParam = params.get("sort") ?? "submitted_at";
  const sort = SORT_OPTIONS.find(s=>s.value===sortParam)?.value ?? "submitted_at";
  const page=validPage(params.get("page"));
  const queryText=(params.get("q") ?? "").slice(0,100);
  const selectedRaw = params.get("order");
  const selectedOrder = selectedRaw && /^\d+$/.test(selectedRaw) ? Number(selectedRaw) : null;
  const validOrder = selectedOrder !== null && Number.isSafeInteger(selectedOrder) && selectedOrder>0;
  const mayRequest = isSales && assigned.length>0 && !invalidStore;
  const storeIds = selectedStore ? [selectedStore] : assigned;
  const listQuery=useQuery({
    queryKey:["my-store-orders","list",user?.id,user?.market,assigned.join(","),selectedStore,status,sort,page,queryText],
    enabled:mayRequest,
    retry:false,
    queryFn:({signal})=>apiGet<unknown>("/orders",{
      store_id:selectedStore,
      status:status==="ALL"?undefined:status,
      q:queryText.trim() || undefined,
      sort,page,page_size:PAGE_SIZE,
    },signal),
  });
  const list=listQuery.isSuccess ? projectPage(listQuery.data,storeIds,page,PAGE_SIZE) : null;
  const canRevenue = Boolean(user && canViewRevenue(user) &&
    (user.owned_location_ids ?? []).some(id=>assigned.includes(id)));
  function update(changes:Record<string,string|null>,resetPage=true) {
    const next=new URLSearchParams(params);
    for(const [key,value] of Object.entries(changes)) {
      if(value === null || value === "" || (key==="store" && value==="all") ||
        (key==="status" && value==="ALL") || (key==="sort" && value==="submitted_at") ||
        (key==="page" && value==="1")) next.delete(key);
      else next.set(key,value);
    }
    if(resetPage) next.delete("page");
    if(!Object.hasOwn(changes,"order")) next.delete("order");
    setParams(next,{replace:true});
  }
  if(!isSales) return <section data-screen="MyStoreOrders" role="alert" className="rounded-card border border-border bg-surface p-6">
    <h1 className="text-2xl font-bold">My store orders</h1><p>Sales access required. No orders were loaded.</p>
  </section>;
  if(assigned.length===0) return <section data-screen="MyStoreOrders" role="alert" className="rounded-card border border-border bg-surface p-6">
    <h1 className="text-2xl font-bold">My store orders</h1><p>No authorized store assignment is available. No orders were requested.</p>
  </section>;
  return <section data-screen="MyStoreOrders" className="space-y-5">
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div><p className="font-mono text-xs font-semibold uppercase text-pine">Sales · Scoped to your stores</p>
        <h1 className="mt-2 text-3xl font-bold text-ink">My store orders</h1>
        <p className="mt-2 text-sm text-inkMuted">Read-only order status and delivery visibility. Store access is enforced by the server.</p>
      </div>
      {canRevenue && <Link to={PATHS.revenue} className="inline-flex items-center gap-2 rounded-control border border-border bg-surface px-4 py-2 text-sm font-semibold text-pine">
        Revenue · my location <ArrowUpRight className="h-4 w-4" aria-hidden="true"/>
      </Link>}
    </header>
    <div className="grid gap-3 rounded-card border border-border bg-surface p-4 sm:grid-cols-2 xl:grid-cols-4">
      <label className="flex flex-col gap-1 text-xs font-semibold">Store
        <select aria-label="Store" value={storeParam} onChange={e=>update({store:e.target.value})} className="rounded-control border border-border bg-surface p-2 text-sm font-normal">
          <option value="all">All my assigned stores</option>
          {assigned.map(id=><option key={id} value={id}>Store #{id}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs font-semibold">Search
        <div className="flex items-center gap-2 rounded-control border border-border px-2">
          <Search className="h-4 w-4 text-inkMuted" aria-hidden="true"/>
          <input aria-label="Search" value={queryText} onChange={e=>update({q:e.target.value})}
            placeholder="Order reference or customer" className="min-w-0 w-full bg-transparent py-2 text-sm font-normal"/>
        </div>
      </label>
      <label className="flex flex-col gap-1 text-xs font-semibold">Status
        <select aria-label="Status" value={status} onChange={e=>update({status:e.target.value})} className="rounded-control border border-border bg-surface p-2 text-sm font-normal">
          {FILTER_STATUSES.map(s=><option value={s} key={s}>{s==="ALL"?"All statuses":s.replaceAll("_"," ")}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs font-semibold">Sort
        <select aria-label="Sort" value={sort} onChange={e=>update({sort:e.target.value})} className="rounded-control border border-border bg-surface p-2 text-sm font-normal">
          {SORT_OPTIONS.map(s=><option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </label>
    </div>
    <div className="flex items-center justify-between gap-3 text-xs text-inkMuted">
      <span role="status">Server-scoped results. {listQuery.dataUpdatedAt ? "Snapshot loaded; refresh for updates." : "Freshness not verified."}</span>
      <button type="button" disabled={listQuery.isFetching || invalidStore} onClick={()=>void listQuery.refetch()}
        className="inline-flex items-center gap-2 rounded-control border border-border px-3 py-2 text-sm disabled:opacity-50">
        <RefreshCw className="h-4 w-4" aria-hidden="true"/> Refresh
      </button>
    </div>
    {invalidStore && <div role="alert" className="rounded-card border border-border p-5">Selected store is unavailable or outside your scope. No orders were requested.</div>}
    {mayRequest && listQuery.isPending && <LoadingState rows={4}/>}
    {mayRequest && listQuery.isError && <ErrorNotice error={listQuery.error} onRetry={()=>void listQuery.refetch()}/>}
    {list && <div className="overflow-x-auto rounded-card border border-border bg-surface">
      {list.items.length===0 ? <EmptyState message="No orders returned for these filters or the selected store."/> :
        <table className="w-full min-w-[740px] text-left text-sm">
          <caption className="sr-only">Orders belonging to authorized stores</caption>
          <thead className="bg-stone text-xs uppercase text-inkMuted"><tr>
            {["Order","Store","Status","Requested","Committed","Promised end","Details"].map(label=>
              <th scope="col" className="px-4 py-3" key={label}>{label}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-border">{list.items.map(order=><tr key={order.id}>
            <td className="px-4 py-3"><span className="font-mono font-semibold">{order.reference}</span>
              <span className="mt-1 block text-xs text-inkMuted">{order.customer ?? "Customer unavailable"} · {order.site ?? "Site unavailable"}</span></td>
            <td className="px-4 py-3">{order.storeCode ?? `Store #${order.storeId}`}</td>
            <td className="px-4 py-3"><span className="rounded-full bg-stone px-2 py-1 font-mono text-xs">{order.status}</span></td>
            <td className="px-4 py-3 font-mono text-xs">{when(order.requestedDate)}</td>
            <td className="px-4 py-3 font-mono text-xs">{when(order.committedDate)}</td>
            <td className="px-4 py-3 font-mono text-xs">{when(order.promisedEnd)}</td>
            <td className="px-4 py-3"><button type="button" onClick={()=>update({order:String(order.id)},false)}
              className="rounded-control border border-border px-3 py-2 font-semibold text-pine">View details</button></td>
          </tr>)}</tbody>
        </table>}
    </div>}
    {list && <nav aria-label="Order pages" className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <p>Page {page}{list.total !== null ? ` · ${list.total} orders reported` : " · total not reported"}</p>
      <div className="flex gap-2">
        <button type="button" disabled={page===1} onClick={()=>update({page:String(page-1)},false)}
          className="rounded-control border border-border px-4 py-2 disabled:opacity-40">Previous</button>
        <button type="button" disabled={list.total !== null ? page*PAGE_SIZE>=list.total : list.items.length<PAGE_SIZE}
          onClick={()=>update({page:String(page+1)},false)}
          className="rounded-control border border-border px-4 py-2 disabled:opacity-40">Next</button>
      </div>
    </nav>}
    {validOrder && mayRequest && <StoreOrderDetails key={selectedOrder} orderId={selectedOrder!} allowedStores={storeIds}
      onClose={()=>update({order:null},false)}/>}
  </section>;
}
