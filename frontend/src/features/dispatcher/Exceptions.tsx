/**
 * Dispatcher Exceptions (M5). Read-only operational evidence; no planning/hold/
 * approval/mapping mutations. docs/06 §5, §6.2, §6.6, §10; ASM-005.
 */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowUpRight, RefreshCcw, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiGet, isApiError } from "../../api/client";
import { PATHS } from "../../app/access";
import { useAuthStore } from "../../app/store";
import { EmptyState, LoadingState } from "../../components/StateViews";
import { evidence, orders, skuDetails, suggestions, type Tab } from "./exceptions/model";

const TABS: { key: Tab; title: string }[] = [
  { key:"no-feasible", title:"No Feasible Date" },
  { key:"replan", title:"Replan Suggested" },
  { key:"blocked", title:"Blocked / Unmapped SKU" },
];
const REF = /^[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}$/;

function FetchError({ error, retry }: {error: unknown; retry: ()=>void}) {
  const ref=isApiError(error) && REF.test(error.correlationId ?? "") ? error.correlationId : null;
  return <div role="alert" className="rounded-card border border-border bg-surface p-5">
    <p className="font-semibold text-risk-predictedLate-fg">
      {isApiError(error) && error.status === 403 ? "Access denied" : "Exception data unavailable"}
    </p>
    <p className="mt-2 text-sm text-inkMuted">No operational decision can be made from unavailable data.</p>
    {ref && <p className="mt-2 font-mono text-xs">Request reference: {ref}</p>}
    <button type="button" onClick={retry} className="mt-3 rounded-control border border-border px-4 py-2 text-sm">Retry</button>
  </div>;
}

function Detail({ type, id, onClose }: { type: Tab; id: number; onClose: ()=>void }) {
  const query = useQuery({
    queryKey: ["dispatcher-exception-detail",type,id],
    queryFn: ({signal}) => apiGet<unknown>(
      type === "no-feasible" || type === "replan" ? `/planning-runs/${id}` : `/orders/${id}`,
      undefined,signal),
    retry:false,
  });
  const data=query.data;
  const info=evidence(data);
  return <section aria-label="Exception evidence" className="rounded-card border border-border bg-surface p-5">
    <div className="flex items-center justify-between gap-3"><h3 className="font-semibold text-ink">Evidence · {type === "blocked" ? "Order" : "Run"} #{id}</h3>
      <button type="button" onClick={onClose} className="rounded-control border px-3 py-2 text-xs">Close</button>
    </div>
    {query.isPending && <LoadingState rows={2} className="mt-4" />}
    {query.isError && <FetchError error={query.error} retry={()=>void query.refetch()} />}
    {query.isSuccess && type === "blocked" && <div className="mt-4">
      <p className="text-sm text-inkMuted">Legacy record only. Missing SKU mapping does not create a CFO planning queue or reroute the order.</p>
      {skuDetails(data).length ? <ul className="mt-3 space-y-2">
        {skuDetails(data).map((sku,i)=><li key={i} className="rounded-control bg-stone p-3 font-mono text-sm">{sku.code} · {sku.status}</li>)}
      </ul> : <p className="mt-3 text-sm">No verified unmapped SKU identifiers are available from the scoped order response.</p>}
      <p className="mt-4 text-sm">Escalate to IT through the established support process. Only IT can confirm mappings; mapping cannot retroactively route a legacy order to CFO.</p>
    </div>}
    {query.isSuccess && type !== "blocked" && <div className="mt-4 space-y-4">
      <p className="text-sm">Result: <strong>{info.result}</strong> · failed check: <strong>{info.failedCheck}</strong></p>
      {type === "no-feasible" && <p className="text-sm">Earliest feasible date: <strong>{info.earliest ?? "Not verified"}</strong>. Do not change a promised date without a recorded agreement.</p>}
      {type === "replan" && <div className="rounded-control bg-stone p-4 text-sm">
        <strong>Suggestion only · {info.kind}</strong>
        <p className="mt-2">The committed plan remains in force. This inspection creates no hold and cannot approve the suggestion. Server-authorised replacement/keep-current workflow is not yet verified.</p>
      </div>}
      <div><h4 className="font-semibold">Dates searched (reported by planning service)</h4>
        {info.checkedDates.length ? <ul className="mt-2 grid gap-2 sm:grid-cols-2">
          {info.checkedDates.map((day,i)=><li key={i} className="rounded-control bg-stone px-3 py-2 text-xs font-mono">{day.date} · {day.result} {day.check ?? ""}</li>)}
        </ul> : <p className="mt-2 text-sm text-inkMuted">Checked dates not supplied; none inferred.</p>}
      </div>
      <div><h4 className="font-semibold">Warehouse gate evidence</h4>
        {info.warehouseChecks.length ? <ul className="mt-2 space-y-1">{info.warehouseChecks.map((v,i)=>
          <li key={i} className="text-sm">{v.warehouse} · {v.failed} · {v.code}</li>)}</ul>
          : <p className="mt-2 text-sm text-inkMuted">Per-warehouse checks not provided.</p>}
        {info.candidateCodes.length > 0 && <p className="mt-2 text-xs text-inkMuted">Rejected candidate codes: {info.candidateCodes.join(", ")}</p>}
      </div>
      {type === "no-feasible" && <p className="text-sm text-inkMuted">Any alternative date, transfer or manual plan must be reviewed in its authorised order workflow; no action is initiated here.</p>}
    </div>}
  </section>;
}

