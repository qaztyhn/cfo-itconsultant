/**
 * M8 Operational KPI dashboard — read-only views over server-authoritative metrics.
 * US-KPI-01/02, US-LOG-01; docs/03 §5.7, docs/06 §14–15 and §17.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuthStore } from "../../app/store";
import { canViewKpi } from "../../app/access";
import { apiFetch, apiGet, isApiError } from "../../api/client";
import { EmptyState, LoadingState } from "../../components/StateViews";
import {
  BASELINE_METRICS, CARDS, METRICS, dailyPoints, decisions,
  displayValue, metricValue, supportingValue, pageNumber, validDate, validId, type MetricKey,
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
  const commit=supportingValue(data,"order_to_commit_min");
  const counter=supportingValue(data,"counter_commit_rate");
  const manual=supportingValue(data,"manual_plan_count");
  return <div aria-label="Operational KPIs" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
    {CARDS.map(([key])=>{
      const meta=METRICS.find(m=>m.key===key)!;
      const value=metricValue(data,key);
      return <section key={key} data-metric={key} className="rounded-card border border-border bg-surface p-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-inkMuted">{meta.label}</p>
        {key==="eta_error_min"?<div className="mt-4 space-y-2">
          <p className="font-mono text-2xl font-bold text-ink">Median {displayValue(value.median,"min")}</p>
          <p>P90 {displayValue(value.p90,"min")}</p>
          <p className="text-xs text-inkMuted">Target: median {displayValue(value.targetMedian,"min")} · P90 {displayValue(value.targetP90,"min")}</p>
          <p className="text-xs text-inkMuted">Forecast before trip Dispatch vs proof of delivery.</p>
        </div>:<div className="mt-4 space-y-2">
          <p className="font-mono text-2xl font-bold text-ink">{displayValue(value.value,meta.unit)}</p>
          <p className="text-xs text-inkMuted">{meta.direction==="lower"?"Lower is better":"Higher is better"}</p>
          {(key==="planning_time_min"||key==="manual_intervention_rate")&&
            <p className="text-xs text-inkMuted">Baseline: {displayValue(value.baseline,meta.unit)}</p>}
          {(key==="planning_time_min"||key==="plan_acceptance_rate")&&
            <p className="text-sm">Sales {displayValue(value.sales,meta.unit)} · Dispatcher {displayValue(value.dispatcher,meta.unit)}</p>}
          {key==="planning_time_min"&&<p className="text-xs text-inkMuted">
            Submit → confirmed: Sales {displayValue(commit.sales,"min")} · Dispatcher {displayValue(commit.dispatcher,"min")}
          </p>}
          {key==="on_time_rate"&&<p className="text-xs text-inkMuted">Delivered inside the promised window. Failed deliveries excluded.</p>}
          {key==="plan_acceptance_rate"&&<p className="text-xs text-inkMuted">
            Committed at the counter: {displayValue(counter.value,"percent")}
          </p>}
          {key==="manual_intervention_rate"&&<p className="text-xs text-inkMuted">
            Manual plans: {displayValue(manual.value,"count")}
          </p>}
        </div>}
      </section>;
    })}
  </div>;
}
function Trend({data,metric}:{data:unknown;metric:MetricKey}) {
  const points=dailyPoints(data);
  const supplied=points.filter(point=>point.value!==null);
  const meta=METRICS.find(x=>x.key===metric)!;
  if(!supplied.length)return <EmptyState message="Chưa có dữ liệu"/>;
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
function BaselineEditor({onSaved}:{onSaved:()=>void}) {
  const [metric,setMetric]=useState<MetricKey>("planning_time_min");
  const [value,setValue]=useState("");
  const [saved,setSaved]=useState(false);
  const numeric=value.trim()!==""?Number(value):NaN;
  const valid=Number.isFinite(numeric)&&numeric>=0;
  const mutation=useMutation({
    mutationFn:(amount:number)=>apiFetch<unknown>(`/kpi/baseline/${metric}`,{
      method:"PUT",body:JSON.stringify({value:amount}),
    }),
    onSuccess:()=>{setSaved(true);onSaved();},
    onError:()=>setSaved(false),
  });
  function submit(e:FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if(!valid||mutation.isPending)return;
    setSaved(false);
    mutation.mutate(numeric);
  }
  return <section className="rounded-card border border-border bg-surface p-5">
    <h2 className="text-lg font-bold">Admin · baseline editor</h2>
    <p className="mt-1 text-sm text-inkMuted">
      Enter an assumed baseline explicitly; it is not an observed KPI. The server must approve this update.
    </p>
    <form onSubmit={submit} className="mt-4 flex flex-wrap items-end gap-3">
      <label className="flex min-w-56 flex-col gap-1 text-sm">Metric
        <select aria-label="Baseline metric" className="rounded-control border border-border p-2"
          value={metric} onChange={e=>{setMetric(e.target.value as MetricKey);setSaved(false);mutation.reset();}}>
          {BASELINE_METRICS.map(item=><option value={item.key} key={item.key}>{item.label}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">Baseline value (API metric unit)
        <input aria-label="Baseline value" type="number" min="0" step="any" value={value}
          onChange={e=>{setValue(e.target.value);setSaved(false);mutation.reset();}}
          className="rounded-control border border-border p-2"/>
      </label>
      <button type="submit" disabled={!valid||mutation.isPending}
        className="rounded-control bg-pine px-4 py-2 font-semibold text-white disabled:opacity-50">
        {mutation.isPending?"Saving…":"Save baseline"}
      </button>
    </form>
    {saved&&<p role="status" className="mt-3 text-sm text-pine">Baseline saved by server. KPI summary refreshed.</p>}
    {mutation.isError&&<p role="alert" className="mt-3 text-sm text-ink">
      Baseline was not saved. Check your permissions and the backend endpoint.
    </p>}
  </section>;
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
    Boolean(from&&to&&(from>to||
      (Date.parse(to+"T00:00:00Z")-Date.parse(from+"T00:00:00Z"))/86400000>=366));
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
    {ready&&user?.roles.includes("admin")&&<BaselineEditor onSaved={()=>void summary.refetch()}/>}
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
