/**
 * M8 Operational KPI dashboard — read-only views over server-authoritative metrics.
 * US-KPI-01/02, US-LOG-01; docs/03 §5.7, docs/06 §14–15 and §17.
 */
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useAuthStore } from "../../app/store";
import { canViewKpi } from "../../app/access";
import { apiGet, isApiError } from "../../api/client";
import { EmptyState, LoadingState } from "../../components/StateViews";
import {
  CARDS, DIAGNOSTICS, METRICS, dailyPoints, decisions, diagnosticValue,
  displayValue, metricValue, pageNumber, validDate, validId, type MetricKey,
} from "./model";

const PAGE_SIZE=25;
function SafeError({error,retry,title}:{error:unknown;retry:()=>void;title:string}) {
  const denied=isApiError(error)&&error.status===403;
  const ref=isApiError(error)&&typeof error.correlationId==="string" &&
    /^[a-fA-F0-9-]{36}$/.test(error.correlationId)?error.correlationId:null;
  return <div role="alert" className="rounded-card border border-border bg-surface p-5">
    <h3 className="font-semibold text-ink">{denied?"Access denied":title}</h3>
    <p className="mt-2 text-sm text-inkMuted">Data cannot be verified. No figures are inferred from this failure.</p>
    {ref&&<p className="mt-2 font-mono text-xs">Request reference: {ref}</p>}
    {!denied&&<button type="button" className="mt-3 rounded-control border border-border px-3 py-2 text-sm" onClick={retry}>Retry</button>}
  </div>;
}
function KpiCards({data}:{data:unknown}) {
  return <div aria-label="Operational KPIs" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
    {CARDS.map((keys,i)=><section key={i} className="rounded-card border border-border bg-surface p-5">
      <p className="font-mono text-xs font-semibold uppercase tracking-wide text-inkMuted">
        {keys.map(key=>METRICS.find(m=>m.key===key)?.label).join(" · ")}
      </p>
      <div className="mt-4 space-y-3">{keys.map(key=>{
        const meta=METRICS.find(m=>m.key===key)!;
        const value=metricValue(data,key);
        return <div key={key} data-metric={key} className="space-y-1">
          {keys.length>1&&<p className="text-xs text-inkMuted">{meta.label}</p>}
          <p className="font-mono text-2xl font-bold text-ink">{displayValue(value.value,meta.unit)}</p>
          <p className="text-xs text-inkMuted">{meta.direction==="lower"?"Lower is better":"Higher is better"}</p>
          <p className="text-xs text-inkMuted">Baseline: {displayValue(value.baseline,meta.unit)}</p>
          {value.change!==null&&<p className="text-xs font-semibold text-pine">
            Server-reported baseline change: {value.change.toLocaleString("en-US",{maximumFractionDigits:2})}
          </p>}
        </div>;
      })}</div>
    </section>)}
  </div>;
}
function Trend({data,metric}:{data:unknown;metric:MetricKey}) {
  const points=dailyPoints(data);
  const supplied=points.filter(point=>point.value!==null);
  const meta=METRICS.find(x=>x.key===metric)!;
  if(!supplied.length)return <EmptyState message="No verified daily KPI points for this selection."/>;
  const values=supplied.map(point=>point.value as number);
  const high=Math.max(...values),low=Math.min(...values);
  const span=Math.max(high-low,Math.abs(high)||1);
  return <div className="space-y-3">
    <p className="text-xs text-inkMuted">Daily values supplied by the KPI API; dates are market-local. Missing values are gaps, not zeroes.</p>
    <div role="img" aria-label={`Daily trend for ${meta.label}; ${supplied.length} reported observations`}
      className="flex h-40 items-end gap-1 overflow-x-auto border-b border-border pb-2">
      {points.map(point=>{
        const height=point.value===null?0:Math.max(7,((point.value-low)/span)*105+17);
        return <div key={point.day} className="flex min-w-2 flex-1 items-end justify-center" title={`${point.day}: ${displayValue(point.value,meta.unit)}`}>
          {point.value!==null?<div className="w-full max-w-8 rounded-t bg-pine" style={{height:`${height}px`}}/>:
            <span className="h-1 w-full bg-border"/>}
        </div>;
      })}
    </div>
    <div className="max-h-40 overflow-y-auto">
      <table className="w-full text-left text-xs"><caption className="sr-only">Accessible daily KPI values</caption>
        <thead><tr><th scope="col" className="py-2">Market-local day</th><th scope="col" className="py-2">Value</th></tr></thead>
        <tbody>{points.map(point=><tr key={point.day} className="border-t border-border">
          <td className="py-1 font-mono">{point.day}</td><td className="py-1 font-mono">{displayValue(point.value,meta.unit)}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </div>;
}
export function KpiDashboard() {
  const user=useAuthStore(s=>s.user);
  const allowed=Boolean(user&&canViewKpi(user));
  const auditAllowed=Boolean(user&&(user.roles.includes("admin")||user.roles.includes("dispatcher")||
    (user.roles.includes("viewer")&&user.kpi_scopes.includes("ops"))));
  const [params,setParams]=useSearchParams();
  const from=validDate(params.get("from"));
  const to=validDate(params.get("to"));
  const fromRaw=params.get("from"),toRaw=params.get("to");
  const invalidRange=(Boolean(fromRaw)&&from===null)||(Boolean(toRaw)&&to===null)||
    Boolean(from&&to&&from>to);
  const warehouseRaw=params.get("warehouse_id"),storeRaw=params.get("store_id");
  const warehouseId=validId(warehouseRaw),storeId=validId(storeRaw);
  const invalidLocation=Boolean(warehouseRaw&&!warehouseId)||Boolean(storeRaw&&!storeId);
  // Warehouse-scoped ops users must not broaden reports to all markets/locations.
  const canFilterLocation=Boolean(user?.roles.includes("admin")||user?.roles.includes("dispatcher"));
  const metricCandidate=params.get("metric");
  const metric:MetricKey=METRICS.find(m=>m.key===metricCandidate)?.key??"on_time_rate";
  const logPage=pageNumber(params.get("log_page"));
  const actionInput=params.get("action")??"";
  const action=/^[A-Z][A-Z0-9_]{0,63}$/.test(actionInput)?actionInput:"";
  const orderId=validId(params.get("order_id"));
  const invalidLogFilter=Boolean(params.get("order_id")&&!orderId)||
    Boolean(actionInput&&!action);
  const ready=allowed&&!invalidRange&&!invalidLocation&&
    (canFilterLocation||(!warehouseRaw&&!storeRaw));
  const filters={from:from??undefined,to:to??undefined};
  const summary=useQuery({queryKey:["ops-kpi","summary",user?.id,user?.market,from,to,warehouseId,storeId],
    enabled:ready,retry:false,
    queryFn:({signal})=>apiGet<unknown>("/kpi/summary",{
      ...filters,warehouse_id:canFilterLocation?warehouseId:undefined,
      store_id:canFilterLocation?storeId:undefined,
    },signal)});
  const daily=useQuery({queryKey:["ops-kpi","daily",user?.id,user?.market,metric,from,to],
    enabled:ready,retry:false,
    queryFn:({signal})=>apiGet<unknown>("/kpi/daily",{metric,...filters},signal)});
  const diagnostics=useQuery({queryKey:["ops-kpi","diagnostics",user?.id,user?.market,from,to],
    enabled:ready,retry:false,
    queryFn:({signal})=>apiGet<unknown>("/kpi/diagnostics",filters,signal)});
  const audit=useQuery({queryKey:["ops-kpi","audit",user?.id,user?.market,from,to,action,orderId,logPage],
    enabled:ready&&auditAllowed&&!invalidLogFilter,retry:false,
    queryFn:({signal})=>apiGet<unknown>("/audit/decisions",{
      ...filters,action:action||undefined,order_id:orderId??undefined,page:logPage,page_size:PAGE_SIZE,
    },signal)});
  function change(values:Record<string,string|null>) {
    const next=new URLSearchParams(params);
    Object.entries(values).forEach(([key,value])=>{if(value)next.set(key,value);else next.delete(key);});
    setParams(next,{replace:true});
  }
  if(!allowed) return <section data-screen="KpiDashboard" role="alert" className="rounded-card border border-border p-6">
    <h1 className="text-2xl font-bold">KPIs & decision log</h1>
    <p className="mt-2">You do not have access to KPIs. Operational KPI access requires admin or ops scope.</p>
  </section>;
  return <section data-screen="KpiDashboard" className="space-y-6">
    <header><p className="font-mono text-xs uppercase font-semibold text-pine">Pilot value metrics</p>
      <h1 className="mt-2 text-3xl font-bold text-ink">KPIs & decision log</h1>
      <p className="mt-2 text-sm text-inkMuted">Server-calculated operational metrics only. Unknown and unsupported data remain unavailable.</p>
    </header>
    <div aria-label="KPI filters" className="grid gap-3 rounded-card border border-border bg-surface p-4 sm:grid-cols-2 xl:grid-cols-4">
      <label className="flex flex-col gap-1 text-sm">From
        <input type="date" aria-label="From" value={fromRaw??""} onChange={e=>change({from:e.target.value})}
          className="rounded-control border border-border bg-surface p-2"/>
      </label>
      <label className="flex flex-col gap-1 text-sm">To
        <input type="date" aria-label="To" value={toRaw??""} onChange={e=>change({to:e.target.value})}
          className="rounded-control border border-border bg-surface p-2"/>
      </label>
      {canFilterLocation&&<label className="flex flex-col gap-1 text-sm">Warehouse ID
        <input aria-label="Warehouse ID" inputMode="numeric" value={warehouseRaw??""} onChange={e=>change({warehouse_id:e.target.value})}
          className="rounded-control border border-border bg-surface p-2" placeholder="All authorised"/>
      </label>}
      {canFilterLocation&&<label className="flex flex-col gap-1 text-sm">Store ID
        <input aria-label="Store ID" inputMode="numeric" value={storeRaw??""} onChange={e=>change({store_id:e.target.value})}
          className="rounded-control border border-border bg-surface p-2" placeholder="All authorised"/>
      </label>}
    </div>
    {!ready&&<p role="alert" className="rounded-card border border-border p-5 text-sm">
      Invalid or unauthorised filters. No KPI data was requested; check dates and location scope.
    </p>}
    {ready&&<div className="space-y-3">
      <h2 className="text-xl font-bold text-ink">Operational performance</h2>
      {summary.isPending&&<LoadingState rows={3}/>}
      {summary.isError&&<SafeError title="KPI summary unavailable" error={summary.error} retry={()=>void summary.refetch()}/>}
      {summary.isSuccess&&<KpiCards data={summary.data}/>}
    </div>}
    {ready&&<section className="rounded-card border border-border bg-surface p-5">
      <h2 className="text-xl font-bold">Daily KPI trend</h2>
      <label className="mt-3 flex max-w-sm flex-col gap-1 text-sm">Metric
        <select aria-label="Trend metric" value={metric} onChange={e=>change({metric:e.target.value})}
          className="rounded-control border border-border bg-surface p-2">
          {METRICS.map(item=><option key={item.key} value={item.key}>{item.label}</option>)}
        </select>
      </label>
      <div className="mt-4">
        {daily.isPending&&<LoadingState rows={2}/>}
        {daily.isError&&<SafeError title="Daily KPI trend unavailable" error={daily.error} retry={()=>void daily.refetch()}/>}
        {daily.isSuccess&&<Trend data={daily.data} metric={metric}/>}
      </div>
    </section>}
    {ready&&<section className="rounded-card border border-border bg-deepPine p-5 text-white">
      <h2 className="text-lg font-bold">Operational diagnostics</h2>
      <p className="mt-1 text-xs">Unsupported diagnostics are not zero.</p>
      {diagnostics.isPending&&<p role="status" className="mt-3">Loading diagnostics…</p>}
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        {DIAGNOSTICS.map(item=><div key={item.key} data-diagnostic={item.key}>
          <p className="font-mono text-xs uppercase">{item.label}</p>
          <p className="mt-2 font-mono text-xl font-bold">
            {diagnostics.isSuccess?displayValue(diagnosticValue(diagnostics.data,item.key),item.unit):"Unavailable"}
          </p>
        </div>)}
      </div>
      {diagnostics.isError&&<p role="status" className="mt-3 text-xs">Diagnostic endpoint unavailable; values withheld.</p>}
    </section>}
    <section className="space-y-3">
      <h2 className="text-xl font-bold">Decision log</h2>
      <p className="text-xs text-inkMuted">Append-only audit records. Free-text reasons, actor names, raw snapshots and personal data are withheld.</p>
      {!auditAllowed?<p role="alert" className="rounded-card border p-4">Decision log access requires admin, dispatcher, or viewer with ops scope.</p>:<>
        <div className="grid gap-3 rounded-card border border-border bg-surface p-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">Action code
            <input aria-label="Action code" value={actionInput} onChange={e=>change({action:e.target.value.toUpperCase(),log_page:null})}
              placeholder="All actions" className="rounded-control border border-border bg-surface p-2"/>
          </label>
          <label className="flex flex-col gap-1 text-sm">Order ID
            <input aria-label="Order ID" inputMode="numeric" value={params.get("order_id")??""}
              onChange={e=>change({order_id:e.target.value,log_page:null})}
              placeholder="All orders" className="rounded-control border border-border bg-surface p-2"/>
          </label>
        </div>
        {invalidLogFilter&&<p role="alert" className="text-sm">Invalid audit filter; no audit request sent.</p>}
        {ready&&!invalidLogFilter&&<>
          {audit.isPending&&<LoadingState rows={4}/>}
          {audit.isError&&<SafeError title="Decision log unavailable" error={audit.error} retry={()=>void audit.refetch()}/>}
          {audit.isSuccess&&(()=>{
            const logs=decisions(audit.data);
            return <div className="overflow-x-auto rounded-card border border-border bg-surface">
              {logs.items.length===0?<EmptyState message="No decisions reported for the selected filters."/>:
                <table className="w-full min-w-[640px] text-left text-sm">
                  <caption className="sr-only">Privacy-safe decision audit records</caption>
                  <thead className="bg-stone text-xs uppercase text-inkMuted"><tr>
                    {["Time","Who","Action","Subject","Safe detail"].map(label=>
                      <th scope="col" key={label} className="px-4 py-3">{label}</th>)}
                  </tr></thead>
                  <tbody className="divide-y divide-border">{logs.items.map(item=><tr key={item.id}>
                    <td className="px-4 py-3 font-mono text-xs">{item.at}</td>
                    <td className="px-4 py-3">{item.actor}</td>
                    <td className="px-4 py-3 font-mono text-xs">{item.action}</td>
                    <td className="px-4 py-3">{item.subject}</td>
                    <td className="px-4 py-3 text-xs">
                      Audit #{item.id}
                      {item.correlationId&&<span className="block font-mono">Correlation: {item.correlationId}</span>}
                    </td>
                  </tr>)}</tbody>
                </table>}
              <nav aria-label="Decision log pages" className="flex items-center justify-between gap-3 p-3 text-sm">
                <span>Page {logPage} · {logs.total??"Unknown"} records reported</span>
                <div className="flex gap-2">
                  <button type="button" className="rounded-control border px-3 py-2 disabled:opacity-40"
                    disabled={logPage===1} onClick={()=>change({log_page:String(logPage-1)})}>Previous</button>
                  <button type="button" className="rounded-control border px-3 py-2 disabled:opacity-40"
                    disabled={logs.total!==null?logPage*PAGE_SIZE>=logs.total:logs.items.length<PAGE_SIZE}
                    onClick={()=>change({log_page:String(logPage+1)})}>Next</button>
                </div>
              </nav>
            </div>;
          })()}
        </>}
      </>}
    </section>
  </section>;
}