export function Exceptions() {
  const user = useAuthStore(s=>s.user);
  const allowed=Boolean(user?.roles.includes("dispatcher"));
  const [params,setParams]=useSearchParams();
  const current=params.get("tab");
  const tab:Tab=current === "replan" || current === "blocked" ? current : "no-feasible";
  const search=params.get("q") ?? "";
  const [detail,setDetail]=useState<{type:Tab;id:number}|null>(null);
  const list=useQuery({
    queryKey:["dispatcher-exceptions",user?.id,user?.market,tab],
    enabled:allowed,
    retry:false,
    queryFn:({signal})=>tab === "replan"
      ? apiGet<unknown>("/alerts",{type:"REPLAN_SUGGESTED",resolved:false},signal)
      : apiGet<unknown>("/orders",{status:tab === "blocked"?"BLOCKED_UNMAPPED_SKU":"NO_FEASIBLE_DATE",page:1,page_size:50},signal),
  });
  const all=tab==="replan" ? suggestions(list.data) : orders(list.data).filter(o=>
    o.status === (tab === "blocked" ? "BLOCKED_UNMAPPED_SKU" : "NO_FEASIBLE_DATE"));
  const filtered=all.filter(item=> tab==="replan"
    ? (`order #${"orderId" in item ? item.orderId : ""}`).toLowerCase().includes(search.toLowerCase().trim())
    : ("ref" in item && [item.ref,String(item.id),item.reason].join(" ").toLowerCase().includes(search.toLowerCase().trim())));
  function change(key:string,value:string) {
    const next=new URLSearchParams(params);
    if(value) next.set(key,value); else next.delete(key);
    setParams(next,{replace:true});
    setDetail(null);
  }
  if(!allowed) return <section data-screen="Exceptions" role="alert" className="rounded-card border p-6">
    <h1 className="text-2xl font-bold">Dispatcher exceptions</h1><p>Dispatcher access required. No exceptions were loaded.</p>
  </section>;
  return <section data-screen="Exceptions" className="space-y-5">
    <header><p className="font-mono text-xs font-semibold uppercase text-pine">Dispatcher · Exceptions</p>
      <h1 className="mt-2 text-3xl font-bold text-ink">Exceptions</h1>
      <p className="mt-2 text-sm text-inkMuted">Inspect infeasible orders, proposed replans and legacy SKU blockers without changing committed work.</p>
    </header>
    <nav aria-label="Exception categories" className="flex flex-wrap gap-2">
      {TABS.map(x=><button key={x.key} type="button" aria-current={tab===x.key?"page":undefined}
        className={`rounded-control px-4 py-2 text-sm font-semibold ${tab===x.key?"bg-pine text-white":"border border-border bg-surface text-ink"}`}
        onClick={()=>change("tab",x.key)}>{x.title}</button>)}
    </nav>
    <div className="flex flex-wrap items-end justify-between gap-3">
      <label className="flex flex-col gap-1 text-sm font-semibold text-ink">Search order reference or reason
        <input value={search} onChange={e=>change("q",e.target.value)}
          className="rounded-control border border-border bg-surface px-3 py-2 font-normal" placeholder="Filter loaded results" />
      </label>
      <button type="button" disabled={list.isFetching} onClick={()=>void list.refetch()}
        className="inline-flex items-center gap-2 rounded-control border px-4 py-2 text-sm disabled:opacity-50">
        <RefreshCcw className="h-4 w-4" /> Refresh
      </button>
    </div>
    <p className="text-xs text-inkMuted" role="status">Loaded results only (up to one server page). {list.dataUpdatedAt ? "Snapshot may be stale; refresh before acting." : "Freshness not verified."}</p>
    {tab==="replan" && <div className="rounded-card border border-border bg-stone p-4 text-sm">
      <ShieldAlert className="mr-2 inline h-4 w-4" /> Replan suggestions do not replace approved plans, acquire holds or dispatch vehicles. Approval and keep-current actions are withheld until server workflows are verified.
    </div>}
    {tab==="blocked" && <div className="rounded-card border border-border bg-stone p-4 text-sm">
      Legacy unmapped orders are not an active Dispatcher backlog. Only IT can map SKUs. Mapping later never automatically moves an existing legacy order into CFO.
    </div>}
    {list.isPending && <LoadingState rows={3} />}
    {list.isError && <FetchError error={list.error} retry={()=>void list.refetch()} />}
    {list.isSuccess && filtered.length === 0 && <EmptyState message={search ? "No loaded exceptions match this filter." : "No exceptions reported for this category. This does not prove the source is current."} />}
    {list.isSuccess && filtered.length>0 && <div className="space-y-3">
      {filtered.map(item=> "orderId" in item ? <article key={item.id} className="rounded-card border border-border bg-surface p-5">
        <div className="flex flex-wrap justify-between gap-3"><div>
          <h2 className="font-semibold text-ink">Order #{item.orderId}</h2>
          <p className="mt-1 font-mono text-xs text-inkMuted">REPLAN_SUGGESTED · Alert #{item.id} · {item.level}</p>
        </div><span className="rounded-full bg-stone px-3 py-1 text-xs">Current plan unchanged</span></div>
        <p className="mt-3 text-sm">Suggestion run: {item.runId ?? "Not reported"}. No automatic commitment or date change.</p>
        {item.runId && <button type="button" className="mt-3 rounded-control border px-4 py-2 text-sm" onClick={()=>setDetail({type:tab,id:item.runId!})}>Inspect suggestion</button>}
      </article> : <article key={item.id} className="rounded-card border border-border bg-surface p-5">
        <div className="flex flex-wrap items-start justify-between gap-3"><div>
          <h2 className="font-semibold text-ink">{item.ref}</h2>
          <p className="mt-1 font-mono text-xs text-inkMuted">{item.status} · Risk {item.risk} · Reason {item.reason}</p>
          <p className="mt-1 text-xs text-inkMuted">Requested date: {item.requestedDate ?? "Not reported"}</p>
        </div><AlertTriangle className="h-5 w-5 text-risk-predictedLate-fg" aria-hidden="true" /></div>
        <div className="mt-4 flex flex-wrap gap-3">
          {tab==="no-feasible" && item.latestRunId && <button className="rounded-control border px-4 py-2 text-sm" type="button"
            onClick={()=>setDetail({type:tab,id:item.latestRunId!})}>Inspect infeasibility</button>}
          {tab==="blocked" && <button type="button" className="rounded-control border px-4 py-2 text-sm" onClick={()=>setDetail({type:tab,id:item.id})}>Inspect mapped SKU evidence</button>}
          {tab==="no-feasible" && <Link className="inline-flex items-center gap-1 rounded-control bg-pine px-4 py-2 text-sm text-white" to={item.latestRunId ? `${PATHS.dispatcherPlanReview}/${item.latestRunId}` : PATHS.dispatcherOrders}>
            Open planning review <ArrowUpRight className="h-4 w-4" /></Link>}
        </div>
      </article>)}
    </div>}
    {detail && <Detail key={`${detail.type}-${detail.id}`} type={detail.type} id={detail.id} onClose={()=>setDetail(null)} />}
  </section>;
}
